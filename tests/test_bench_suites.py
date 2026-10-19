"""基准套件：三框架对账、性能门、`run_all` 的 0/1/2 三语义与"未就绪不冒充通过"。

`not_enabled` 那几条是本文件的重点：一个"套件没跑"必须**不能**被算成通过。
"""

import json
import os

FRAMEWORKS = ("pytest", "gotestsum", "playwright")


# ── 三框架逐项对账 ─────────────────────────────────────────────────────


def test_every_fixture_has_artifact_and_expected(repo_root):
    """三份产物入库且各带 expected.json（M1 DoD 第一行）。"""
    for framework in FRAMEWORKS:
        directory = os.path.join(repo_root, "bench", "fixtures", framework)
        entries = sorted(os.listdir(directory))
        assert any(name.endswith(".xml") for name in entries), "%s 缺 XML 产物" % framework
        assert "expected.json" in entries, "%s 缺 expected.json" % framework
        assert "README.md" in entries, "%s 缺 README.md（来源/工具版本/命令）" % framework


def test_expected_json_records_provenance(repo_root):
    """expected.json 必须写明产出工具、版本与命令——"真实产物"这句话要可复核。"""
    for framework in FRAMEWORKS:
        path = os.path.join(repo_root, "bench", "fixtures", framework, "expected.json")
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        produced = data.get("produced_by") or {}
        assert data.get("framework") == framework
        for key in ("tool", "tool_version", "command", "source"):
            assert produced.get(key), "%s 的 produced_by 缺 %s" % (framework, key)
        assert produced["source"] == "本机真实运行", (
            "%s 的来源必须如实标注（本机真实运行 / 预置产物）" % framework)


def test_bench_ingest_reconciliation_passes(bench_ingest, tmp_path):
    """三框架元素重数 / XML 声明值 / expected.json 三通道逐项相等。"""
    result = bench_ingest.run(perf_gate=False, big_file=str(tmp_path / "big.xml"),
                              big_cases=400)
    failed = [c for c in result["checks"] if not c["ok"]]
    assert result["ok"] is True, "逐项对账未达标：%s" % failed
    names = {c["name"] for c in result["checks"]}
    for framework in FRAMEWORKS:
        assert "fixture/%s/elements_vs_expected" % framework in names
        assert "fixture/%s/xml_declared_vs_expected" % framework in names
        assert "fixture/%s/suites_vs_expected" % framework in names


def test_bench_ingest_records_undeclared_fields_honestly(bench_ingest, tmp_path):
    """gotestsum 不声明 `skipped` 属性——对账要如实标"未声明"，不能当成 0 而报假红。"""
    result = bench_ingest.run(perf_gate=False, big_file=str(tmp_path / "big.xml"),
                             big_cases=400)
    check = next(c for c in result["checks"]
                 if c["name"] == "fixture/gotestsum/xml_declared_vs_expected")
    assert check["ok"] is True, check["detail"]
    assert "skipped" in check["detail"], "未声明字段没有被标出来：%s" % check["detail"]


def test_bench_ingest_detects_off_by_one(bench_ingest, tmp_path):
    """探活口径：把对账读到的数量改 1，判定必须报出差异（防"绿是装饰"）。"""
    result = bench_ingest.run(perf_gate=False, big_file=str(tmp_path / "big.xml"),
                              big_cases=400, fault="off_by_one")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert failed, "注入 off_by_one 后对账仍全绿"
    assert any("elements_vs_expected" in c["name"] for c in failed)


def test_bench_ingest_perf_gate_can_fail(bench_ingest, tmp_path):
    """性能门槛压到 0 -> 必须报未达标（证明性能判定真的在判）。"""
    result = bench_ingest.run(perf_gate=True, big_file=str(tmp_path / "big.xml"),
                              big_cases=400, fault="perf_impossible")
    check = next(c for c in result["checks"] if c["name"] == "perf/iterparse_big_file")
    assert check["ok"] is False


def test_bench_ingest_perf_gate_off_reports_only(bench_ingest, tmp_path):
    result = bench_ingest.run(perf_gate=False, big_file=str(tmp_path / "big.xml"),
                              big_cases=400)
    check = next(c for c in result["checks"] if c["name"] == "perf/iterparse_big_file")
    assert check["ok"] is True
    assert check["cases"] == 400


def test_bench_ingest_parses_streaming_counts(bench_ingest, tmp_path):
    """解析器自身：三态计数正确、suite 明细正确。"""
    xml = tmp_path / "sample.xml"
    xml.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="s" tests="3" failures="1">'
        '<testcase classname="a" name="t1"/>'
        '<testcase classname="a" name="t2"><failure message="x"/></testcase>'
        '<testcase classname="a" name="t3"><skipped/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8")
    totals, suites = bench_ingest.parse_junit_stream(str(xml))
    assert totals == {"tests": 3, "failures": 1, "errors": 0, "skipped": 1}
    assert len(suites) == 1 and suites[0]["name"] == "s" and suites[0]["tests"] == 3


# ── run_all：退出码三语义 ──────────────────────────────────────────────


def test_bench_flaky_reconciliation_passes(bench_flaky):
    """flaky 分型 / `flaky_score` 与台账、参照实现逐值相等（M4 DoD 第一行）。"""
    result = bench_flaky.run()
    failed = [c for c in result["checks"] if not c["ok"]]
    assert result["ok"] is True, "flaky 对账未达标：%s" % failed
    names = {c["name"] for c in result["checks"]}
    for wanted in ("flaky/anchors_vs_expected", "flaky/samples_vs_expected",
                   "flaky/production_vs_refimpl", "flaky/broken_flaky_exclusive",
                   "flaky/degrade_zero_counted", "flaky/corpus_label_counts"):
        assert wanted in names, wanted


def test_bench_flaky_broken_flaky_exclusive_is_independent(bench_flaky):
    """`broken ∩ flaky == ∅` 是**独立断言**：拿两份集合求交，两份都非空。"""
    result = bench_flaky.run(corpus=False)
    check = next(c for c in result["checks"] if c["name"] == "flaky/broken_flaky_exclusive")
    assert check["ok"] is True, check["detail"]
    assert check["broken"], "broken 集合为空（判据空转）"
    assert check["flaky"], "flaky 集合为空（判据空转）"
    assert set(check["broken"]) & set(check["flaky"]) == set()


def test_bench_flaky_zero_counted_degradation(bench_flaky):
    """K34：零计数样本落 watch（fail_rate 无定义），不得判 stable。"""
    result = bench_flaky.run(corpus=False)
    check = next(c for c in result["checks"] if c["name"] == "flaky/degrade_zero_counted")
    assert check["ok"] is True, check["detail"]
    assert "无定义" in check["detail"]


def test_bench_flaky_detects_off_by_one(bench_flaky):
    """探活口径：transitions +1，判定必须报出差异。"""
    result = bench_flaky.run(corpus=False, fault="off_by_one")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert failed, "注入 off_by_one 后对账仍全绿"
    assert any("vs_expected" in c["name"] for c in failed)


def test_bench_flaky_detects_forced_flaky(bench_flaky):
    """把一切判成 flaky → `broken ∩ flaky == ∅` 必须报红（互斥判据非恒真）。"""
    result = bench_flaky.run(corpus=False, fault="force_flaky")
    check = next(c for c in result["checks"] if c["name"] == "flaky/broken_flaky_exclusive")
    assert check["ok"] is False, "强行判 flaky 后互斥断言仍绿（判据失效）"


def test_bench_flaky_probe_detects_all(bench_flaky):
    import argparse
    assert bench_flaky._probe(argparse.Namespace(ledger=None)) == 0


# ── slow 套件（M5）─────────────────────────────────────────────────────


def test_bench_slow_reconciliation_passes(bench_slow):
    """p50/p95 与回归判定与台账、参照实现逐值相等（M5 DoD 第一行）。"""
    result = bench_slow.run()
    failed = [c for c in result["checks"] if not c["ok"]]
    assert result["ok"] is True, "slow 对账未达标：%s" % failed
    names = {c["name"] for c in result["checks"]}
    for wanted in ("slow/anchors_vs_expected", "slow/samples_vs_expected",
                   "slow/production_vs_refimpl", "slow/regression_boundaries",
                   "slow/missing_time_not_zero", "slow/undefined_is_none_not_false",
                   "slow/corpus_regression_counts"):
        assert wanted in names, wanted


def test_bench_slow_regression_boundaries_are_three_state(bench_slow):
    """回归边界六种：True / False / None 三态都要出现（判据不是恒真/恒假）。"""
    result = bench_slow.run(corpus=False)
    check = next(c for c in result["checks"] if c["name"] == "slow/regression_boundaries")
    assert check["ok"] is True, check["detail"]
    assert "三态齐全" in check["detail"]


def test_bench_slow_missing_time_is_not_zero_filled(bench_slow):
    """缺失耗时**不补 0**：这条口径在本基准里可证伪（补 0 会给出不同 p50）。"""
    result = bench_slow.run(corpus=False)
    check = next(c for c in result["checks"] if c["name"] == "slow/missing_time_not_zero")
    assert check["ok"] is True, check["detail"]
    assert "缺失不进样本" in check["detail"]


def test_bench_slow_detects_off_by_one(bench_slow):
    """探活口径：对账读到的 p50 +1，判定必须报出差异。"""
    result = bench_slow.run(corpus=False, fault="off_by_one")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert failed, "注入 off_by_one 后对账仍全绿"
    assert any("vs_expected" in c["name"] for c in failed)


def test_bench_slow_detects_forced_regression(bench_slow):
    """把一切判成回归 -> 边界对账必须报红（判据非恒真）。"""
    result = bench_slow.run(corpus=False, fault="force_regression")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert failed, "注入 force_regression 后对账仍全绿"


def test_bench_slow_probe_detects_all(bench_slow):
    import argparse
    assert bench_slow._probe(argparse.Namespace(ledger=None)) == 0


# ── export 套件（M5）───────────────────────────────────────────────────


def test_bench_export_reconciliation_passes(bench_export):
    """导出字段一致 + 逐字节一致 + 门禁退出码（M5 DoD）。"""
    result = bench_export.run()
    failed = [c for c in result["checks"] if not c["ok"]]
    assert result["ok"] is True, "export 对账未达标：%s" % failed
    names = {c["name"] for c in result["checks"]}
    for wanted in ("export/json_key_order", "export/md_column_order", "export/md_escaping",
                   "export/byte_identical", "export/no_forbidden_metadata",
                   "export/rule_declared", "export/fail_on_exit_codes",
                   "export/gate_reads_model_only"):
        assert wanted in names, wanted


def test_bench_export_detects_timestamp_leak(bench_export):
    """探活口径：渲染器写了生成时刻 -> 逐字节一致检查必须报红。"""
    result = bench_export.run(fault="write_timestamp")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert failed, "注入 write_timestamp 后仍全绿"
    assert any("byte_identical" in c["name"] for c in failed)


def test_bench_export_detects_ingested_at_leak(bench_export):
    result = bench_export.run(fault="leak_ingested_at")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert any("no_forbidden_metadata" in c["name"] for c in failed), failed


def test_bench_export_probe_detects_all(bench_export):
    import argparse
    assert bench_export._probe(argparse.Namespace()) == 0


def test_run_all_list_shows_registry(run_all):
    assert {entry["name"] for entry in run_all.SUITES} == {"ingest", "flaky", "slow", "export"}


def test_run_all_flaky_suite_is_enabled_at_m4(run_all):
    """M4 起 `flaky` 套件已就绪（`CURRENT_MILESTONE >= 4`），不再 `not_enabled`。"""
    assert run_all.CURRENT_MILESTONE >= 4
    results, _ = run_all.run_suites({"flaky"}, perf_gate=False)
    assert results and results[0]["not_enabled"] is False, results
    assert results[0]["ok"] is True, [c for c in results[0]["checks"] if not c["ok"]]


def test_run_all_all_four_suites_are_enabled_at_m5(run_all):
    """**M5 收尾判据**：四套件全部就绪（`CURRENT_MILESTONE >= 5`），无 `not_enabled`。"""
    assert run_all.CURRENT_MILESTONE >= 5
    results, _ = run_all.run_suites({"ingest", "flaky", "slow", "export"}, perf_gate=False)
    by_name = {r["suite"]: r for r in results}
    assert set(by_name) == {"ingest", "flaky", "slow", "export"}
    for name, result in by_name.items():
        assert result["not_enabled"] is False, name
        assert result["ok"] is True, (name, [c for c in result["checks"] if not c["ok"]])


def test_run_all_default_selection_exits_zero_at_m5(run_all):
    """M5 起不带 `--suites` 跑全部套件也拿 0（未就绪不再存在）。"""
    assert run_all.main(["--no-perf-gate"]) == 0


def test_run_all_exit_0_when_all_selected_suites_pass(run_all):
    assert run_all.main(["--suites", "ingest", "--no-perf-gate"]) == 0


def test_run_all_exit_2_on_unknown_suite(run_all):
    assert run_all.main(["--suites", "definitely-not-a-suite"]) == 2


def test_run_all_exit_2_on_empty_suite_list(run_all):
    assert run_all.main(["--suites", " , "]) == 2


def test_not_enabled_suite_is_not_a_pass(run_all, monkeypatch):
    """未就绪套件：`ok` 必须是 False、`not_enabled` 是 True（不得冒充通过）。"""
    monkeypatch.setattr(run_all, "CURRENT_MILESTONE", 0)
    results, _ = run_all.run_suites({"ingest", "flaky"})
    by_name = {r["suite"]: r for r in results}
    for suite in ("ingest", "flaky"):
        assert by_name[suite]["not_enabled"] is True, suite
        assert by_name[suite]["ok"] is False, suite
        assert by_name[suite]["notes"], "%s 必须带 notes 声明" % suite


def test_not_enabled_forces_exit_1(run_all, monkeypatch):
    """只要有一个套件未就绪，退出码就是 1——"没跑"不能算"达标"。"""
    monkeypatch.setattr(run_all, "CURRENT_MILESTONE", 0)
    assert run_all.main(["--suites", "ingest", "--no-perf-gate"]) == 1


def test_failing_suite_forces_exit_1(run_all, monkeypatch):
    """有一个套件真失败 -> exit 1。用桩把 ingest 换成必失败的实现。"""
    class _Failing:
        @staticmethod
        def run(**_kwargs):
            return {"suite": "ingest", "enabled": True, "ok": False,
                    "checks": [{"name": "stub/always_fails", "ok": False, "detail": "桩"}],
                    "notes": []}

    monkeypatch.setattr(run_all, "_load_suite_module", lambda _name: _Failing)
    assert run_all.main(["--suites", "ingest", "--no-perf-gate"]) == 1


def test_missing_suite_script_is_not_enabled(run_all, monkeypatch):
    """套件脚本缺失 -> not_enabled，而不是"零检查即通过"。"""
    monkeypatch.setattr(run_all, "_load_suite_module", lambda _name: None)
    results, _ = run_all.run_suites({"ingest"})
    assert results[0]["not_enabled"] is True and results[0]["ok"] is False


def test_probe_reports_all_detected(run_all):
    """探活总入口：全部注入都要能被检出（否则探活本身是装饰）。"""
    assert run_all.main(["--probe"]) == 0


def test_run_all_skips_prechecks_flag_still_works(run_all):
    assert run_all.main(["--suites", "ingest", "--no-perf-gate", "--skip-prechecks"]) == 0


# ── 入库产物脱敏守门（可证伪）─────────────────────────────────────────


def test_fixture_leak_scan_is_clean(scan_leaks, repo_root):
    """入库的 fixture 里不得出现本机绝对路径 / 机器名 / 真实域名。"""
    problems, scanned = scan_leaks.scan(os.path.join(repo_root, "bench", "fixtures"))
    assert scanned > 0, "扫描面为空（判据失效）"
    assert problems == [], "发现泄漏：%s" % problems


def test_fixture_leak_scan_detects_real_machine_data(scan_leaks, tmp_path):
    """变异验证：造一份带真机器名的产物，守门必须报红（防"恒绿"）。"""
    target = tmp_path / "leak.xml"
    target.write_text(
        '<testsuites hostname="LAPTOP-DEADBEEF" path="C:\\Users\\real\\proj\\x.xml">'
        '<testsuite name="s" tests="1"><testcase name="t"/></testsuite></testsuites>',
        encoding="utf-8")
    problems, scanned = scan_leaks.scan(str(tmp_path))
    assert scanned == 1
    labels = " ".join(problems)
    assert "machine-name" in labels, problems
    assert "windows-abs-path" in labels, problems


def test_fixture_leak_scan_allows_abstraction_in_docs(scan_leaks, tmp_path):
    """文档里"我们删掉了 hostname 属性"这类**抽象**描述不该被当成泄漏。

    否则守门会去罚它自己的说明书（M1 实测踩过：README 被判 4 处泄漏）。
    """
    doc = tmp_path / "README.md"
    doc.write_text(
        "入库前删除 `hostname` 属性（机器名），并把绝对路径改写成仓库内相对路径。\n",
        encoding="utf-8")
    problems, scanned = scan_leaks.scan(str(tmp_path))
    assert scanned == 1
    assert problems == [], problems
