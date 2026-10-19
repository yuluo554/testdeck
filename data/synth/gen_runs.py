#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成 run 语料生成器 + 真值台账 `expect.json`（D5 / D6 / D7）。

设计要点（对应 `plan/04-数据计划.md` §二 真值纪律）：

1. **确定性**：同 `--seed` 输出**逐字节一致**。实现手段：单点 `random.Random(seed)`、
   全整数/字符串（无浮点）、字典键序固定、`\n` 行尾、不读系统时钟、不迭代 set。
2. **真值只存输入与期望**：`expect.json` 里 `anchors` / `samples` 同时带
   **输入侧**（`history` / `timings_ms` / `regression_split` / `runs`）与**期望侧**
   （分型 / flaky_score / p50 / p95 / 回归标记）。**不存** `observed` 类字段——
   那会让基准退化成"比对两份预答案"，引擎全坏也全绿。由
   `bench/refimpl.py:_find_observed_keys` 与本脚本的生成期断言双重守门。
3. **生成期自证**：写完立刻用**参照实现**（`bench/refimpl.py`，与生产实现零共享代码）
   复算，不一致即拒绝落盘；并逐项断言"要求覆盖的模式**真的存在**"
   （"我打算生成" != "生成出来了"）。
4. **假数据白名单**：分支只允许 `main` / `feature/synth-*` / `fix/synth-*`；
   仓库名只允许 `demo-app` / `demo-lib` / `demo-web`；commit 用 40 位全数字占位；
   `ci_run_id` 从 `1000000000` 起递增。**零真实组织名 / 用户名 / 域名 / 路径**。

用法：

    py -3.12 data/synth/gen_runs.py                      # 生成（默认 200 run × 5000 用例）
    py -3.12 data/synth/gen_runs.py --seed 42 --check    # 只校验，不写盘
    py -3.12 data/synth/gen_runs.py --runs 40 --cases 600
    py -3.12 data/synth/gen_runs.py --big 50000          # 单文件 5 万用例（性能门语料）

退出码：0 成功 / 1 自证失败或 `--check` 对不上 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

#: 入库的真值台账（D7）
LEDGER_PATH = os.path.join(HERE, "expect.json")
#: 大文件语料（D6，不入仓——见 .gitignore 的 `data/synth/*.xml`）
BIG_XML_PATH = os.path.join(HERE, "big.xml")
#: 三份生产规则包（快照源；此处**读 JSON 文件**，不 import `testdeck.*`）
RULES_DIR = os.path.join(ROOT, "src", "testdeck", "rules")

LABELS = ("stable", "flaky", "broken", "watch")
STATUSES = ("pass", "fail", "skip", "missing")

#: 假仓库名白名单
REPOS = ("demo-app", "demo-lib", "demo-web")
#: 假分支白名单（前缀形态）
BRANCH_PATTERNS = ("main", "feature/synth-", "fix/synth-")
#: 固定基准时刻（不读系统时钟，保证可重放）
BASE_TIME = "2026-01-01T00:00:00+00:00"
#: 假 ci_run_id 起点
RUN_ID_BASE = 1000000000
#: 假 commit 起点（40 位全数字占位）
COMMIT_BASE = 1


# ── 载入参照实现（同一份代码，不复制逻辑）──────────────────────────────


def _load_refimpl():
    path = os.path.join(ROOT, "bench", "refimpl.py")
    spec = importlib.util.spec_from_file_location("testdeck_refimpl", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


refimpl = _load_refimpl()


def load_rules_snapshot():
    """把三份生产规则包拍成快照（前瞻口径一致：测试另断言快照 == 生产规则）。"""
    with open(os.path.join(RULES_DIR, "flaky.json"), "r", encoding="utf-8") as fh:
        flaky = json.load(fh)
    with open(os.path.join(RULES_DIR, "slow.json"), "r", encoding="utf-8") as fh:
        slow = json.load(fh)
    with open(os.path.join(RULES_DIR, "view.json"), "r", encoding="utf-8") as fh:
        view = json.load(fh)
    return {
        "flaky": flaky["flaky"],
        "slow": slow["slow"],
        "percentile": slow["percentile"],
        "view": view["view"],
    }


# ── 状态序列构造器（纯函数，全部确定性）────────────────────────────────


def all_status(status, n):
    return [status] * n


def k_transitions(n, k):
    """构造**恰好 k 次状态翻转**的计数序列。

    做法：把 n 个位置切成 k+1 个交替的块，块长尽量均分。这样翻转数恰为 k，
    且 pass/fail 数量大致平衡（``fail_rate`` 落在区间中部），才能真的落进
    ``flaky`` 区间。

    早期版本把"剩余位置全塞进末态"，导致 ``n=200, k=3`` 时 fail_rate 高达
    0.985（越过 0.95 上界）→ 分型被算成 ``watch``，"flaky 样本"其实不存在。
    生成期断言正是靠"四类分型各 ≥1"抓住了这个错误。
    """
    if k <= 0:
        return ["pass"] * n
    if k + 1 > n:
        raise ValueError("n=%d 装不下 %d 次翻转" % (n, k))
    blocks = k + 1
    base, extra = divmod(n, blocks)
    seq = []
    status = "pass"
    for i in range(blocks):
        size = base + (1 if i < extra else 0)
        seq.extend([status] * size)
        status = "fail" if status == "pass" else "pass"
    if len(seq) != n:
        raise AssertionError("块长分配错误：%d != %d" % (len(seq), n))
    actual = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    if actual != k:
        raise AssertionError("翻转数 %d != 目标 %d" % (actual, k))
    return seq


def insert_status(history, status, positions):
    """在指定位置把状态替换成 skip/missing（用于造"不制造 transition"的样本）。"""
    seq = list(history)
    for pos in positions:
        seq[pos % len(seq)] = status
    return seq


def constant_timings(n, ms):
    """常量耗时窗口：让 p50 恰等于 ms（边界样本需要精确值）。"""
    return [ms] * n


def ramp_timings(n, start, step):
    return [start + step * i for i in range(n)]


def window_around(length, center):
    """围绕 ``center`` 的对称窗口：**p50 恰等于 center**，但 p50 != p95。

    用途：回归边界的 ratio/delta 必须精确可控，所以窗口中位数要钉死；
    同时又不能全常量，否则 p95 与插值分支永远走不到。
    对称偏移（偶数长度取 ``[-L/2..-1] + [1..L/2]``）使中位两点均值为 0。
    """
    if length <= 0:
        return []
    half = length // 2
    offsets = list(range(-half, 0))
    if length % 2 == 1:
        offsets.append(0)
    offsets.extend(range(1, half + 1))
    return [center + off for off in offsets]


# ── 用例构造器 ─────────────────────────────────────────────────────────


def make_case(name, history, timings, split=None):
    if len(history) != len(timings):
        raise ValueError("history 与 timings 长度必须一致：%s" % name)
    return {
        "name": name,
        "history": history,
        "timings_ms": timings,
        "regression_split": split,
    }


def build_anchors():
    """手工设计的锚点：**逐一覆盖** plan/04 §二.5 要求的模式。

    每条锚点都写明 `intent`，生成期断言据它复核"意图真的兑现了"。
    """
    anchors = []
    runs_n = 12

    def add(anchor, case, intent):
        anchors.append({"anchor": anchor, "case": case, "intent": intent})

    # —— 四类分型各 ≥1 ——
    add("stable_all_pass",
        make_case("anchor_stable", all_status("pass", runs_n), constant_timings(runs_n, 100)),
        {"label": "stable"})

    add("broken_all_fail",
        make_case("anchor_broken", all_status("fail", runs_n), constant_timings(runs_n, 100)),
        {"label": "broken"})

    add("flaky_min_transitions",
        make_case("anchor_flaky", k_transitions(runs_n, 3), constant_timings(runs_n, 100)),
        {"label": "flaky", "transitions": 3})

    # watch：fail_rate 落在 [0.05, 0.95] 内但 transitions < 3
    add("watch_low_transitions",
        make_case("anchor_watch_low_transitions", k_transitions(runs_n, 2),
                  constant_timings(runs_n, 100)),
        {"label": "watch", "transitions": 2})

    # watch：fail_rate 低于下界（0.05）
    low_rate = ["pass"] * 60 + ["fail"]
    add("watch_below_min_rate",
        make_case("anchor_watch_low_rate", low_rate, constant_timings(len(low_rate), 100)),
        {"label": "watch"})

    # watch：fail_rate 高于上界（0.95）
    high_rate = ["fail"] * 60 + ["pass"]
    add("watch_above_max_rate",
        make_case("anchor_watch_high_rate", high_rate, constant_timings(len(high_rate), 100)),
        {"label": "watch"})

    # —— missing ≥1、skip ≥1 ——
    with_missing = insert_status(k_transitions(runs_n, 4), "missing", [2, 6])
    add("missing_sample",
        make_case("anchor_missing", with_missing, constant_timings(runs_n, 100)),
        {"has_missing": True})

    with_skip = insert_status(k_transitions(runs_n, 4), "skip", [1, 5])
    add("skip_sample",
        make_case("anchor_skip", with_skip, constant_timings(runs_n, 100)),
        {"has_skip": True})

    # 零计数样本：这条用例在所有 run 都是 skip/missing -> fail_rate 是 0/0、无定义，
    # 分型必须落 watch（不得因为 "fails == 0" 就判成 stable）。
    add("watch_no_counted_runs",
        make_case("anchor_no_counted_runs",
                  ["skip", "missing", "skip", "missing", "skip", "missing"],
                  constant_timings(6, 100)),
        {"label": "watch", "counted_runs": 0})

    # —— transitions 1..5 梯度 ——
    for k in (1, 2, 3, 4, 5):
        add("transitions_%d" % k,
            make_case("anchor_transitions_%d" % k, k_transitions(runs_n, k),
                      constant_timings(runs_n, 100)),
            {"transitions": k})

    # —— 回归六边界（ratio 恰好/略低/略高；delta 恰好/略低/略高）——
    # 常量窗口让 p50 恰等于窗口值，边界才是精确的（不是"近似"）。
    def reg_case(name, base_ms, curr_ms):
        timings = constant_timings(4, base_ms) + constant_timings(4, curr_ms)
        return make_case(name, all_status("pass", 8), timings, split=4)

    add("reg_ratio_exact_delta_exact",
        reg_case("anchor_reg_1_2_exact_200_exact", 1000, 1200),
        {"regression": True, "why": "ratio 恰 1.2（>=）且 delta 恰 200ms（>=）"})
    add("reg_ratio_exact_delta_below",
        reg_case("anchor_reg_1_2_exact_200_below", 900, 1080),
        {"regression": False, "why": "ratio 恰 1.2 但 delta 180ms < 200ms → 不判回归"})
    add("reg_ratio_below",
        reg_case("anchor_reg_ratio_below", 1000, 1199),
        {"regression": False, "why": "ratio 1.199 < 1.2"})
    add("reg_ratio_above",
        reg_case("anchor_reg_ratio_above", 1000, 1201),
        {"regression": True, "why": "ratio 1.201 > 1.2 且 delta 201ms > 200ms"})
    add("reg_delta_exact_ratio_above",
        reg_case("anchor_reg_delta_exact", 500, 700),
        {"regression": True, "why": "delta 恰 200ms（>=）且 ratio 1.4 > 1.2"})
    add("reg_delta_below",
        reg_case("anchor_reg_delta_below", 500, 699),
        {"regression": False, "why": "delta 199ms < 200ms"})
    add("reg_delta_above",
        reg_case("anchor_reg_delta_above", 500, 701),
        {"regression": True, "why": "delta 201ms > 200ms 且 ratio 1.402 > 1.2"})
    add("reg_undefined_base",
        reg_case("anchor_reg_undefined_base", 0, 500),
        {"regression": None, "why": "base_p50 == 0 → undefined_base，不判回归"})

    return anchors


# ── runs（run 侧输入）───────────────────────────────────────────────────


def build_runs(count):
    """构造 count 条假 run 元数据（白名单值，完全确定性）。"""
    runs = []
    for i in range(count):
        if i % 5 == 0:
            branch = "main"
        elif i % 5 in (1, 2, 3):
            branch = "feature/synth-%d" % (i % 7)
        else:
            branch = "fix/synth-%d" % (i % 5)
        runs.append({
            "index": i,
            "repo": REPOS[i % len(REPOS)],
            "branch": branch,
            # 40 位全数字占位：从 1 起递增
            "commit_sha": "%040d" % (COMMIT_BASE + i),
            "ci_run_id": str(RUN_ID_BASE + i),
            # 固定基准时刻 + 递增分钟数（不读系统时钟）
            "started_at": _plus_minutes(BASE_TIME, i),
        })
    return runs


def _plus_minutes(iso, minutes):
    """在固定基准时刻上加分钟（手算，不引 datetime 时区依赖，保证逐字节一致）。"""
    from datetime import datetime, timedelta

    base = datetime.fromisoformat(iso)
    return (base + timedelta(minutes=minutes)).isoformat()


# ── 语料（D5）──────────────────────────────────────────────────────────


def build_corpus(runs_n, cases_n, seed):
    """构造主辅料：cases_n 个用例，每个用例的 history 长度 = runs_n。

    分型配比由索引 + 局部 RNG 决定（确定性）；目的是让四类分型都有可观数量，
    且带出 skip / missing / 各档 transitions，供 M4/M5 基准使用。
    """
    rng = random.Random(seed)
    cases = []
    for i in range(cases_n):
        name = "case_%05d" % i
        bucket = i % 12
        if bucket in (0, 1, 2, 3, 4):
            # stable：绝大多数通过，偶发一条 skip / missing
            history = all_status("pass", runs_n)
            if bucket == 4 and runs_n > 4:
                history = insert_status(history, "skip", [i % runs_n])
        elif bucket == 5:
            history = all_status("fail", runs_n)  # broken
        elif bucket in (6, 7, 8):
            # flaky：transitions 3..5
            history = k_transitions(runs_n, 3 + (bucket - 6))
        elif bucket == 9:
            # watch：区间内但 transitions 不足
            history = k_transitions(runs_n, 1 + (i % 2))
        elif bucket == 10:
            # watch：低失效率
            history = ["pass"] * runs_n
            for pos in range(max(1, runs_n // 40)):
                history[(pos * 7) % runs_n] = "fail"
        else:
            # 带 missing 的混合样本
            history = insert_status(k_transitions(runs_n, 4), "missing",
                                    [i % runs_n, (i + 3) % runs_n])
        # 少量样本插入 missing（覆盖"missing 不进分母、不制造 transition"）
        if i % 37 == 0 and runs_n > 6:
            history = insert_status(history, "missing", [i % runs_n])
        if i % 53 == 0 and runs_n > 8:
            history = insert_status(history, "skip", [(i + 2) % runs_n])

        # 耗时：按 6 档原型分配，保证语料里**同时**有真回归与非回归。
        # 口径提醒：回归 = ratio >= 1.2 **且** delta >= 200ms，两条都要满足。
        # （早期版本只造"变慢"样本，结果 regression_false == 0，M5 的
        #   "不误报"半边就没料可测；生成期断言已把这条钉死。）
        split = runs_n // 2
        archetype = i % 6
        if archetype == 0:
            # 平稳：比率与 delta 都不达标 -> 非回归
            timings = window_around(runs_n, 300)
        elif archetype == 1:
            # 比率达标但 delta 只有 150ms -> 非回归（delta 是卡点）
            timings = window_around(split, 400) + window_around(runs_n - split, 550)
        elif archetype == 2:
            # delta 达 300ms 但比率只有 1.15 -> 非回归（ratio 是卡点）
            timings = window_around(split, 2000) + window_around(runs_n - split, 2300)
        elif archetype == 3:
            # 恰好压边界：ratio 恰 1.2 且 delta 恰 200ms -> 回归（边界计入）
            timings = window_around(split, 1000) + window_around(runs_n - split, 1200)
        elif archetype == 4:
            # 明显回归：ratio 1.8 / delta 400ms
            timings = window_around(split, 500) + window_around(runs_n - split, 900)
        else:
            # 无回归窗口（base/curr 不可得）-> undefined_base / missing_window
            split = None
            timings = ramp_timings(runs_n, 100 + (i % 9), 3)
        # 少量 missing 耗时（None）：验证"缺失不补 0、不进样本"
        if i % 61 == 0 and runs_n > 5:
            timings = list(timings)
            timings[i % runs_n] = None

        cases.append(make_case(name, history, timings, split))
    _ = rng  # 保留 rng 供后续扩展；当前生成路径完全由索引决定（更稳）
    return cases


def subsample(cases, size, seed):
    """确定性子采样：按名字排序后等距抽取（不依赖 set 迭代序）。"""
    ordered = sorted(cases, key=lambda c: c["name"])
    if size >= len(ordered):
        return ordered
    step = len(ordered) / float(size)
    picked = [ordered[min(len(ordered) - 1, int(i * step))] for i in range(size)]
    # 去重（等距抽取可能撞到同一条）后补齐
    seen = []
    names = set()
    for case in picked:
        if case["name"] not in names:
            names.add(case["name"])
            seen.append(case)
    idx = 0
    while len(seen) < size and idx < len(ordered):
        if ordered[idx]["name"] not in names:
            names.add(ordered[idx]["name"])
            seen.append(ordered[idx])
        idx += 1
    return sorted(seen, key=lambda c: c["name"])


# ── 台账装配 ───────────────────────────────────────────────────────────


def build_ledger(seed=42, runs_n=200, cases_n=5000, sample_size=50):
    rules = load_rules_snapshot()
    anchors = build_anchors()
    runs = build_runs(runs_n)
    corpus = build_corpus(runs_n, cases_n, seed)
    samples = subsample(corpus, sample_size, seed)

    anchor_records = []
    for entry in anchors:
        case = entry["case"]
        derived = refimpl.expected_for_case(case, rules)
        anchor_records.append({
            "anchor": entry["anchor"],
            "intent": entry["intent"],
            "case": case,
            "expected": derived,
        })

    sample_records = []
    for case in samples:
        derived = refimpl.expected_for_case(case, rules)
        sample_records.append({"case": case, "expected": derived})

    totals = refimpl.recompute_totals(corpus, rules)

    return {
        "schema": 1,
        "generator": {
            "script": "data/synth/gen_runs.py",
            "seed": seed,
            "params": {"runs": runs_n, "cases": cases_n, "sample_size": sample_size},
            "note": "真值只存输入与期望；不存 observed。参照实现见 bench/refimpl.py。",
        },
        "rules_snapshot": rules,
        "runs": runs,
        "anchors": anchor_records,
        "samples": sample_records,
        "expected_totals": totals,
    }


def dumps_ledger(ledger):
    """稳定序列化：键序固定、缩进 2、无 BOM、`\\n` 行尾、末尾一个换行。"""
    return json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


# ── 生成期断言（"我打算生成" != "生成出来了"）────────────────────────────


def run_generation_assertions(ledger):
    """对**已生成的内容**逐项断言模式覆盖；返回问题清单（空 = 通过）。"""
    problems = []
    rules = ledger["rules_snapshot"]
    anchors = ledger["anchors"]
    corpus_totals = ledger["expected_totals"]

    # ① 每条锚点的意图必须兑现
    for record in anchors:
        intent = record["intent"]
        expected = record["expected"]
        for key, want in intent.items():
            if key == "why":
                continue
            if key == "has_missing":
                if want and "missing" not in record["case"]["history"]:
                    problems.append("%s：意图要 missing，但 history 里没有" % record["anchor"])
                continue
            if key == "has_skip":
                if want and "skip" not in record["case"]["history"]:
                    problems.append("%s：意图要 skip，但 history 里没有" % record["anchor"])
                continue
            got = expected.get(key)
            if got != want:
                problems.append("%s：意图 %s=%r，实算 %r" % (record["anchor"], key, want, got))

    # ② 四类分型各 ≥1（在锚点集合上）
    labels_present = {r["expected"]["label"] for r in anchors}
    for label in LABELS:
        if label not in labels_present:
            problems.append("锚点里缺分型：%s" % label)

    # ③ 语料整体也必须四类齐全（锚点是一小撮，语料是底座）
    for label in LABELS:
        if corpus_totals["label_counts"].get(label, 0) < 1:
            problems.append("语料里缺分型：%s" % label)

    # ④ missing / skip 至少在语料里各出现一次
    if corpus_totals["status_counts"].get("missing", 0) < 1:
        problems.append("语料里没有 missing 状态")
    if corpus_totals["status_counts"].get("skip", 0) < 1:
        problems.append("语料里没有 skip 状态")

    # ⑤ transitions 1..5 梯度（锚点集合）
    anchor_transitions = {r["expected"]["transitions"] for r in anchors}
    for k in (1, 2, 3, 4, 5):
        if k not in anchor_transitions:
            problems.append("锚点缺 transitions=%d" % k)

    # ⑥ 回归六边界：ratio 恰好/略低/略高、delta 恰好/略低/略高
    by_anchor = {r["anchor"]: r["expected"] for r in anchors}
    boundary_expectations = {
        "reg_ratio_exact_delta_exact": True,
        "reg_ratio_exact_delta_below": False,
        "reg_ratio_below": False,
        "reg_ratio_above": True,
        "reg_delta_exact_ratio_above": True,
        "reg_delta_below": False,
        "reg_delta_above": True,
        "reg_undefined_base": None,
    }
    for anchor, want in boundary_expectations.items():
        if anchor not in by_anchor:
            problems.append("缺回归边界锚点：%s" % anchor)
            continue
        got = by_anchor[anchor]["regression"]
        if got is not want:
            problems.append("回归边界 %s：期望 %r，实算 %r" % (anchor, want, got))

    # ⑦ 至少有一条 True / 一条 False 回归（防"全 None 也算过"）
    reg_values = [r["expected"]["regression"] for r in anchors]
    if True not in reg_values:
        problems.append("没有任何锚点判为回归（判据可能恒假）")
    if False not in reg_values:
        problems.append("没有任何锚点判为非回归（判据可能恒真）")

    # ⑦b **语料**里也必须有真回归（锚点是一小撮，底座要能撑 M5 的"能检出"半边）
    if corpus_totals.get("regression_true", 0) < 1:
        problems.append("语料里没有任何真回归样本（regression_true == 0）"
                        "——M5 的回归基准将无从检出")
    if corpus_totals.get("regression_false", 0) < 1:
        problems.append("语料里没有任何非回归样本（regression_false == 0）")

    # ⑧ 假数据白名单
    for run in ledger["runs"]:
        branch = run["branch"]
        if not (branch == "main" or branch.startswith("feature/synth-")
                or branch.startswith("fix/synth-")):
            problems.append("分支不在白名单：%s" % branch)
        if run["repo"] not in REPOS:
            problems.append("仓库名不在白名单：%s" % run["repo"])
        if len(run["commit_sha"]) != 40 or not run["commit_sha"].isdigit():
            problems.append("commit 不是 40 位全数字占位：%s" % run["commit_sha"])
        if int(run["ci_run_id"]) < RUN_ID_BASE:
            problems.append("ci_run_id 小于起点：%s" % run["ci_run_id"])

    # ⑨ 真值里没有 observed 类字段
    observed = refimpl._find_observed_keys(ledger)
    if observed:
        problems.append("真值出现 observed 类字段：%s" % observed[:5])

    # ⑩ 参照实现独立复算（这是"真值可被输入侧独立算出"的硬证据）
    problems.extend(refimpl.verify_ledger(ledger))

    return problems


# ── 大文件语料（D6，性能门）────────────────────────────────────────────


def write_big_xml(path, total_cases, suites=50):
    """写单文件 `total_cases` 用例的 JUnit XML（性能门语料；不入仓）。

    用 `iterparse` 友好的普通结构：`testsuites` → 多个 `testsuite` → `testcase`。
    只为"能被子迭代解析"，不追求语义丰富。
    """
    per_suite = max(1, total_cases // suites)
    root = ET.Element("testsuites", {
        "name": "synth-big",
        "tests": str(per_suite * suites),
        "failures": "0",
        "errors": "0",
    })
    written = 0
    for s in range(suites):
        suite = ET.SubElement(root, "testsuite", {
            "name": "big.suite_%02d" % s,
            "tests": str(per_suite),
            "failures": "0",
            "errors": "0",
            "time": "0.100",
        })
        for c in range(per_suite):
            ET.SubElement(suite, "testcase", {
                "classname": "big.pkg.mod%d" % (c % 200),
                "name": "test_case_%06d" % (s * per_suite + c),
                "time": "0.001",
            })
            written += 1
    tree = ET.ElementTree(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return written


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gen_runs", description="合成 run 语料 + 真值台账")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--cases", type=int, default=5000)
    parser.add_argument("--sample-size", type=int, default=50,
                        help="入库台账里的样本条数（全程语料不入仓，体积原因）；"
                             "默认值必须与已入库的 expect.json 一致，"
                             "否则裸跑 `--check` 会假红")
    parser.add_argument("--check", action="store_true", help="只校验不写盘")
    parser.add_argument("--big", type=int, default=0,
                        help="另写单文件 N 用例的性能门语料（不入仓）")
    parser.add_argument("--ledger", default=LEDGER_PATH)
    args = parser.parse_args(argv)

    if args.runs < 1 or args.cases < 1 or args.sample_size < 1:
        print("用法错误：--runs / --cases / --sample-size 必须为正整数", file=sys.stderr)
        return 2

    ledger = build_ledger(args.seed, args.runs, args.cases, args.sample_size)
    problems = run_generation_assertions(ledger)

    if problems:
        for item in problems:
            print("FAIL  生成期断言：" + item)
        print("结论：自证失败，拒绝落盘（%d 处）" % len(problems))
        return 1

    text = dumps_ledger(ledger)

    if args.check:
        if not os.path.isfile(args.ledger):
            print("FAIL  --check：台账不存在，无法比对：%s" % args.ledger)
            return 1
        with open(args.ledger, "r", encoding="utf-8") as fh:
            existing = fh.read()
        if existing != text:
            print("FAIL  --check：重生成结果与已登记台账**不逐字节一致**")
            print("      （seed=%d runs=%d cases=%d）" % (args.seed, args.runs, args.cases))
            return 1
        print("PASS  --check：与已登记台账逐字节一致（%d 字节）" % len(text.encode("utf-8")))
        print("      生成期断言全过：四类分型齐 / missing+skip 齐 / transitions 1..5 / 回归六边界")
        return 0

    with open(args.ledger, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("PASS  写出台账 %s（%d 字节）" % (args.ledger, len(text.encode("utf-8"))))
    print("      锚点 %d / 样本 %d / runs %d / 语料用例 %d"
          % (len(ledger["anchors"]), len(ledger["samples"]),
             len(ledger["runs"]), ledger["expected_totals"]["cases"]))

    if args.big:
        written = write_big_xml(BIG_XML_PATH, args.big)
        size = os.path.getsize(BIG_XML_PATH)
        print("PASS  写出大文件语料 %s（%d 用例 / %.1f MB）"
              % (BIG_XML_PATH, written, size / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
