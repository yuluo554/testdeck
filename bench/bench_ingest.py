#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准①：三框架产物逐项对账 + 大文件 `iterparse` 计时。

对应 `plan/04-数据计划.md` §五「基准口径」的第一、二行：

| 基准 | 输入 | 判据 | 门槛 |
| ingest | D1–D3 真实产物 | 用例数 / 失败数 / skipped 与各框架自身汇总**逐项相等** | 0 差异 |
| 同上（性能） | D6 单文件 5 万用例 | `iterparse` 解析耗时 | < 2s |

**M2 起本脚本消费生产解析器**（`src/testdeck/junit.py`）：`plan/04` §五 写明 M1 是
"数据先行"，本文件里自带的 `parse_junit_stream` 只是**基准侧**的临时实现；生产解析器
落地后，两边**互为对照**。所以这里保留两条**独立实现**的计数通道：

1. **生产解析器**（`testdeck.junit.parse_file`）——被测对象，也是第一判据的来源；
2. **基准侧 `iterparse` 重数**（本文件的 `parse_junit_stream`）——与生产实现零共享代码，
   用来抓"生产解析器自己算错了还自我一致"的情形（`parser_vs_recount` 检查）；
3. **框架在 XML 属性里的声明值**（`testsuites@tests` 等；未声明的字段记 `null`）；
4. **各 fixture 的 `expected.json`**：由 `bench/fixtures/regen_fixtures.py` 真跑产出。

四通道逐项比较，任一不等即报差异（0 差异才算达标）。性能门也计时**生产解析器**
（基准量的是被测对象，不是基准自己的实现）。

用法：

    py -3.12 bench/bench_ingest.py                 # 对账 + 性能
    py -3.12 bench/bench_ingest.py --no-perf-gate  # 只对账（CI 用：性能只报告不判红）
    py -3.12 bench/bench_ingest.py --probe         # 探活：注入缺陷，断言能被报出

退出码：0 达标 / 1 有未达标 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 让本脚本两种跑法都能 import 生产包（`py -3.12 bench/bench_ingest.py` 没有
#: pytest 的 `pythonpath=["src"]`；CI 里 `pip install -e .` 之后其实已可导入）
_SRC = os.path.join(ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from testdeck import junit  # noqa: E402  （路径先补，再导入）

FIXTURES_DIR = os.path.join(HERE, "fixtures")
#: 反向发现的三框架 fixture（目录名 → 说明）
FRAMEWORKS = ("pytest", "gotestsum", "playwright")
#: D6 大文件语料路径（不入仓；缺失时按需生成）
BIG_XML_DEFAULT = os.path.join(ROOT, "data", "synth", "big.xml")

COUNT_FIELDS = ("tests", "failures", "errors", "skipped")

#: 性能门槛（plan/04 §五：本机实测 < 2s；CI 只报告不判红）
PERF_LIMIT_SECONDS = 2.0
PERF_BIG_CASES = 50000
#: 计时重复次数，取最小值以抵消偶发抖动
PERF_REPEAT = 3


# ── 基准侧独立重数（与生产实现零共享代码，用于互为对照）──────────────────


def parse_junit_stream(path):
    """`iterparse` 流式计数：返回 ``(totals, suites)``。

    内存纪律：`testcase` 与 `testsuite` 的 `end` 事件处都 `clear()`，
    保证 5 万用例（乃至 50MB 级）文件不会把整树留在内存里。
    """
    totals = dict.fromkeys(COUNT_FIELDS, 0)
    suites = []
    current = None
    for event, elem in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            if elem.tag == "testsuite":
                current = dict.fromkeys(COUNT_FIELDS, 0)
                current["name"] = elem.get("name") or ""
            continue
        if elem.tag == "testcase":
            totals["tests"] += 1
            if current is not None:
                current["tests"] += 1
            kind = None
            for child in elem:
                if child.tag in ("failure", "error", "skipped"):
                    kind = child.tag
                    break
            if kind == "failure":
                totals["failures"] += 1
                if current is not None:
                    current["failures"] += 1
            elif kind == "error":
                totals["errors"] += 1
                if current is not None:
                    current["errors"] += 1
            elif kind == "skipped":
                totals["skipped"] += 1
                if current is not None:
                    current["skipped"] += 1
            elem.clear()
        elif elem.tag == "testsuite":
            if current is not None:
                suites.append(current)
            current = None
            elem.clear()
    return totals, suites


def declared_in_xml(path):
    """读框架**自己声明**的计数（未声明的字段为 ``None``）。"""
    root = ET.parse(path).getroot()
    if root.tag == "testsuites" and any(root.get(f) is not None for f in COUNT_FIELDS):
        elem = root
    else:
        elem = root if root.tag == "testsuite" else root.find("testsuite")
    if elem is None:
        return dict.fromkeys(COUNT_FIELDS)
    out = {}
    for field in COUNT_FIELDS:
        raw = elem.get(field)
        out[field] = None if raw in (None, "") else int(raw)
    return out


# ── 逐项对账 ───────────────────────────────────────────────────────────


def _fixture_xml(framework):
    directory = os.path.join(FIXTURES_DIR, framework)
    hits = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".xml"):
            hits.append(os.path.join(directory, name))
    return hits


def reconcile_fixture(framework, fault=None):
    """把一个 fixture 的四条通道逐项对账，返回 checks 列表。"""
    checks = []
    xmls = _fixture_xml(framework)
    if len(xmls) != 1:
        return [{
            "name": "fixture/%s/artifact" % framework,
            "ok": False,
            "detail": "应恰好 1 个 XML 产物，实际 %d 个：%s" % (len(xmls), xmls),
        }]
    xml_path = xmls[0]
    expected_path = os.path.join(FIXTURES_DIR, framework, "expected.json")
    if not os.path.isfile(expected_path):
        return [{
            "name": "fixture/%s/expected.json" % framework,
            "ok": False,
            "detail": "缺 expected.json（真值台账）",
        }]
    with open(expected_path, "r", encoding="utf-8") as fh:
        expected = json.load(fh)

    # ① 生产解析器（被测对象）
    outcome = junit.parse_file(xml_path, xml_path)
    observed = outcome.totals
    observed_suites = [
        {"name": suite.name, **{f: getattr(suite, f) for f in COUNT_FIELDS}}
        for suite in outcome.suites
    ]
    # ② 基准侧独立重数（不同实现，用来抓"生产实现自洽但算错"）
    recount, recount_suites = parse_junit_stream(xml_path)
    # ③ 框架在 XML 属性里的声明值
    declared = declared_in_xml(xml_path)

    checks.append({
        "name": "fixture/%s/parsed" % framework,
        "ok": outcome.ok,
        "detail": ("生产解析器落库口径 framework=%s，%s" % (outcome.framework, _fmt(observed))
                   if outcome.ok else "生产解析器跳过该文件：reason=%s" % outcome.reason),
    })

    if fault == "off_by_one":
        # 探活注入点：**消费处**——对账读到的观测值。改动定义处（解析器）也能过，
        # 但那就不是在验证"对账真的在看结果"。
        observed = dict(observed)
        observed["tests"] += 1

    # ① 生产解析器 vs 基准侧重数（互为对照：两份独立实现必须给同一个答案）
    diffs = []
    for field in COUNT_FIELDS:
        if recount[field] != observed[field]:
            diffs.append("%s: 生产 %s != 基准侧重数 %s" % (field, observed[field], recount[field]))
    if len(recount_suites) != len(observed_suites):
        diffs.append("suite 数：生产 %d != 基准侧重数 %d"
                     % (len(observed_suites), len(recount_suites)))
    else:
        for idx, (prod, rec) in enumerate(zip(observed_suites, recount_suites)):
            if (prod["name"] or "") != (rec["name"] or ""):
                diffs.append("suite[%d].name：生产 %r != 基准侧 %r"
                             % (idx, prod["name"], rec["name"]))
            for field in COUNT_FIELDS:
                if prod[field] != rec[field]:
                    diffs.append("suite[%d].%s：生产 %s != 基准侧 %s"
                                 % (idx, field, prod[field], rec[field]))
    checks.append({
        "name": "fixture/%s/parser_vs_recount" % framework,
        "ok": not diffs,
        "detail": "；".join(diffs) if diffs
                  else "生产解析器与基准侧重数逐项相等（%d 个 suite）" % len(recount_suites),
    })

    # ② 生产解析器 vs expected.json.totals（逐项）
    diffs = []
    for field in COUNT_FIELDS:
        want = expected.get("totals", {}).get(field)
        got = observed[field]
        if want != got:
            diffs.append("%s: 生产解析器 %s != expected %s" % (field, got, want))
    checks.append({
        "name": "fixture/%s/elements_vs_expected" % framework,
        "ok": not diffs,
        "detail": "；".join(diffs) if diffs else "4 项逐项相等 %s" % _fmt(observed),
    })

    # ③ 框架在 XML 里的声明值 vs expected.json.totals（只比"声明过"的字段）
    diffs = []
    for field in COUNT_FIELDS:
        declared_value = declared.get(field)
        want = expected.get("totals", {}).get(field)
        if declared_value is None:
            # 框架没声明这一项：这不等于"声明为 0"，如实记录而不当成差异
            if expected.get("declared_in_xml", {}).get(field) is not None:
                diffs.append("%s: expected 说框架声明过，XML 里却没有" % field)
            continue
        if declared_value != want:
            diffs.append("%s: XML 声明 %s != expected %s" % (field, declared_value, want))
    undeclared = [f for f in COUNT_FIELDS if declared.get(f) is None]
    checks.append({
        "name": "fixture/%s/xml_declared_vs_expected" % framework,
        "ok": not diffs,
        "detail": ("；".join(diffs) if diffs
                   else "声明值逐项相符（未声明：%s）" % (",".join(undeclared) or "无")),
    })

    # ④ 各 suite 明细：生产解析器 vs expected.json.suites（逐项）
    diffs = []
    want_suites = expected.get("suites") or []
    if len(want_suites) != len(observed_suites):
        diffs.append("suite 数 %d != expected %d" % (len(observed_suites), len(want_suites)))
    for idx, want in enumerate(want_suites):
        if idx >= len(observed_suites):
            break
        got = observed_suites[idx]
        for field in COUNT_FIELDS:
            if want.get(field) != got.get(field):
                diffs.append("suite[%d].%s: %s != %s" % (idx, field, got.get(field), want.get(field)))
        if (want.get("name") or "") not in ("", got.get("name") or ""):
            diffs.append("suite[%d].name: %r != %r" % (idx, got.get("name"), want.get("name")))
    checks.append({
        "name": "fixture/%s/suites_vs_expected" % framework,
        "ok": not diffs,
        "detail": "；".join(diffs) if diffs else "%d 个 suite 逐项相等" % len(observed_suites),
    })

    # ⑤ 框架识别（生产实现）vs expected.json.framework
    want_framework = expected.get("framework")
    checks.append({
        "name": "fixture/%s/framework_detected" % framework,
        "ok": outcome.framework == want_framework,
        "detail": "识别为 %s（期望 %s）" % (outcome.framework, want_framework),
    })
    return checks


def _fmt(counts):
    return " ".join("%s=%s" % (f, counts[f]) for f in COUNT_FIELDS)


def _display(path):
    """尽量显示仓库内相对路径，供人读。

    ``os.path.relpath`` 在 Windows **跨盘符**时会抛 ``ValueError``
    （实测：仓库在 ``D:``、临时语料在 ``C:``）——这是 `paths.relative_to_root`
    已经记录过的同一个坑，不能让它在这里变成崩溃。
    """
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


# ── 性能门（D6）────────────────────────────────────────────────────────


def _ensure_big_xml(path, cases):
    """大文件语料不入仓；缺失时按同一生成器按需生成。"""
    if os.path.isfile(path):
        return False
    spec = importlib.util.spec_from_file_location(
        "testdeck_gen_runs", os.path.join(ROOT, "data", "synth", "gen_runs.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.write_big_xml(path, cases)
    return True


def perf_check(big_file, perf_gate=True, fault=None):
    """对 5 万用例单文件计时**生产解析器**的 `iterparse` 解析。"""
    limit = PERF_LIMIT_SECONDS
    if fault == "perf_impossible":
        # 探活注入点：把门槛压到 0，任何真实耗时都不可能通过——
        # 若这样还能"达标"，说明性能判定根本没在判。
        limit = 0.0
    best = None
    cases = 0
    for _ in range(PERF_REPEAT):
        started = time.perf_counter()
        outcome = junit.parse_file(big_file, big_file)
        elapsed = time.perf_counter() - started
        best = elapsed if best is None else min(best, elapsed)
        cases = outcome.totals["tests"]
    ok = (best < limit) if perf_gate else True
    detail = "iterparse %d 用例：%.3fs（门槛 %ss%s）"
    detail = detail % (cases, best, limit,
                       "，取 %d 次最小值" % PERF_REPEAT if PERF_REPEAT > 1 else "")
    return {
        "name": "perf/iterparse_big_file",
        "ok": ok,
        "detail": detail,
        "elapsed_seconds": best,
        "cases": cases,
        "limit_seconds": limit,
    }


# ── 套件入口 ───────────────────────────────────────────────────────────


def run(perf_gate=True, big_cases=PERF_BIG_CASES, big_file=None, fault=None):
    """跑完整 ingest 基准，返回结构化结果（供 `bench/run_all.py` 消费）。"""
    checks = []
    notes = []
    for framework in FRAMEWORKS:
        checks.extend(reconcile_fixture(framework, fault=fault))

    big_path = big_file or BIG_XML_DEFAULT
    try:
        generated = _ensure_big_xml(big_path, big_cases)
    except Exception as exc:  # noqa: BLE001 - 生成失败不是"通过"
        checks.append({
            "name": "perf/iterparse_big_file",
            "ok": False,
            "detail": "大文件语料无法就绪：%s: %s" % (type(exc).__name__, exc),
        })
    else:
        if generated:
            notes.append("大文件语料本次按需生成：%s" % _display(big_path))
        checks.append(perf_check(big_path, perf_gate=perf_gate, fault=fault))
        if not perf_gate:
            notes.append("性能门已按 --no-perf-gate 关闭（只报告数值，不判红）")

    failed = [c for c in checks if not c["ok"]]
    return {
        "suite": "ingest",
        "enabled": True,
        "ok": not failed,
        "checks": checks,
        "notes": notes,
    }


def _print_result(result):
    print("== 基准 %s ==" % result["suite"])
    for check in result["checks"]:
        print("%s  %-42s %s" % ("PASS" if check["ok"] else "FAIL", check["name"], check["detail"]))
    for note in result["notes"]:
        print("NOTE  %s" % note)
    failed = [c for c in result["checks"] if not c["ok"]]
    print("结果：%s（%d 项检查，%d 项未达标）"
          % ("达标" if not failed else "未达标", len(result["checks"]), len(failed)))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_ingest", description="三框架产物对账 + 性能")
    parser.add_argument("--probe", action="store_true", help="探活：注入缺陷并断言能被报出")
    parser.add_argument("--no-perf-gate", dest="perf_gate", action="store_false", default=True,
                        help="性能只报告不判红（CI 用）")
    parser.add_argument("--big-file", default=None, help="覆盖 D6 大文件路径")
    parser.add_argument("--big-cases", type=int, default=PERF_BIG_CASES)
    args = parser.parse_args(argv)

    if args.probe:
        return _probe(args)
    result = run(perf_gate=args.perf_gate, big_cases=args.big_cases, big_file=args.big_file)
    _print_result(result)
    return 0 if result["ok"] else 1


def _probe(args):
    """探活：从实算值派生注入值，重跑**同一套** check，断言它报出差异。

    "探活打在消费处"——注入的是对账读取的结果，不是定义/常量。
    若注入后依然全绿，说明这套 check 是装饰品。
    """
    print("== 探活（--probe）：注入缺陷，断言判定能报出差异 ==")
    problems = []
    scenarios = (
        ("off_by_one", "对账读到的用例数 +1", {}),
        ("perf_impossible", "性能门槛压到 0s", {"perf_gate": True}),
    )
    for fault, desc, kwargs in scenarios:
        result = run(perf_gate=kwargs.get("perf_gate", args.perf_gate),
                     big_cases=args.big_cases, big_file=args.big_file, fault=fault)
        failed = [c for c in result["checks"] if not c["ok"]]
        if failed:
            print("PASS  注入[%s]（%s）-> 判定报出未达标：%s"
                  % (fault, desc, failed[0]["name"]))
        else:
            print("FAIL  注入[%s]（%s）-> 判定**没有**报出任何差异（探活失效）" % (fault, desc))
            problems.append(fault)
    print("=" * 60)
    print("探活结论：%s" % ("全部能被检出" if not problems else "未检出：%s" % ",".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
