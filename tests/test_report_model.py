"""`report_model.py`：字段声明序是唯一契约（md 列序 = JSON 键序 = TUI 取值来源）。

M5 的 `render_md` / `render_json` 会消费同一个 dict；这里先把**声明序**与**取值面**
钉死，免得导出落地时再"各自对齐一遍"。
"""

import os

import pytest

from testdeck import cli, db, exit_codes, queries, report_model, rules

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)


@pytest.fixture
def store(repo_root, tmp_path):
    db_path = str(tmp_path / "report.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    conn = db.open_existing(db_path)
    try:
        yield conn
    finally:
        conn.close()


def test_report_fields_are_ordered_and_stable():
    """字段是**有序元组**（不是集合）：导出列序/键序都取它，改序等于改契约。"""
    assert isinstance(report_model.REPORT_FIELDS, tuple)
    assert report_model.REPORT_FIELDS == (
        "suite_name", "classname", "name", "status", "time_ms",
        "failure_type", "failure_message", "stack_first_line",
    )
    assert "case_id" not in report_model.REPORT_FIELDS, "自增主键跨机器无意义，不进报表"


def test_build_report_shape_and_field_order(store):
    report = report_model.build_report(store)
    assert set(report) == {"run", "summary", "cases", "history", "suites",
                           "profiles", "slow", "diff", "regressions"}
    assert list(report["run"]) == list(queries.RUN_FIELDS)
    for row in report["cases"]:
        assert tuple(row) == report_model.REPORT_FIELDS, tuple(row)
    assert len(report["cases"]) == 18


def test_build_report_defaults_to_latest_run(store):
    report = report_model.build_report(store)
    assert report["run"]["run_id"] == queries.resolve_run(store).run_id
    assert report_model.build_report(store, report["run"]["run_id"])["run"]["run_id"] == \
        report["run"]["run_id"]


def test_build_report_uses_rule_summary_fields(store):
    report = report_model.build_report(store)
    assert list(report["summary"]) == rules.load_view_rules()["summary_fields"]
    assert report["summary"]["total"] == 18


def test_history_window_defaults_to_view_rule(store):
    """`history` 的窗口默认取 `view.sparkline_runs`（"画多少次"也只有一个来源）。"""
    window = rules.load_view_rules()["sparkline_runs"]
    report = report_model.build_report(store)
    case_id = next(iter(report["history"]))
    assert report["history"][case_id] == queries.history(store, case_id, window)
    assert report_model.build_report(store, window=3)["history"][case_id] == \
        queries.history(store, case_id, 3)


def test_build_report_refuses_empty_or_unknown_run(tmp_path):
    """没有 run / run 不存在 → `ReportError`（调用方给退出码 3，不返回空报告）。"""
    db_path = str(tmp_path / "empty.db")
    conn = db.connect(db_path)
    try:
        with pytest.raises(report_model.ReportError):
            report_model.build_report(conn)
    finally:
        conn.close()


def test_run_fields_exclude_ingested_at():
    """`ingested_at` 是元数据，**不进导出**（`plan/02` §三 时间纪律）。"""
    assert "ingested_at" not in report_model.RUN_FIELDS
    assert "ingested_at" not in report_model.REPORT_FIELDS


def test_report_model_does_not_import_textual():
    """表示层纪律：`report_model` 不得 import Textual（TUI 只是它的渲染器之一）。"""
    import ast
    import pathlib
    source = pathlib.Path(report_model.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] != "textual" for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            assert node.module.split(".")[0] != "textual"
