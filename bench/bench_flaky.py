#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准②：flaky 分型 / `flaky_score` 与真值台账、参照实现逐值对账（D5 + D7）。

对应 `plan/04-数据计划.md` §五「基准口径」的两行：

| 基准 | 输入 | 判据 | 门槛 |
| --- | --- | --- | --- |
| `bench_flaky.py` | D5 + D7 | 分型与 `flaky_score` 与 `expect.json` 逐值相等 | 0 差异 |
| 同上（差异点） | 恒失败 fixture | `broken ∩ flaky == ∅` | 硬断言 |

**三条独立通道**（与 `bench_ingest` 的四通道同思路）：

1. **生产实现**（`testdeck.flaky.classify`）——被测对象，阈值取自
   `src/testdeck/rules/flaky.json`；
2. **参照实现**（`bench/refimpl.py:compute_profile`）——与生产零共享代码，
   阈值取自台账的 `rules_snapshot`（**不读**生产规则包）；
3. **真值台账**（`data/synth/expect.json` 的 `anchors` / `samples` 期望侧 + 全语料
   `expected_totals`）——生成期由参照实现算好。

**真值纪律**（`plan/04` §二）：本脚本只读**输入侧**（`case.history`），期望侧只作对账
对象；**不得**把生产实现算出的值写回台账。

`broken ∩ flaky == ∅` 是**独立断言**：拿固定 fixture 的两份集合求交，不靠
`flaky.classify` 内部的分型顺序自证——顺序改了但两个集合仍互斥，这条照样过；
顺序改了且集合相交（例如把恒失败也判成 flaky），这条必红。

用法：

    py -3.12 bench/bench_flaky.py                 # 对账
    py -3.12 bench/bench_flaky.py --probe         # 探活：注入缺陷，断言能被报出
    py -3.12 bench/bench_flaky.py --no-corpus     # 跳过全语料复算（只跑锚点/样本）

退出码：0 达标 / 1 有未达标 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 让本脚本两种跑法都能 import 生产包（与 `bench_ingest.py` 同法）
_SRC = os.path.join(ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from testdeck import flaky, rules  # noqa: E402  （路径先补，再导入）

LEDGER_PATH = os.path.join(ROOT, "data", "synth", "expect.json")

#: 逐值对账的字段（与参照实现的 `COMPARED_FIELDS` 在分型面上取交集；
#: 分位数 / 回归属 M5，不在这里比）
COMPARED_FIELDS = ("label", "counted_runs", "passes", "fails",
                   "fail_rate", "transitions", "flaky_score")


# ── 载入（按路径装载，不 import 生产脚本的模块名）──────────────────────


def _load_script(rel_path, module_name):
    path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_ledger(path=None):
    with open(path or LEDGER_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _history_of(case):
    """台账用例的输入侧 → 生产实现要的 ``[(run_seq, status), ...]``（升序）。"""
    return [(index, status) for index, status in enumerate(case["history"])]


# ── 生产侧分型（唯一被测入口；探活的注入点也在这里）────────────────────


def classify_case(case, ruleset, fault=None):
    """把台账里一条用例的**输入侧**判成分型（返回渲染后的逐值 dict）。

    ``fault`` 是探活注入点：它**打在消费处**——注入的是对账读到的结果，
    不是常量或定义（`plan/04` §五 末段：探活打在消费处）。
    """
    profile = flaky.classify(_history_of(case), ruleset)
    observed = {
        "label": profile.label,
        "counted_runs": profile.counted_runs,
        "passes": profile.passes,
        "fails": profile.fails,
        "fail_rate": profile.fail_rate_text,
        "transitions": profile.transitions,
        "flaky_score": profile.flaky_score_text,
    }
    if fault == "off_by_one":
        # 对账读到的 transitions +1（判定若没在判 transitions，这里不会报差异）
        observed["transitions"] += 1
    elif fault == "force_flaky":
        # 把一切都判成 flaky —— `broken ∩ flaky == ∅` 的独立断言必须报红
        observed["label"] = flaky.LABEL_FLAKY
    return observed


# ── 逐值对账 ───────────────────────────────────────────────────────────


def _diff_fields(recorded, derived):
    problems = []
    for field in COMPARED_FIELDS:
        want = recorded.get(field)
        got = derived.get(field)
        if want != got:
            problems.append("%s: 登记 %r != 实算 %r" % (field, want, got))
    return problems


def reconcile_records(records, ruleset, group_name, fault=None):
    """一组台账记录（带输入侧 + 期望侧）逐值对账；返回 checks 列表。"""
    problems = []
    for record in records:
        name = record.get("anchor") or record["case"]["name"]
        derived = classify_case(record["case"], ruleset, fault=fault)
        for item in _diff_fields(record["expected"], derived):
            problems.append("%s[%s] %s" % (group_name, name, item))
    return {
        "name": "flaky/%s_vs_expected" % group_name,
        "ok": not problems,
        "detail": ("；".join(problems[:5]) + ("…共 %d 处" % len(problems) if len(problems) > 5 else ""))
                  if problems
                  else "%d 条记录 %d 项逐值相等" % (len(records), len(COMPARED_FIELDS)),
    }


def reconcile_against_reference(records, ledger, ruleset, fault=None):
    """生产实现 vs **参照实现**（两套独立代码，阈值来源不同）逐值对账。"""
    refimpl = _load_script(os.path.join("bench", "refimpl.py"), "td_refimpl")
    snapshot = ledger["rules_snapshot"]["flaky"]
    problems = []
    for record in records:
        case = record["case"]
        derived = classify_case(case, ruleset, fault=fault)
        expected = refimpl.compute_profile(case["history"], snapshot)
        for field in COMPARED_FIELDS:
            if derived.get(field) != expected.get(field):
                problems.append("%s %s: 生产 %r != 参照 %r"
                                % (case.get("name"), field, derived.get(field), expected.get(field)))
    return {
        "name": "flaky/production_vs_refimpl",
        "ok": not problems,
        "detail": ("；".join(problems[:5]) if problems
                   else "生产实现与参照实现逐值相等（%d 条记录）" % len(records)),
    }


def reconcile_corpus_totals(ledger, fault=None):
    """重建全语料（D5，按台账声明的参数），生产实现的分型计数 vs `expected_totals`。"""
    gen = _load_script(os.path.join("data", "synth", "gen_runs.py"), "td_gen_runs")
    params = ledger["generator"]["params"]
    seed = ledger["generator"]["seed"]
    corpus = gen.build_corpus(params["runs"], params["cases"], seed)
    ruleset = rules.load_flaky_rules()
    counts = {}
    for case in corpus:
        label = classify_case(case, ruleset, fault=fault)["label"]
        counts[label] = counts.get(label, 0) + 1
    want = ledger["expected_totals"]["label_counts"]
    diffs = []
    for label in sorted(set(want) | set(counts)):
        if want.get(label) != counts.get(label):
            diffs.append("%s: 实算 %s != 登记 %s" % (label, counts.get(label), want.get(label)))
    return {
        "name": "flaky/corpus_label_counts",
        "ok": not diffs,
        "detail": ("；".join(diffs) if diffs
                   else "%d 条用例分型计数逐类相等（%s）"
                        % (len(corpus), ", ".join("%s=%d" % (k, counts[k])
                                                  for k in sorted(counts)))),
        "counts": counts,
    }


# ── 独立断言：broken ∩ flaky == ∅（M4 DoD）────────────────────────────


def broken_flaky_exclusive(records, ruleset, fault=None):
    """拿固定 fixture 的两份集合求交——**不靠分类函数内部顺序自证**。

    两份集合都从**生产实现**的分类结果收集，但判据本身是"两个集合有没有交集"，
    与"分类函数先判哪个分支"无关：顺序改成先判 flaky 也一样能过，除非真的把
    恒失败样本判进了 flaky。
    """
    broken = set()
    flaky_set = set()
    for record in records:
        case = record["case"]
        name = record.get("anchor") or case.get("name")
        label = classify_case(case, ruleset, fault=fault)["label"]
        if label == flaky.LABEL_BROKEN:
            broken.add(name)
        elif label == flaky.LABEL_FLAKY:
            flaky_set.add(name)
    overlap = sorted(broken & flaky_set)
    return {
        "name": "flaky/broken_flaky_exclusive",
        "ok": not overlap and bool(broken) and bool(flaky_set),
        "detail": ("恒失败与抖动两个集合相交：%s" % overlap if overlap
                   else "broken(%d) ∩ flaky(%d) == ∅（两份集合都非空）"
                        % (len(broken), len(flaky_set))),
        "broken": sorted(broken),
        "flaky": sorted(flaky_set),
    }


# ── 两条降级（K34 + 窗口不足）──────────────────────────────────────────


def degradation_checks(ruleset, fault=None):
    """零计数样本落 `watch`（K34）+ 窗口不足一律 `watch`（不得输出 flaky）。"""
    checks = []
    fallback = flaky.fallback_label(ruleset)

    # ① 全 skip/missing（n == 0）：fail_rate 无定义，必须落 watch 而不是 stable
    zero = [(i, status) for i, status in enumerate(["skip", "missing", "skip", "missing"])]
    zero_profile = flaky.classify(zero, ruleset)
    checks.append({
        "name": "flaky/degrade_zero_counted",
        "ok": zero_profile.label == fallback and zero_profile.fail_rate is None,
        "detail": "零计数样本判为 %s（fail_rate=%r；必须 %s 且无定义）"
                  % (zero_profile.label, zero_profile.fail_rate, fallback),
    })

    # ② 全 pass 但只有 1 次参与计数：n < min_runs_for_flaky -> watch（不得判 stable）
    min_runs = int(ruleset["min_runs_for_flaky"])
    short = [(0, "pass")] * (min_runs - 1)
    short_profile = flaky.classify(short, ruleset)
    checks.append({
        "name": "flaky/degrade_short_window",
        "ok": short_profile.label == fallback,
        "detail": "窗口 %d 次（< min_runs_for_flaky=%d）判为 %s（必须 %s，不得输出 flaky）"
                  % (len(short), min_runs, short_profile.label, fallback),
    })
    return checks


# ── 套件入口 ───────────────────────────────────────────────────────────


def run(corpus=True, fault=None, ledger_path=None):
    """跑完整 flaky 基准，返回结构化结果（供 `bench/run_all.py` 消费）。"""
    ledger = load_ledger(ledger_path)
    ruleset = rules.load_flaky_rules()
    anchors = ledger["anchors"]
    samples = ledger["samples"]
    records = anchors + samples

    checks = [
        reconcile_records(anchors, ruleset, "anchors", fault=fault),
        reconcile_records(samples, ruleset, "samples", fault=fault),
        reconcile_against_reference(records, ledger, ruleset, fault=fault),
        broken_flaky_exclusive(records, ruleset, fault=fault),
    ]
    checks.extend(degradation_checks(ruleset, fault=fault))
    if corpus:
        checks.append(reconcile_corpus_totals(ledger, fault=fault))

    failed = [c for c in checks if not c["ok"]]
    return {
        "suite": "flaky",
        "enabled": True,
        "ok": not failed,
        "checks": checks,
        "notes": [],
    }


def _print_result(result):
    print("== 基准 %s ==" % result["suite"])
    for check in result["checks"]:
        print("%s  %-42s %s" % ("PASS" if check["ok"] else "FAIL", check["name"], check["detail"]))
    failed = [c for c in result["checks"] if not c["ok"]]
    print("结果：%s（%d 项检查，%d 项未达标）"
          % ("达标" if not failed else "未达标", len(result["checks"]), len(failed)))


def _probe(args):
    """探活：注入缺陷，断言判定能报出差异（探活打在**消费处**）。"""
    print("== 探活（--probe）：注入缺陷，断言判定能报出差异 ==")
    problems = []
    scenarios = (
        ("off_by_one", "对账读到的 transitions +1"),
        ("force_flaky", "把一切判成 flaky（两集合应相交）"),
    )
    for fault, desc in scenarios:
        result = run(corpus=False, fault=fault, ledger_path=getattr(args, "ledger", None))
        failed = [c for c in result["checks"] if not c["ok"]]
        if failed:
            print("PASS  注入[%s]（%s）-> 判定报出未达标：%s"
                  % (fault, desc, ", ".join(c["name"] for c in failed[:3])))
        else:
            print("FAIL  注入[%s]（%s）-> 判定**没有**报出任何差异（探活失效）" % (fault, desc))
            problems.append(fault)
    print("=" * 60)
    print("探活结论：%s" % ("全部能被检出" if not problems else "未检出：%s" % ",".join(problems)))
    return 0 if not problems else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_flaky", description="flaky 分型逐值对账")
    parser.add_argument("--probe", action="store_true", help="探活：注入缺陷并断言能被报出")
    parser.add_argument("--no-corpus", dest="corpus", action="store_false", default=True,
                        help="跳过全语料复算（只跑锚点/样本）")
    parser.add_argument("--ledger", default=None, help="覆盖真值台账路径")
    args = parser.parse_args(argv)

    if args.probe:
        return _probe(args)
    result = run(corpus=args.corpus, ledger_path=args.ledger)
    _print_result(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
