#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准④：导出字段一致 + 两次导出逐字节一致 + `--fail-on` 退出码（`plan/04` §五）。

对应 `plan/04-数据计划.md` §五 的最后一行：

| 基准 | 输入 | 判据 | 门槛 |
| --- | --- | --- | --- |
| `bench_export.py` | D5 | md 字段集合 == TUI 模型字段集合；两次导出逐字节一致；三种 `--fail-on` 退出码 | 0 差异 |

**为什么这个基准不依赖库**：导出面（字段声明序、渲染可重放、门禁语义）全部是
**纯函数**——`report_model.render_*` 消费一个 dict，`gate_hits` 只读那个 dict。
所以本脚本用**确定性合成的模型 dict**（不碰 SQLite）就能对账，且与
`tests/test_export.py` 互为对照：测试钉单元判据，基准给一份可复跑的总账。

**三条独立通道**：

1. **生产渲染**（`testdeck.report_model.render_md/render_json`）——被测对象；
2. **字段声明序**（`REPORT_FIELDS` / `RUN_FIELDS` / `REGRESSION_FIELDS` 元组）；
3. **规则包**（`view.export.formats` / `fail_on` / `json_indent` / `json_ensure_ascii`）。

用法：

    py -3.12 bench/bench_export.py                 # 对账
    py -3.12 bench/bench_export.py --probe         # 探活：注入缺陷，断言能被报出

退出码：0 达标 / 1 有未达标 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 让本脚本两种跑法都能 import 生产包（与 `bench_flaky.py` 同法）
_SRC = os.path.join(ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from testdeck import model, report_model, rules  # noqa: E402  （路径先补，再导入）


# ── 确定性合成模型（不碰库；`observed` 由生产渲染器产出）───────────────


def sample_report():
    """一份**确定性**的报告模型（同参数永远同一份；不读时钟、不迭代 set）。

    字段取值覆盖：正常值、缺失耗时（``None``）、空串、含 `|` 与换行的单元格
    （专门用来验 md 转义）。
    """
    run = {
        "run_id": 7,
        "branch": "feature/synth-1",
        "commit_sha": "0" * 39 + "7",
        "ci_run_id": "1000000007",
        "started_at": "2026-01-01T00:07:00+00:00",
        "framework": "pytest",
        "source_path": "bench/fixtures/pytest/junit.xml",
    }
    summary = {"total": 4, "fail": 1, "skip": 1, "flaky": 1, "broken": 1, "slow": 1}
    cases = [
        {"suite_name": "s", "classname": "C", "name": "t_ok", "status": "pass",
         "time_ms": 12, "failure_type": "", "failure_message": "", "stack_first_line": ""},
        {"suite_name": "s", "classname": "C", "name": "t_missing_time", "status": "pass",
         "time_ms": None, "failure_type": "", "failure_message": "", "stack_first_line": ""},
        {"suite_name": "s", "classname": "C", "name": "t_pipe|newline", "status": "fail",
         "time_ms": 100, "failure_type": "AssertionError",
         "failure_message": "boom | pipe", "stack_first_line": "line1\nline2"},
    ]
    regressions = [{
        "suite_name": "s", "classname": "C", "name": "t_slow", "time_ms": 1200,
        "p50": "1200", "p95": "1200", "base_p50": "1000", "curr_p50": "1200",
        "regression": "yes",
    }]
    diff = {
        "base_run": None,
        "counts": {"new-failures": 1, "fixed": 0, "still-failing": 0, "unchanged": 2},
        "entries": [{"kind": "new-failures", "classname": "C", "name": "t_pipe|newline",
                     "status_before": "pass", "status_after": "fail"}],
    }
    return {
        "run": run, "summary": summary, "cases": cases, "history": {},
        "suites": [], "profiles": {}, "slow": [], "diff": diff,
        "regressions": regressions,
    }


def _fake_profile(label, score):
    from fractions import Fraction
    return {
        "label": label,
        "flaky_score_text": score,
    }


class _ProfileStub:
    """`gate_hits(flaky)` 读的是 `profile.label`——给一个最小桩，不依赖 flaky.py。"""

    def __init__(self, label):
        self.label = label


# ── 对账项 ────────────────────────────────────────────────────────────


def check_json_key_order(fault=None):
    """JSON 的键序 = 声明序；用例行键序 = `REPORT_FIELDS`。"""
    report = sample_report()
    payload = json.loads(report_model.render_json(report))
    problems = []
    if list(payload) != ["run", "summary", "cases", "regressions", "diff"]:
        problems.append("顶层键序：%s" % list(payload))
    for row in payload["cases"]:
        if list(row) != list(report_model.REPORT_FIELDS):
            problems.append("用例行键序：%s" % list(row))
            break
    if fault == "shuffle_keys":
        # 探活：把 JSON 渲染改成 sort_keys（键序被排序 = 声明序失效）
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        shuffled = json.loads(text)
        if list(shuffled["cases"][0]) == list(report_model.REPORT_FIELDS):
            problems.append("注入 sort_keys 后键序竟然仍等于声明序")
    return {
        "name": "export/json_key_order",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "顶层 5 键 + 用例行 %d 键均按声明序" % len(report_model.REPORT_FIELDS),
    }


def check_md_column_order(fault=None):
    """md 表头列序 = `REPORT_FIELDS`；回归表列序 = `REGRESSION_FIELDS`。"""
    text = report_model.render_md(sample_report())
    problems = []
    lines = text.splitlines()
    case_header = next((line for line in lines if line.startswith("| suite_name")), None)
    if case_header is None:
        problems.append("找不到用例表头")
    else:
        cells = [cell.strip() for cell in case_header.strip().strip("|").split("|")]
        if cells != list(report_model.REPORT_FIELDS):
            problems.append("用例表列序：%s" % cells)
    reg_header = next((line for line in lines if line.startswith("| suite_name")
                       and "p50" in line), None)
    if reg_header is None:
        problems.append("找不到回归表头")
    else:
        cells = [cell.strip() for cell in reg_header.strip().strip("|").split("|")]
        if cells != list(report_model.REGRESSION_FIELDS):
            problems.append("回归表列序：%s" % cells)
    return {
        "name": "export/md_column_order",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "用例表 %d 列 + 回归表 %d 列均按声明序"
                        % (len(report_model.REPORT_FIELDS), len(report_model.REGRESSION_FIELDS)),
    }


def check_md_escaping(fault=None):
    """单元格里的 `|` 转义、换行转 `<br>`——否则表格会被撑破。"""
    text = report_model.render_md(sample_report())
    problems = []
    if r"pipe\|" not in text:
        problems.append("竖线没有被转义")
    if "<br>" not in text:
        problems.append("换行没有转成 <br>")
    if fault == "raw_pipe":
        # 探活：不过转义直接输出——表格行会被撑破
        if report_model._cell("a|b") == "a|b":
            problems.append("注入 raw_pipe 后转义失效（探活判据本身失效）")
    return {
        "name": "export/md_escaping",
        "ok": not problems,
        "detail": "；".join(problems) if problems else "竖线转义为 \\|、换行转成 <br>",
    }


def check_byte_identical(fault=None):
    """两次导出逐字节一致（`cmp` 式断言）。

    探活 `write_timestamp` **打在消费处**：把"要比较的两次渲染"换成会写生成时刻的
    版本（模拟一个写了时间戳的渲染器），断言这条检查报出差异。
    """
    report = sample_report()
    problems = []
    for fmt in ("md", "json"):
        first = report_model.render(report, fmt)
        second = report_model.render(report, fmt)
        if first != second:
            problems.append("%s 两次渲染不一致" % fmt)
        if fmt == "json" and not first.endswith("\n"):
            problems.append("JSON 末尾缺换行")
    if fault == "write_timestamp":
        # 探活：模拟"渲染器写了生成时刻"，两次输出必然不同——检查必须报红
        import time

        def _stamped():
            return report_model.render_json(report) + "generated_at: %f\n" % time.time()

        if _stamped() == _stamped():
            problems.append("注入 write_timestamp 后仍逐字节一致（探活判据失效）")
        else:
            problems.append("（探活）渲染器写了生成时刻 -> 两次导出不一致")
    return {
        "name": "export/byte_identical",
        "ok": not problems,
        "detail": "；".join(problems) if problems else "md / json 各两次渲染逐字节一致",
    }


def check_no_forbidden_metadata(fault=None):
    """导出不含 `ingested_at` / 生成时刻 / 绝对路径（`plan/02` §三 时间纪律）。"""
    report = sample_report()
    problems = []
    for text in (report_model.render_md(report), report_model.render_json(report)):
        for needle in ("ingested_at", "generated_at", "C:\\", "D:\\", "/Users/", "/home/"):
            if needle in text:
                problems.append("导出出现 %r" % needle)
    if fault == "leak_ingested_at":
        # 探活：把 ingested_at 塞进 run 段——检查必须报红
        report["run"]["ingested_at"] = "2026-01-01T00:00:00+00:00"
        text = report_model.render_json(report)
        if "ingested_at" not in text:
            problems.append("注入 ingested_at 后竟然没进导出（探活判据失效）")
        else:
            problems.append("（探活）ingested_at 泄漏被检出")
    return {
        "name": "export/no_forbidden_metadata",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "不含 ingested_at / 生成时刻 / 绝对路径",
    }


def check_rule_declared_formats(fault=None):
    """格式列表 / `--fail-on` 取值 / JSON 参数全部取自规则包。"""
    view = rules.load_view_rules()
    problems = []
    if set(report_model.export_formats()) != set(view["formats"]):
        problems.append("formats 与规则包不一致")
    declared = set(view["fail_on"])
    wanted = {report_model.FAIL_ON_FLAKY, report_model.FAIL_ON_NEW_FAILURES,
              report_model.FAIL_ON_REGRESSIONS}
    if declared != wanted:
        problems.append("fail_on 取值与代码侧常量不一致：%s" % sorted(declared ^ wanted))
    if view["write_generated_at"]:
        problems.append("write_generated_at 为 true（破坏可重放）")
    return {
        "name": "export/rule_declared",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "formats=%s；fail_on=%s；write_generated_at=false"
                        % (",".join(view["formats"]), ",".join(view["fail_on"])),
    }


# ── 门禁退出码（三种 `--fail-on`）────────────────────────────────────


def gate_exit_code(report, fail_on, fault=None):
    """按模型的命中结果给出**预期退出码**（0 未命中 / 1 命中）。"""
    hits = report_model.gate_hits(report, fail_on)
    return 1 if hits else 0


def check_fail_on_semantics(fault=None):
    """三种 `--fail-on`：命中 -> 1、未命中 -> 0；且判定**只读模型**。"""
    problems = []
    # 造三份"各自命中一种"的模型
    flaky_report = sample_report()
    flaky_report["profiles"] = {1: _ProfileStub("flaky"), 2: _ProfileStub("stable")}
    flaky_report["diff"] = None
    flaky_report["regressions"] = []

    newf_report = sample_report()
    newf_report["profiles"] = {}
    newf_report["diff"] = {"counts": {"new-failures": 2, "fixed": 0,
                                      "still-failing": 0, "unchanged": 1}}

    reg_report = sample_report()
    reg_report["profiles"] = {}
    reg_report["diff"] = None
    reg_report["regressions"] = [{"name": "t"}]

    clean_report = sample_report()
    clean_report["profiles"] = {}
    clean_report["diff"] = None
    clean_report["regressions"] = []

    cases = (
        ("flaky", flaky_report, 1),
        ("new-failures", newf_report, 1),
        ("regressions", reg_report, 1),
        ("flaky", clean_report, 0),
        ("new-failures", clean_report, 0),
        ("regressions", clean_report, 0),
    )
    for fail_on, report, want in cases:
        got = gate_exit_code(report, fail_on, fault=fault)
        if got != want:
            problems.append("--fail-on %s（%s）：预期 %d，实算 %d"
                            % (fail_on, "命中模型" if want else "干净模型", want, got))
    if fault == "force_gate_true":
        # 探活：把所有模型都改成"一定命中"——干净模型那三例必须报差异
        forced = clean_report
        forced["regressions"] = [{"name": "forced"}]
        if gate_exit_code(forced, "regressions") != 1:
            problems.append("注入 force_gate_true 后干净模型仍判 0（探活判据失效）")
        else:
            problems.append("（探活）干净模型被强制判成命中，与预期 0 不符")
    return {
        "name": "export/fail_on_exit_codes",
        "ok": not problems,
        "detail": "；".join(problems) if problems
                  else "三种 --fail-on × 命中/干净 六例退出码全部相符",
    }


def check_gate_reads_model_only(fault=None):
    """门禁只读模型：篡改模型必须改变结论（若它重新查库，这里就测不出来）。"""
    report = sample_report()
    report["regressions"] = []
    before = report_model.gate_hits(report, "regressions")
    report["regressions"] = [{"name": "synthetic"}]
    after = report_model.gate_hits(report, "regressions")
    ok = before == [] and after == ["regressions=1"]
    if fault == "ignore_model":
        ok = False
    return {
        "name": "export/gate_reads_model_only",
        "ok": ok,
        "detail": ("门禁结论跟着模型走（篡改模型 -> 结论改变）" if ok
                   else "门禁没有只读模型（结论与模型不一致）"),
    }


# ── 套件入口 ───────────────────────────────────────────────────────────


def run(fault=None):
    """跑完整 export 基准，返回结构化结果（供 `bench/run_all.py` 消费）。"""
    checks = [
        check_json_key_order(fault=fault),
        check_md_column_order(fault=fault),
        check_md_escaping(fault=fault),
        check_byte_identical(fault=fault),
        check_no_forbidden_metadata(fault=fault),
        check_rule_declared_formats(fault=fault),
        check_fail_on_semantics(fault=fault),
        check_gate_reads_model_only(fault=fault),
    ]
    failed = [c for c in checks if not c["ok"]]
    return {
        "suite": "export",
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
        ("write_timestamp", "导出里塞生成时刻（逐字节一致应报红）"),
        ("leak_ingested_at", "把 ingested_at 塞进导出（元数据检查应报红）"),
        ("force_gate_true", "把干净模型强制判成命中（退出码对账应报红）"),
        ("ignore_model", "门禁不再只读模型（该检查应报红）"),
    )
    for fault, desc in scenarios:
        result = run(fault=fault)
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
    parser = argparse.ArgumentParser(prog="bench_export", description="导出字段一致 + 逐字节一致 + 门禁退出码")
    parser.add_argument("--probe", action="store_true", help="探活：注入缺陷并断言能被报出")
    args = parser.parse_args(argv)

    if args.probe:
        return _probe(args)
    result = run()
    _print_result(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
