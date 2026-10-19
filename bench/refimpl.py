#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参照实现：只读 `expect.json` 的**输入侧**，独立复算期望值。

三条纪律（见 `plan/04-数据计划.md` §二 真值纪律）：

1. **不 import `testdeck.*`**——与生产实现零共享代码。守门方式：AST 扫描 +
   变异验证（`bench/run_all.py:no_production_import_problems`，以及
   `tests/test_bench_refimpl.py` 把一条 `from testdeck import model` 的变异样本
   喂给守门函数并断言它报红）。
2. 阈值**全部来自 `expect.json` 的 `rules_snapshot`**，不读
   `src/testdeck/rules/*.json`。参照实现一旦去读生产规则包，"独立复算"就退化成
   "读同一份配置互相点头"。两者是否一致由 `tests/test_bench_refimpl.py` 单独断言
   ——那是"口径一致性"检查，不是"真值复算"。
3. 只用标准库；数值用 `fractions.Fraction` 精确运算，避免浮点漂移。

本模块**不是**被测对象：它算出的值只用于（a）生成期自证（`gen_runs.py` 写完即复算）、
（b）与生产实现对账（M4/M5 的 `bench_flaky.py` / `bench_slow.py`）。

四态字符串在这里是**独立常量**（不是从 `testdeck.model` 借的）——这一点是刻意的：
如果参照实现和被测实现共用状态枚举，"枚举写错"这类缺陷在两边同时错，对账就抓不到。
两边是否一致由口径一致性测试守。
"""

from __future__ import annotations

import json
import math
from decimal import Decimal, localcontext
from fractions import Fraction

#: 四态（与 data/README.md §四 的枚举定义一致；此处独立声明，理由见模块 docstring）
PASS, FAIL, SKIP, MISSING = "pass", "fail", "skip", "missing"
STATUSES = (PASS, FAIL, SKIP, MISSING)

#: 参与 fail_rate / flaky_score 计数的状态
COUNTED = (PASS, FAIL)


# ── 精确数值的渲染 ─────────────────────────────────────────────────────


def render(value):
    """Fraction -> 精确十进制串（终止小数）；不终止则用 ``p/q``。``None`` -> ``None``。

    为什么不用 ``float``：`fail_rate` 的边界（5% / 95%）与回归比值（1.2）必须精确。
    浮点会让"恰好等于阈值"的样本随机落到某一侧，基准就成了掷硬币。
    """
    if value is None:
        return None
    if not isinstance(value, Fraction):
        value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    reduced = value.denominator
    for prime in (2, 5):
        while reduced % prime == 0:
            reduced //= prime
    if reduced != 1:
        return "%d/%d" % (value.numerator, value.denominator)
    with localcontext() as ctx:
        ctx.prec = 80
        dec = Decimal(value.numerator) / Decimal(value.denominator)
    return format(dec, "f")


def _frac(value):
    """把规则里的十进制字符串（``"1.2"`` / ``"0.05"``）转成精确 Fraction。"""
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value))


# ── 分位数（线性插值）───────────────────────────────────────────────────


def percentile(values, p):
    """线性插值分位数：索引 ``(n-1)*p``，floor/ceil 两点按小数部分插值。

    输入按值升序排序（稳定）；空样本 -> ``None``；单样本 -> 该值。
    公式与 `plan/03` 模块④ / `rules/slow.json:percentile.index_formula` 一致。
    """
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    if n == 1:
        return Fraction(ordered[0])
    idx = Fraction(n - 1) * _frac(p)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return Fraction(ordered[lo])
    frac = idx - lo
    return Fraction(ordered[lo]) + (Fraction(ordered[hi]) - Fraction(ordered[lo])) * frac


def p50_of(timings):
    """窗口内 p50（缺失耗时 ``None`` 不进样本、不补 0）。"""
    return percentile([t for t in timings if t is not None], Fraction(1, 2))


def p95_of(timings, p95="0.95"):
    return percentile([t for t in timings if t is not None], p95)


# ── 分型 ───────────────────────────────────────────────────────────────


def compute_profile(history, rules):
    """从状态序列算 fail_rate / transitions / flaky_score / 分型。

    口径（`data/README.md` §四 与 `plan/03` 模块③）：

    - 分母只含 pass/fail；skip/missing 既不进分母，也**不制造 transition**；
    - ``transitions`` = 相邻两个"参与计数"的 run 状态不同则 +1（跳过它们的 skip/missing）；
    - ``flaky_score = transitions / (n - 1)``，``n < 2`` -> 0；
    - 分型顺序：**先判恒失败** -> ``fail_rate == 1`` 是 ``broken``、``== 0`` 是 ``stable``；
      再判 ``flaky``（区间内且 transitions 达标）；其余 ``watch``；
    - **样本不足降级**：窗口 run 数 < ``min_runs_for_flaky`` -> 一律 ``watch``
      （"不得输出 flaky"，见 `plan/03` 模块③ 降级）；
    - **零计数降级**：``n == 0``（该用例在所有 run 都是 skip/missing）时 ``fail_rate``
      是 0/0、**无定义**，一律 ``watch``。不得判成 ``stable``——"一次都没真正跑过"
      不构成"稳定"的证据；算成 stable 会让 stable 计数虚高，把"这个用例根本没在跑"
      这类真问题藏起来。
    """
    counted = [s for s in history if s in COUNTED]
    n = len(counted)
    passes = counted.count(PASS)
    fails = counted.count(FAIL)
    transitions = sum(1 for a, b in zip(counted, counted[1:]) if a != b)
    # 零计数样本（n == 0）的 fail_rate 是 0/0、**无定义** → None（不是 Fraction(0)）。
    # 渲染成 "0" 会与"跑过且从没失败"（stable）撞车，正是 K34 要禁的误导；
    # 这一条与 `data/README.md` §四「分型降级②（零计数样本）」同源。
    fail_rate = Fraction(fails, n) if n else None
    flaky_score = Fraction(transitions, n - 1) if n >= 2 else Fraction(0)

    min_rate = _frac(rules["min_fail_rate"])
    max_rate = _frac(rules["max_fail_rate"])
    min_transitions = int(rules["min_transitions"])
    min_runs = int(rules["min_runs_for_flaky"])
    fallback = rules["fallback_label"]

    if len(history) < min_runs or n == 0:
        label = fallback
    elif fail_rate == 1:
        label = _label_name(rules, "broken", "broken")
    elif fail_rate == 0:
        label = _label_name(rules, "stable", "stable")
    elif min_rate <= fail_rate <= max_rate and transitions >= min_transitions:
        label = _label_name(rules, "flaky", "flaky")
    else:
        label = fallback

    return {
        "label": label,
        "counted_runs": n,
        "passes": passes,
        "fails": fails,
        "fail_rate": render(fail_rate),
        "transitions": transitions,
        "flaky_score": render(flaky_score),
    }


def _label_name(rules, key, default):
    """分型名取自规则包的 labels 表；表里没这个键时退回默认名。"""
    labels = rules.get("labels")
    if isinstance(labels, dict) and key in labels:
        return key
    return default


# ── 回归判定 ───────────────────────────────────────────────────────────


def regression(base_p50, curr_p50, slow_rules):
    """``curr/base >= ratio`` **且** ``curr-base >= delta_ms``（边界计入）。

    返回 ``(bool | None, note)``：base 缺失或为 0 -> ``(None, "undefined_base")``
    （不判回归，也不谎报"无回归"）。
    """
    ratio = _frac(slow_rules["regression_ratio"])
    delta = int(slow_rules["regression_delta_ms"])
    if base_p50 is None or curr_p50 is None:
        return None, "missing_window"
    if base_p50 == 0:
        return None, "undefined_base"
    actual_ratio = Fraction(curr_p50) / Fraction(base_p50)
    actual_delta = int(curr_p50) - int(base_p50)
    hit = actual_ratio >= ratio and actual_delta >= delta
    note = "ratio=%s(%s) delta=%dms(%s)" % (
        render(actual_ratio),
        ">=" if actual_ratio >= ratio else "<",
        actual_delta,
        ">=" if actual_delta >= delta else "<",
    )
    return hit, note


# ── 单用例的期望值 ─────────────────────────────────────────────────────


def expected_for_case(case, rules):
    """从**输入侧**（history / timings_ms / split）算出期望侧。"""
    history = case["history"]
    timings = case["timings_ms"]
    split = case.get("regression_split")
    flaky_rules = rules["flaky"]
    slow_rules = rules["slow"]
    p_rules = rules["percentile"]

    profile = compute_profile(history, flaky_rules)
    all_p50 = percentile([t for t in timings if t is not None], p_rules["p50"])
    all_p95 = percentile([t for t in timings if t is not None], p_rules["p95"])

    base_p50 = curr_p50 = None
    reg = None
    note = None
    if isinstance(split, int) and 0 < split < len(timings):
        base_p50 = p50_of(timings[:split])
        curr_p50 = p50_of(timings[split:])
        reg, note = regression(base_p50, curr_p50, slow_rules)
    else:
        note = "no_window"

    return {
        "label": profile["label"],
        "counted_runs": profile["counted_runs"],
        "passes": profile["passes"],
        "fails": profile["fails"],
        "fail_rate": profile["fail_rate"],
        "transitions": profile["transitions"],
        "flaky_score": profile["flaky_score"],
        "p50_ms": render(all_p50),
        "p95_ms": render(all_p95),
        "base_p50_ms": render(base_p50),
        "curr_p50_ms": render(curr_p50),
        "regression": reg,
        "regression_note": note,
    }


#: 期望侧用于对账的字段（顺序即输出顺序；`regression_note` 不进逐值对账——
#: 它是给人看的解释，不是判定结果）
COMPARED_FIELDS = (
    "label",
    "counted_runs",
    "passes",
    "fails",
    "fail_rate",
    "transitions",
    "flaky_score",
    "p50_ms",
    "p95_ms",
    "base_p50_ms",
    "curr_p50_ms",
    "regression",
)


def compare_expected(recorded, derived):
    """逐字段比较两个期望侧；返回问题清单（空 = 一致）。"""
    problems = []
    for field in COMPARED_FIELDS:
        want = recorded.get(field)
        got = derived.get(field)
        if want != got:
            problems.append("%s: 登记 %r != 复算 %r" % (field, want, got))
    return problems


def recompute_totals(cases, rules):
    """对一组用例（输入侧）复算汇总，用于与 `expected_totals` 对账。"""
    label_counts = {name: 0 for name in ("stable", "flaky", "broken", "watch")}
    status_counts = {name: 0 for name in STATUSES}
    transitions_histogram = {}
    reg_true = reg_false = reg_undefined = 0
    cases_with_skip = cases_with_missing = 0
    for case in cases:
        derived = expected_for_case(case, rules)
        label_counts[derived["label"]] = label_counts.get(derived["label"], 0) + 1
        for status in case["history"]:
            status_counts[status] = status_counts.get(status, 0) + 1
        if SKIP in case["history"]:
            cases_with_skip += 1
        if MISSING in case["history"]:
            cases_with_missing += 1
        key = str(derived["transitions"])
        transitions_histogram[key] = transitions_histogram.get(key, 0) + 1
        if derived["regression"] is True:
            reg_true += 1
        elif derived["regression"] is False:
            reg_false += 1
        else:
            reg_undefined += 1
    return {
        "cases": len(cases),
        "label_counts": label_counts,
        "status_counts": status_counts,
        "transitions_histogram": transitions_histogram,
        "regression_true": reg_true,
        "regression_false": reg_false,
        "regression_undefined": reg_undefined,
        "cases_with_skip": cases_with_skip,
        "cases_with_missing": cases_with_missing,
    }


# ── 真值台账自检 ───────────────────────────────────────────────────────


def _find_observed_keys(node, path=""):
    """递归找出名字里含 ``observed`` 的键——真值不得存"已经算好的观测"。"""
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            if "observed" in str(key).lower():
                hits.append("%s.%s" % (path, key) if path else str(key))
            hits.extend(_find_observed_keys(value, "%s.%s" % (path, key)))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            hits.extend(_find_observed_keys(value, "%s[%d]" % (path, idx)))
    return hits


def verify_ledger(ledger):
    """独立复算整份台账的期望侧，返回问题清单（空 = 一致）。

    复算对象：`anchors` + `samples`（这两组带完整输入侧），以及
    `expected_totals`（由 `corpus_cases` 复算）。
    """
    problems = []
    rules = ledger.get("rules_snapshot")
    if not isinstance(rules, dict):
        return ["台账缺 rules_snapshot（参照实现无从取阈值）"]

    observed = _find_observed_keys(ledger)
    if observed:
        problems.append("台账出现 observed 类字段（真值只存输入与期望）：%s" % observed[:5])

    for group in ("anchors", "samples"):
        records = ledger.get(group) or []
        if not records:
            problems.append("%s 为空（判据空转）" % group)
            continue
        for record in records:
            case = record.get("case")
            if not isinstance(case, dict):
                problems.append("%s 记录缺 case（输入侧）：%r" % (group, record.get("anchor")))
                continue
            name = record.get("anchor") or case.get("name", "?")
            derived = expected_for_case(case, rules)
            for item in compare_expected(record.get("expected", {}), derived):
                problems.append("%s[%s] %s" % (group, name, item))

    corpus = ledger.get("corpus_cases")
    if corpus:
        want = ledger.get("expected_totals") or {}
        got = recompute_totals(corpus, rules)
        for key in sorted(want):
            if want[key] != got.get(key):
                problems.append("expected_totals.%s: 登记 %r != 复算 %r" % (key, want[key], got.get(key)))
    # 主辅料本身不入仓（体积），故台账通常不带 corpus_cases。
    # 此时 `expected_totals` 由 `gen_runs.py --check` 覆盖：`--check` 会**重新生成
    # 整个语料并复算汇总**，再与已登记台账逐字节比对——汇总漂移会直接表现为字节差异。
    # 这里不把它判为缺陷，但也不假装验过：`corpus_cases` 缺席时不进逐值对账。

    return problems


def load_ledger(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    """命令行入口：独立复算一份台账并报告。"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="refimpl", description="参照实现：独立复算 expect.json")
    parser.add_argument("ledger", nargs="?", default=None, help="expect.json 路径")
    args = parser.parse_args(argv)

    path = args.ledger
    if path is None:
        import os

        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(os.path.dirname(here), "data", "synth", "expect.json")
    if not __import__("os").path.isfile(path):
        print("FAIL  台账不存在：%s（先跑 py -3.12 data/synth/gen_runs.py）" % path)
        return 2

    ledger = load_ledger(path)
    problems = verify_ledger(ledger)
    for item in problems:
        print("FAIL  " + item)
    print("参照实现复算 %s：%s" % (path, "一致" if not problems else "%d 处不一致" % len(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
