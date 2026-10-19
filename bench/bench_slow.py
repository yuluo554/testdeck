#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准③：p50/p95 与回归判定对账（`plan/04` §五「基准口径」）。

对应 `plan/04-数据计划.md` §五 的一行：

| 基准 | 输入 | 判据 | 门槛 |
| --- | --- | --- | --- |
| `bench_slow.py` | D5 + D7 | p50/p95 与参照实现逐值相等；回归边界六种 | 0 差异 |

**三条独立通道**（与 `bench_flaky.py` 同思路）：

1. **生产实现**（`testdeck.slow`）——被测对象，阈值取自 `src/testdeck/rules/slow.json`；
2. **参照实现**（`bench/refimpl.py:expected_for_case`）——与生产零共享代码，
   阈值取自台账的 `rules_snapshot`（**不读**生产规则包）；
3. **真值台账**（`data/synth/expect.json` 的 `anchors` / `samples` 期望侧）——
   生成期由参照实现算好。

**两条硬断言**（`plan/03` 模块④ 的降级条）：

- **缺失耗时不进样本、不补 0**：拿"补 0"的对照实现复算，结论必须不同（否则这条口径
  在本基准里不可证伪）；
- **回归不可判返回 `None` 而不是 `False`**：`undefined_base` / `missing_window` 两种
  都不得被算成"无回归"。

用法：

    py -3.12 bench/bench_slow.py                 # 对账
    py -3.12 bench/bench_slow.py --probe         # 探活：注入缺陷，断言能被报出
    py -3.12 bench/bench_slow.py --no-corpus     # 跳过全语料复算（只跑锚点/样本）

退出码：0 达标 / 1 有未达标 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 让本脚本两种跑法都能 import 生产包（与 `bench_flaky.py` 同法）
_SRC = os.path.join(ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from testdeck import model, rules, slow  # noqa: E402  （路径先补，再导入）

LEDGER_PATH = os.path.join(ROOT, "data", "synth", "expect.json")

#: 逐值对账的字段（与参照实现 `COMPARED_FIELDS` 在分位数/回归面上取交集）
COMPARED_FIELDS = ("p50_ms", "p95_ms", "base_p50_ms", "curr_p50_ms", "regression")


def _load_script(rel_path, module_name):
    path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_ledger(path=None):
    with open(path or LEDGER_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _split_of(case):
    """台账用例的切分点（**输入侧**给出，引擎不得自行发明）。

    非法的 `regression_split`（缺、0、越界）一律映射成 ``0``——于是前段样本为空、
    回归判定落 `missing_window`，与参照实现的 `no_window` 同结论。
    """
    split = case.get("regression_split")
    if isinstance(split, int) and not isinstance(split, bool) \
            and 0 < split < len(case["timings_ms"]):
        return split
    return None


# ── 生产侧（唯一被测入口；探活的注入点也在这里）───────────────────────


def classify_case(case, ruleset, fault=None):
    """把台账里一条用例的**输入侧**判成慢测试画像（返回渲染后的逐值 dict）。

    ``fault`` 是探活注入点：它**打在消费处**——注入的是对账读到的结果。
    """
    profile = slow.profile_case(
        0, "s", "C", case.get("name", "?"), None, case["timings_ms"],
        _split_of(case), ruleset,
    )
    observed = {
        "p50_ms": profile.p50_text,
        "p95_ms": profile.p95_text,
        "base_p50_ms": model.render_exact(profile.base_p50),
        "curr_p50_ms": model.render_exact(profile.curr_p50),
        "regression": profile.regression,
    }
    if fault == "off_by_one":
        # 对账读到的 p50 数值 +1（判定若没在判分位数，这里不会报差异）
        p50 = profile.p50 if profile.p50 is not None else Fraction(0)
        observed["p50_ms"] = model.render_exact(p50 + 1)
    elif fault == "force_regression":
        # 把一切判成回归 —— 回归边界对账必须报红
        observed["regression"] = True
    return observed


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
        name = record.get("anchor") or record["case"].get("name")
        derived = classify_case(record["case"], ruleset, fault=fault)
        for item in _diff_fields(record["expected"], derived):
            problems.append("%s[%s] %s" % (group_name, name, item))
    return {
        "name": "slow/%s_vs_expected" % group_name,
        "ok": not problems,
        "detail": ("；".join(problems[:5]) + ("…共 %d 处" % len(problems) if len(problems) > 5 else ""))
                  if problems
                  else "%d 条记录 %d 项逐值相等" % (len(records), len(COMPARED_FIELDS)),
    }


def reconcile_against_reference(records, ledger, ruleset, fault=None):
    """生产实现 vs **参照实现**（两套独立代码，阈值来源不同）逐值对账。"""
    refimpl = _load_script(os.path.join("bench", "refimpl.py"), "td_refimpl")
    snapshot = ledger["rules_snapshot"]
    problems = []
    for record in records:
        case = record["case"]
        derived = classify_case(case, ruleset, fault=fault)
        expected = refimpl.expected_for_case(case, snapshot)
        for field in COMPARED_FIELDS:
            if derived.get(field) != expected.get(field):
                problems.append("%s %s: 生产 %r != 参照 %r"
                                % (case.get("name"), field, derived.get(field), expected.get(field)))
    return {
        "name": "slow/production_vs_refimpl",
        "ok": not problems,
        "detail": ("；".join(problems[:5]) if problems
                   else "生产实现与参照实现逐值相等（%d 条记录）" % len(records)),
    }


# ── 回归边界六种（DoD：恰好 / 略低 / 略高）────────────────────────────


BOUNDARY_ANCHORS = {
    "reg_ratio_exact_delta_exact": True,
    "reg_ratio_exact_delta_below": False,
    "reg_ratio_below": False,
    "reg_ratio_above": True,
    "reg_delta_exact_ratio_above": True,
    "reg_delta_below": False,
    "reg_delta_above": True,
    "reg_undefined_base": None,
}


def regression_boundaries(records, ruleset, fault=None):
    """六种回归边界（`ratio` 恰好/略低/略高、`delta` 恰好/略低/略高）逐项断言。

    **两边都要有**：既有判成回归的（能检出），也有判成非回归的（不误报），
    还有判不了的（`None`）——三者都在，判据才不是恒真/恒假。
    """
    by_anchor = {}
    for record in records:
        anchor = record.get("anchor")
        if anchor in BOUNDARY_ANCHORS:
            by_anchor[anchor] = classify_case(record["case"], ruleset, fault=fault)["regression"]
    problems = []
    for anchor, want in BOUNDARY_ANCHORS.items():
        if anchor not in by_anchor:
            problems.append("缺边界锚点 %s" % anchor)
            continue
        got = by_anchor[anchor]
        if got is not want:
            problems.append("%s：期望 %r，实算 %r" % (anchor, want, got))
    seen = set(by_anchor.values())
    if True not in seen:
        problems.append("没有任何边界判成回归（判据可能恒假）")
    if False not in seen:
        problems.append("没有任何边界判成非回归（判据可能恒真）")
    if None not in seen:
        problems.append("没有任何边界判成「不可判」（undefined_base 未覆盖）")
    return {
        "name": "slow/regression_boundaries",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "%d 个边界锚点逐项相符（True/False/None 三态齐全）" % len(by_anchor),
    }


# ── 两条硬断言：缺失耗时 / 不可判 ─────────────────────────────────────


def missing_time_and_undefined_checks(ruleset, fault=None):
    """缺失耗时**不补 0**；不可判返回 `None` 而不是 `False`（两条都是口径，不是"顺手算"）。"""
    checks = []

    # ① 缺失耗时：把 None 当 0 会给出不同的 p50（这条口径在本基准里可证伪）
    with_missing = slow.p50([100, 200, None], ruleset)
    with_zero = slow.p50([100, 200, 0], ruleset)
    checks.append({
        "name": "slow/missing_time_not_zero",
        "ok": with_missing is not None and with_missing != with_zero,
        "detail": "缺失耗时 p50=%s != 补 0 的 p50=%s（缺失不进样本）"
                  % (model.render_exact(with_missing), model.render_exact(with_zero)),
    })

    # ② 不可判：undefined_base / missing_window 都返回 None，不是 False
    undefined_hit, undefined_note = slow.regression(0, 500, ruleset)
    missing_hit, missing_note = slow.regression(None, 500, ruleset)
    checks.append({
        "name": "slow/undefined_is_none_not_false",
        "ok": (undefined_hit is None and undefined_note == slow.NOTE_UNDEFINED_BASE
               and missing_hit is None and missing_note == slow.NOTE_MISSING_WINDOW),
        "detail": "base==0 -> (%r,%s)；缺样本 -> (%r,%s)（都必须是 None，不谎报「无回归」）"
                  % (undefined_hit, undefined_note, missing_hit, missing_note),
    })

    # ③ 瀑布条整数运算：`.5` 边界向上取整（不是银行家舍入）
    checks.append({
        "name": "slow/bar_width_half_up",
        "ok": slow.bar_width(1, 2, 1) == 1 and slow.bar_width(1000, 0, 40) == 0,
        "detail": "bar_width(1,2,1)=%d（四舍五入为 1）；max=0 时全宽 0（不除零）"
                  % slow.bar_width(1, 2, 1),
    })
    return checks


# ── 全语料复算 ────────────────────────────────────────────────────────


def reconcile_corpus_totals(ledger, fault=None):
    """重建全语料（D5，按台账声明的参数），生产的回归三态计数 vs `expected_totals`。"""
    gen = _load_script(os.path.join("data", "synth", "gen_runs.py"), "td_gen_runs")
    params = ledger["generator"]["params"]
    seed = ledger["generator"]["seed"]
    corpus = gen.build_corpus(params["runs"], params["cases"], seed)
    ruleset = rules.load_slow_rules()
    hit_true = hit_false = undefined = 0
    for case in corpus:
        verdict = classify_case(case, ruleset, fault=fault)["regression"]
        if verdict is True:
            hit_true += 1
        elif verdict is False:
            hit_false += 1
        else:
            undefined += 1
    want = ledger["expected_totals"]
    diffs = []
    for label, got, key in (("真回归", hit_true, "regression_true"),
                            ("非回归", hit_false, "regression_false"),
                            ("不可判", undefined, "regression_undefined")):
        if want.get(key) != got:
            diffs.append("%s: 实算 %s != 登记 %s" % (label, got, want.get(key)))
    return {
        "name": "slow/corpus_regression_counts",
        "ok": not diffs,
        "detail": ("；".join(diffs) if diffs
                   else "%d 条用例回归三态计数逐项相等（true=%d false=%d undefined=%d）"
                        % (len(corpus), hit_true, hit_false, undefined)),
    }


# ── 套件入口 ───────────────────────────────────────────────────────────


def run(corpus=True, fault=None, ledger_path=None):
    """跑完整 slow 基准，返回结构化结果（供 `bench/run_all.py` 消费）。"""
    ledger = load_ledger(ledger_path)
    ruleset = rules.load_slow_rules()
    anchors = ledger["anchors"]
    samples = ledger["samples"]
    records = anchors + samples

    checks = [
        reconcile_records(anchors, ruleset, "anchors", fault=fault),
        reconcile_records(samples, ruleset, "samples", fault=fault),
        reconcile_against_reference(records, ledger, ruleset, fault=fault),
        regression_boundaries(records, ruleset, fault=fault),
    ]
    checks.extend(missing_time_and_undefined_checks(ruleset, fault=fault))
    if corpus:
        checks.append(reconcile_corpus_totals(ledger, fault=fault))

    failed = [c for c in checks if not c["ok"]]
    return {
        "suite": "slow",
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
        ("off_by_one", "对账读到的 p50 +1"),
        ("force_regression", "把一切判成回归（边界对账应报红）"),
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
    parser = argparse.ArgumentParser(prog="bench_slow", description="p50/p95 与回归判定对账")
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
