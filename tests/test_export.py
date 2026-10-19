"""`export`（M5 模块⑤）：字段序一致、逐字节可重放、`--fail-on` 三种语义、退出码。

三条 DoD 在这里落地：

- **md 列序 = JSON 键序 = `REPORT_FIELDS`**（共用 `report_model`，不是两处对齐）；
- **两次导出逐字节一致**（`cmp` 式断言：不含生成时刻、不含 `ingested_at`、不含绝对路径）；
- **`--fail-on` 三种值命中 -> 1；未知值 / 缺参数 -> 2；库/run 不可用 -> 3**，
  且判定**只读模型**（不重新查库）。
"""

import json
import os

import pytest

from testdeck import cli, db, diff, exit_codes, flaky, model, report_model, rules

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)


@pytest.fixture
def store(repo_root, tmp_path):
    db_path = str(tmp_path / "export.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    conn = db.open_existing(db_path)
    try:
        yield conn, db_path
    finally:
        conn.close()


# ── 字段序：md 列序 = JSON 键序 = 字段声明序 ──────────────────────────


def test_render_json_key_order_matches_report_fields(store):
    conn, _db = store
    report = report_model.build_report(conn)
    payload = json.loads(report_model.render_json(report))
    for row in payload["cases"]:
        assert tuple(row) == report_model.REPORT_FIELDS, tuple(row)
    assert list(payload) == ["run", "summary", "cases", "regressions", "diff"]


def test_render_md_column_order_matches_report_fields(store):
    conn, _db = store
    text = report_model.render_md(report_model.build_report(conn))
    header = next(line for line in text.splitlines()
                  if line.startswith("| suite_name"))
    cells = [cell.strip() for cell in header.strip().strip("|").split("|")]
    assert cells == list(report_model.REPORT_FIELDS)


def test_render_md_and_json_agree_on_case_rows(store):
    """同一份模型渲染两次（md / json）：用例身份与状态逐项相同。"""
    conn, _db = store
    report = report_model.build_report(conn)
    payload = json.loads(report_model.render_json(report))
    text = report_model.render_md(report)
    for row in payload["cases"]:
        assert row["name"] in text
        assert row["status"] in text


# ── 逐字节可重放 ──────────────────────────────────────────────────────


def test_render_json_is_byte_identical_across_two_runs(store):
    conn, _db = store
    first = report_model.render_json(report_model.build_report(conn))
    second = report_model.render_json(report_model.build_report(conn))
    assert first == second
    assert first.endswith("\n"), "JSON 末尾必须有一个换行"


def test_render_md_is_byte_identical_across_two_runs(store):
    conn, _db = store
    first = report_model.render_md(report_model.build_report(conn))
    second = report_model.render_md(report_model.build_report(conn))
    assert first == second


def test_export_via_cli_is_byte_identical(store, capsys):
    """**双跑 `cmp`**：同一条 CLI 命令跑两次，stdout 逐字节一致。"""
    _conn, db_path = store
    runs = []
    for _ in range(2):
        assert cli.main(["export", "--db", db_path, "--format", "json"]) == exit_codes.OK
        runs.append(capsys.readouterr().out)
    assert runs[0].encode("utf-8") == runs[1].encode("utf-8")
    assert runs[0].endswith("\n")


def test_export_contains_no_generated_at_or_absolute_path(store):
    """不写生成时刻、不含 `ingested_at`、不含绝对路径（`plan/03` 模块⑤）。"""
    conn, _db = store
    for text in (report_model.render_json(report_model.build_report(conn)),
                 report_model.render_md(report_model.build_report(conn))):
        assert "ingested_at" not in text
        assert "generated_at" not in text
        assert "C:\\" not in text and "D:\\" not in text
        assert "/Users/" not in text and "/home/" not in text


def test_export_source_path_is_relative(store):
    conn, _db = store
    report = report_model.build_report(conn)
    assert report["run"]["source_path"].startswith("bench/fixtures/")


# ── md 单元格转义（不破坏表格）──────────────────────────────────────


def test_md_cell_escapes_pipe_and_newline(store):
    """单元格里的 `|` 转义、换行转 `<br>`——否则表格会被撑破。"""
    conn, _db = store
    report = report_model.build_report(conn)
    # 三份 fixture 里 playwright 的 stack 首行含换行（fixture 自带）
    text = report_model.render_md(report)
    assert "|" in text
    for line in text.splitlines():
        if line.startswith("| ") and "<br>" in line:
            # 含 <br> 的行仍然是一行（没有真的换行撑破表格）
            assert line.count("|") >= len(report_model.REPORT_FIELDS)
    assert report_model._cell("a|b") == "a\\|b"
    assert report_model._cell("a\nb") == "a<br>b"
    assert report_model._cell(None) == "—"


# ── 回归清单进导出 ────────────────────────────────────────────────────


def test_regressions_section_uses_declared_field_order(store):
    conn, _db = store
    report = report_model.build_report(conn)
    payload = json.loads(report_model.render_json(report))
    for row in payload["regressions"]:
        assert tuple(row) == report_model.REGRESSION_FIELDS, tuple(row)


# ── --fail-on 三种语义（只读模型）────────────────────────────────────


def _report_with(**overrides):
    """造一份最小报告模型（只用于门禁判定，不碰库）。"""
    base = {
        "run": {}, "summary": {}, "cases": [], "history": {}, "suites": [],
        "profiles": {}, "slow": [], "diff": None, "regressions": [],
    }
    base.update(overrides)
    return base


def test_gate_flaky_hits_when_flaky_count_positive():
    profile = flaky.CaseProfile(label=flaky.LABEL_FLAKY, counted_runs=6, passes=3, fails=3,
                                fail_rate=model.as_fraction("0.5"), transitions=3,
                                flaky_score=model.as_fraction("1"))
    report = _report_with(profiles={1: profile})
    assert report_model.gate_hits(report, "flaky") == ["flaky=1"]
    assert report_model.gate_hits(report, "new-failures") == []
    assert report_model.gate_hits(report, "regressions") == []


def test_gate_new_failures_reads_diff_counts():
    report = _report_with(diff={"counts": {diff.NEW_FAILURES: 2, diff.FIXED: 1}})
    assert report_model.gate_hits(report, "new-failures") == ["new-failures=2"]
    assert report_model.gate_hits(report, "flaky") == []


def test_gate_regressions_reads_regression_list():
    report = _report_with(regressions=[{"name": "t"}])
    assert report_model.gate_hits(report, "regressions") == ["regressions=1"]


def test_gate_without_fail_on_never_hits():
    report = _report_with(regressions=[{"name": "t"}],
                          profiles={1: flaky.CaseProfile(
                              label=flaky.LABEL_FLAKY, counted_runs=6, passes=3, fails=3,
                              fail_rate=model.as_fraction("0.5"), transitions=3,
                              flaky_score=model.as_fraction("1"))})
    assert report_model.gate_hits(report, None) == []


def test_gate_never_requeries_db(store):
    """门禁**只读模型**：给一个"报告 dict 与库不一致"的模型，判定必须跟着模型走。

    做法：拿真报告，然后把 `regressions` 清空——若门禁重新查库，它就会看到真库里的
    回归清单；若它只读模型（本实现），就看不到。这条钉住"看到的就是门禁算的"。
    """
    conn, _db = store
    report = report_model.build_report(conn)
    assert report_model.gate_hits(report, "regressions") == []  # 真库无回归
    tampered = dict(report)
    tampered["regressions"] = [{"name": "synthetic"}]
    assert report_model.gate_hits(tampered, "regressions") == ["regressions=1"]


# ── 退出码 ────────────────────────────────────────────────────────────


def test_export_exit_1_when_gate_hits(store, monkeypatch):
    """门禁命中 -> exit 1。用桩把模型换成"一定有回归"的实现。"""
    _conn, db_path = store
    real = report_model.build_report

    def fake(conn, run_id=None, window=None):
        report = real(conn, run_id, window)
        report["regressions"] = [{"name": "synthetic"}]
        return report

    monkeypatch.setattr(report_model, "build_report", fake)
    assert cli.main(["export", "--db", db_path, "--fail-on", "regressions"]) == \
        exit_codes.GATE_TRIGGERED


def test_export_exit_0_when_gate_not_hit(store):
    _conn, db_path = store
    for value in ("flaky", "new-failures", "regressions"):
        assert cli.main(["export", "--db", db_path, "--fail-on", value]) == exit_codes.OK


def test_export_unknown_format_is_usage_error(tmp_path):
    assert cli.main(["export", "--format", "xml"]) == exit_codes.USAGE


def test_export_unknown_fail_on_is_usage_error(tmp_path):
    assert cli.main(["export", "--fail-on", "everything"]) == exit_codes.USAGE


def test_export_missing_db_is_dependency_error(tmp_path):
    assert cli.main(["export", "--db", str(tmp_path / "nope.db")]) == exit_codes.DEPENDENCY


def test_export_empty_db_is_dependency_error(tmp_path):
    db_path = str(tmp_path / "empty.db")
    db.connect(db_path).close()
    assert cli.main(["export", "--db", db_path]) == exit_codes.DEPENDENCY


def test_export_run_id_not_found_is_dependency_error(store):
    _conn, db_path = store
    assert cli.main(["export", "--db", db_path, "--run", "4242"]) == exit_codes.DEPENDENCY


def test_export_unknown_format_raises_value_error():
    with pytest.raises(ValueError):
        report_model.render({}, "xml")


# ── 导出模块本身的分层与纪律 ─────────────────────────────────────────


def test_export_module_does_not_import_textual():
    """表示层纪律：`export.py` 不得 import Textual（TUI 只是渲染器之一）。"""
    import ast
    import pathlib
    from testdeck import export
    source = pathlib.Path(export.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != "textual" for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            assert node.module.split(".")[0] != "textual"


def test_report_model_exports_use_rule_declared_formats():
    """格式列表取自规则包（`view.export.formats`），代码里不写第二份。"""
    assert set(report_model.export_formats()) == set(rules.load_view_rules()["formats"])


def test_fail_on_values_come_from_rules():
    """`--fail-on` 的三个取值与规则包登记的一致。"""
    declared = set(rules.load_view_rules()["fail_on"])
    assert declared == {report_model.FAIL_ON_FLAKY, report_model.FAIL_ON_NEW_FAILURES,
                        report_model.FAIL_ON_REGRESSIONS}
