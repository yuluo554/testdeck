"""`diff.py` 判定层：两次 run 用例级 diff 的**三类分类**逐类对账。

判定层是纯函数（只吃状态对），所以这里既跑内存构造的 `DiffRow`，也跑真实库上的
`queries.diff_rows`（编排层取数 → 判定层分类，依赖方向单向向下）。
"""

import os

import pytest

from testdeck import cli, db, diff, exit_codes, model, queries


def _row(case_id, before, after, classname="C", name="t"):
    return queries.DiffRow(case_id, "s", classname, name, before, after)


FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)


# ── 分类口径（逐类）────────────────────────────────────────────────────


@pytest.mark.parametrize("before,after,expected", [
    # 新增失败：after == fail 且 before != fail（含 before 缺行）
    (model.STATUS_PASS, model.STATUS_FAIL, diff.NEW_FAILURES),
    (model.STATUS_SKIP, model.STATUS_FAIL, diff.NEW_FAILURES),
    (model.STATUS_MISSING, model.STATUS_FAIL, diff.NEW_FAILURES),
    (None, model.STATUS_FAIL, diff.NEW_FAILURES),
    # 修复：before == fail 且 after == pass
    (model.STATUS_FAIL, model.STATUS_PASS, diff.FIXED),
    # 仍失败：两侧都 fail
    (model.STATUS_FAIL, model.STATUS_FAIL, diff.STILL_FAILING),
    # 其余：不落上面三类
    (model.STATUS_PASS, model.STATUS_PASS, diff.UNCHANGED),
    (model.STATUS_FAIL, model.STATUS_SKIP, diff.UNCHANGED),
    (model.STATUS_FAIL, model.STATUS_MISSING, diff.UNCHANGED),
    (model.STATUS_FAIL, None, diff.UNCHANGED),
    (None, model.STATUS_PASS, diff.UNCHANGED),
    (model.STATUS_PASS, None, diff.UNCHANGED),
    (None, None, diff.UNCHANGED),
    (model.STATUS_SKIP, model.STATUS_SKIP, diff.UNCHANGED),
])
def test_classify_matrix(before, after, expected):
    assert diff.classify(before, after) == expected


def test_new_failure_takes_priority_over_still_failing():
    """`fail→fail` 是"仍失败"，不是"新增失败"——新增失败要求 before != fail。"""
    assert diff.classify(model.STATUS_FAIL, model.STATUS_FAIL) == diff.STILL_FAILING
    assert diff.classify(model.STATUS_FAIL, model.STATUS_FAIL) != diff.NEW_FAILURES


def test_fixed_requires_after_pass_not_skip_or_missing():
    """**口径硬点**：`fail→skip` / `fail→缺` **不是**"修复"。

    没有 `pass` 就没有"修好了"的证据——把"这次没跑/被跳过"算成修复会让修复数虚高。
    """
    assert diff.classify(model.STATUS_FAIL, model.STATUS_SKIP) == diff.UNCHANGED
    assert diff.classify(model.STATUS_FAIL, model.STATUS_MISSING) == diff.UNCHANGED
    assert diff.classify(model.STATUS_FAIL, None) == diff.UNCHANGED
    assert diff.classify(model.STATUS_FAIL, model.STATUS_PASS) == diff.FIXED


# ── 分组 / 计数 ────────────────────────────────────────────────────────


def test_group_rows_uses_fixed_class_order_and_keeps_empty_buckets():
    rows = [_row(1, model.STATUS_PASS, model.STATUS_FAIL),
            _row(2, model.STATUS_FAIL, model.STATUS_PASS),
            _row(3, model.STATUS_FAIL, model.STATUS_FAIL),
            _row(4, model.STATUS_PASS, model.STATUS_PASS)]
    groups = diff.group_rows(diff.classify_rows(rows))
    assert list(groups) == list(diff.CLASS_ORDER), "分桶顺序 = CLASS_ORDER（固定）"
    assert [e.case_id for e in groups[diff.NEW_FAILURES]] == [1]
    assert [e.case_id for e in groups[diff.FIXED]] == [2]
    assert [e.case_id for e in groups[diff.STILL_FAILING]] == [3]
    assert [e.case_id for e in groups[diff.UNCHANGED]] == [4]


def test_group_rows_gives_empty_lists_for_absent_classes():
    """某一类一条都没有时，桶仍在（空列表）——呈现层不必判 None。"""
    groups = diff.group_rows(diff.classify_rows([_row(1, model.STATUS_PASS, model.STATUS_PASS)]))
    for kind in diff.CLASS_ORDER:
        assert kind in groups and isinstance(groups[kind], list)
    assert groups[diff.NEW_FAILURES] == []


def test_counts_and_new_failure_count():
    rows = [_row(1, model.STATUS_PASS, model.STATUS_FAIL),
            _row(2, None, model.STATUS_FAIL),
            _row(3, model.STATUS_FAIL, model.STATUS_PASS),
            _row(4, model.STATUS_FAIL, model.STATUS_FAIL)]
    classified = diff.classify_rows(rows)
    assert diff.counts(classified) == {
        diff.NEW_FAILURES: 2, diff.FIXED: 1, diff.STILL_FAILING: 1, diff.UNCHANGED: 0}
    assert diff.new_failure_count(classified) == 2
    assert sum(diff.counts(classified).values()) == len(rows), "分类不漏行"


def test_classified_display_shows_missing_side():
    entry = diff.classify_rows([_row(1, model.STATUS_PASS, None)])[0]
    assert entry.kind == diff.UNCHANGED
    assert "pass→(缺)" in entry.display


def test_class_order_covers_every_class_and_reconciled_subset():
    assert set(diff.CLASS_ORDER) == {
        diff.NEW_FAILURES, diff.FIXED, diff.STILL_FAILING, diff.UNCHANGED}
    assert set(diff.RECONCILED_CLASSES) <= set(diff.CLASS_ORDER)
    assert diff.NEW_FAILURES in diff.RECONCILED_CLASSES
    # 三类都有展示标题（TUI / 导出共用）
    for kind in diff.CLASS_ORDER:
        assert diff.CLASS_TITLES[kind]


# ── 接真实库（编排层取数 → 判定层分类）────────────────────────────────


@pytest.fixture
def store(repo_root, tmp_path):
    db_path = str(tmp_path / "diff.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    conn = db.open_existing(db_path)
    run = queries.resolve_run(conn)
    try:
        yield conn, run
    finally:
        conn.close()


def test_same_run_diff_is_all_unchanged(store):
    """同一 run 与自身 diff：`x→x`。fail→fail 落"仍失败"，其余落"其余"；无新增/修复。"""
    conn, run = store
    classified = diff.classify_rows(queries.diff_rows(conn, run.run_id, run.run_id))
    assert len(classified) == 18
    counts = diff.counts(classified)
    assert counts[diff.NEW_FAILURES] == 0
    assert counts[diff.FIXED] == 0
    # 三份真跑产物各 1 条 fail，与自身 diff即 fail→fail → 仍失败
    assert counts[diff.STILL_FAILING] == 3
    assert counts[diff.UNCHANGED] == 15


def test_diff_against_future_run_reports_new_failures(store):
    """与"未来 run"（缺行侧）diff：本 run 的 fail 用例都算**新增失败**。

    `缺→fail` 是新增失败（base 里没有、这次坏了），`缺→pass` 是其余——这条同时
    钉住"缺行不等于任何状态"。
    """
    conn, run = store
    rows = queries.diff_rows(conn, run.run_id + 1, run.run_id)
    counts = diff.counts(diff.classify_rows(rows))
    failing = sum(1 for row in rows if row.status_after == model.STATUS_FAIL)
    assert counts[diff.NEW_FAILURES] == failing == 3
    assert counts[diff.STILL_FAILING] == 0
    assert counts[diff.FIXED] == 0


def test_diff_reverses_to_unchanged(store):
    """反向 diff（本 run → 未来 run 缺行）：fail→缺 落"其余"，不落"修复"。

    fail→缺**不是**修复（没有 pass 就没有修好的证据），也不是仍失败（这次没跑）。
    """
    conn, run = store
    rows = queries.diff_rows(conn, run.run_id, run.run_id + 1)
    counts = diff.counts(diff.classify_rows(rows))
    assert counts[diff.NEW_FAILURES] == 0
    assert counts[diff.FIXED] == 0, "fail→缺 不是修复"
    assert counts[diff.STILL_FAILING] == 0
    assert counts[diff.UNCHANGED] == 18
