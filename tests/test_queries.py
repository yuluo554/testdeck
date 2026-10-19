"""`queries.py` 只读层：失败优先排序单点、summary 与 SQL 逐项相等、四态矩阵原料。

设备件统一"真跑产物 + 临时库"，不碰用户默认库。这一层是 UI 之外的**第二条通路**
（`plan/02` §五："便于无头测试 summary 计数"），所以 DoD 的"summary 与直接 SQL 查询
逐项相等"就落在这里，而不是靠 Pilot 截图。
"""

import os
from fractions import Fraction

import pytest

from testdeck import cli, db, exit_codes, queries, rules

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)


@pytest.fixture
def store(repo_root, tmp_path):
    """三份真跑产物落进临时库，返回 ``(conn, run)``（用完关连接）。"""
    db_path = str(tmp_path / "queries.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    conn = db.open_existing(db_path)
    run = queries.resolve_run(conn)
    assert run is not None
    try:
        yield conn, run
    finally:
        conn.close()


# ── 只读：不写库 ──────────────────────────────────────────────────────


def test_queries_never_write(store):
    """只读层跑一遍全部查询函数后，四表行数与 `meta` 都不变。"""
    conn, run = store
    before = db.table_counts(conn)
    queries.runs(conn)
    queries.resolve_run(conn)
    queries.previous_run(conn, run.run_id)
    queries.tree_rows(conn, run.run_id)
    queries.summary(conn, run.run_id)
    queries.matrix_rows(conn, run.run_id, 20)
    queries.slow_rows(conn, run.run_id)
    queries.diff_rows(conn, run.run_id, run.run_id)
    for suite in queries.tree_rows(conn, run.run_id):
        for case in suite.cases:
            queries.case_detail(conn, run.run_id, case.case_id)
            queries.history(conn, case.case_id, 20)
    assert db.table_counts(conn) == before


def test_query_layer_holds_no_textual_object(store):
    """返回的是 dataclass / dict / 元组——**不含任何 Textual 对象**（分层判据）。"""
    conn, run = store
    import textual.widgets  # noqa: F401 - 反向对照：Textual 此刻是装着的

    values = [
        queries.resolve_run(conn, run.run_id),
        *queries.tree_rows(conn, run.run_id),
        queries.summary(conn, run.run_id),
        *queries.slow_rows(conn, run.run_id),
    ]
    for value in values:
        assert not type(value).__module__.startswith("textual"), type(value)


# ── summary 与直接 SQL 逐项相等（DoD）────────────────────────────────


def test_summary_equals_direct_sql(store):
    """`queries.summary` 的每个已实装字段都与一条直出的 SQL 相等。"""
    conn, run = store
    summary = queries.summary(conn, run.run_id)
    assert summary["total"] == conn.execute(
        "SELECT COUNT(*) FROM occurrences WHERE run_id = ?", (run.run_id,)).fetchone()[0]
    for status, field in (("fail", "fail"), ("skip", "skip")):
        expected = conn.execute(
            "SELECT COUNT(*) FROM occurrences WHERE run_id = ? AND status = ?",
            (run.run_id, status)).fetchone()[0]
        assert summary[field] == expected, field
    assert summary["total"] == 18 and summary["fail"] == 3 and summary["skip"] == 3


def test_summary_field_order_comes_from_rules(store):
    """键序 = 规则包的 `view.summary_fields`（"屏幕上先显示哪个"也只有一个来源）。"""
    conn, run = store
    from testdeck import rules
    fields = rules.load_view_rules()["summary_fields"]
    assert list(queries.summary(conn, run.run_id)) == fields


def test_pending_summary_fields_are_not_guessed(store):
    """六个 summary 字段 M5 起**全部实装**：没有任何一个是"待实装"的 ``None``。

    `flaky` / `broken` 由 `flaky.py` 填、`slow` 由 `slow.py` 填（阈值单点在规则包）。
    这条与 K37 同源：口径没实装时必须是 ``None``（不猜），实装后必须是**数**——
    所以这里断言"规则包声明的每个 summary 字段都拿到了数"。
    """
    conn, run = store
    summary = queries.summary(conn, run.run_id)
    # 没有"待实装"字段了（M5 收尾），规则包声明的六个字段全部有值
    assert queries.PENDING_SUMMARY_FIELDS == (), sorted(queries.PENDING_SUMMARY_FIELDS)
    for field in rules.load_view_rules()["summary_fields"]:
        assert summary[field] is not None, field
    # `slow` 的口径 = 本 run 里达到 `slow_ms` 的用例数（与 `slow.is_slow` 逐项相等）
    from testdeck import slow as _slow
    slow_rules = rules.load_slow_rules()
    expected = sum(
        1 for (time_ms,) in conn.execute(
            "SELECT time_ms FROM occurrences WHERE run_id = ? AND time_ms IS NOT NULL",
            (run.run_id,)).fetchall()
        if _slow.is_slow(time_ms, slow_rules))
    assert summary["slow"] == expected == 1


def test_flaky_and_broken_summary_fields_come_from_flaky_py(store):
    """`flaky` / `broken` 由 `flaky.py` 的判定结果计数——不是 `None`，也不是 SQL 直出。

    三份真跑产物只有 1 个 run：每条用例 `counted_runs <= 1 < min_runs_for_flaky`，
    故一律 `watch`，`flaky` / `broken` 都是 0。这条同时钉住"summary 的 flaky 数与
    矩阵里标 flaky 的行数同源"（同一份判定）。
    """
    conn, run = store
    summary = queries.summary(conn, run.run_id)
    assert summary["flaky"] == 0 and summary["broken"] == 0
    profiles = queries.case_profiles(conn, run.run_id, 20)
    assert profiles, "分型面为空（判据失效）"
    assert sum(1 for p in profiles.values() if p.label == "flaky") == summary["flaky"]
    assert sum(1 for p in profiles.values() if p.label == "broken") == summary["broken"]
    _, rows = queries.matrix_rows(conn, run.run_id, 20)
    assert sum(1 for r in rows if r.label == "flaky") == summary["flaky"]
    assert sum(1 for r in rows if r.label == "broken") == summary["broken"]


# ── 失败优先排序（单点）────────────────────────────────────────────────


def test_tree_rows_put_failing_subtrees_first(store):
    """同一父节点下 `fail_count > 0` 的子树在前；组内 suite 按 XML 出现序升序。"""
    conn, run = store
    suites = queries.tree_rows(conn, run.run_id)
    fail_flags = [suite.fail_count > 0 for suite in suites]
    assert fail_flags == sorted(fail_flags, reverse=True), fail_flags
    # 三份产物各一个 suite，各带 1 条失败 -> 全在"失败"组，组内按 suite_id（XML 序）
    assert [suite.suite_id for suite in suites] == sorted(s.suite_id for s in suites)


def test_case_order_is_fail_first_then_lexical(store):
    """class 内：失败的用例在前，组内按 `name` 字典序。"""
    conn, run = store
    for suite in queries.tree_rows(conn, run.run_id):
        for classname, cases in suite.class_groups:
            fails = [case.name for case in cases if case.failed]
            rest = [case.name for case in cases if not case.failed]
            assert [case.name for case in cases] == fails + rest, (suite.name, classname)
            assert fails == sorted(fails) and rest == sorted(rest)


def test_class_order_is_fail_first_then_lexical(store):
    """class 层：有失败的 class 在前，组内按 `classname` 字典序。"""
    conn, run = store
    for suite in queries.tree_rows(conn, run.run_id):
        flags = [any(case.failed for case in cases) for _name, cases in suite.class_groups]
        assert flags == sorted(flags, reverse=True), (suite.name, flags)
        # 直接钉住：在"有失败"与"无失败"两个组内，classname 都是升序
        for has_fail in (True, False):
            names = [name for name, cases in suite.class_groups
                     if any(case.failed for case in cases) == has_fail]
            assert names == sorted(names), (suite.name, has_fail, names)


def test_fail_first_key_is_the_single_sort_point():
    """排序键的行为：失败计数 > 0 排前（组内按 secondary 升序），失败组内也按 secondary。"""
    assert queries.fail_first_key(3, "z") < queries.fail_first_key(0, "a")
    assert queries.fail_first_key(1, "b") > queries.fail_first_key(1, "a")
    assert queries.fail_first_key(0, "b") > queries.fail_first_key(0, "a")
    assert sorted([queries.fail_first_key(0, "b"), queries.fail_first_key(0, "a")]) == \
        [(1, "a"), (1, "b")]


def test_tree_rows_does_not_drop_cases(store):
    """树上用例数 == occurrences 行数（防"排序时丢行"）。"""
    conn, run = store
    on_tree = sum(len(suite.cases) for suite in queries.tree_rows(conn, run.run_id))
    in_db = conn.execute("SELECT COUNT(*) FROM occurrences WHERE run_id = ?",
                         (run.run_id,)).fetchone()[0]
    assert on_tree == in_db == 18


def test_class_groups_are_contiguous(store):
    """同一 classname 的行在 `SuiteRow.cases` 里必须连续（呈现层靠这个切节点）。"""
    conn, run = store
    for suite in queries.tree_rows(conn, run.run_id):
        names = [case.classname for case in suite.cases]
        seen = []
        for name in names:
            if not seen or seen[-1] != name:
                seen.append(name)
        assert len(seen) == len(set(seen)), (suite.name, names)


# ── 缺失耗时 / 矩阵原料 / diff 原料 ───────────────────────────────────


def test_slow_rows_exclude_null_time(store):
    """`time_ms IS NULL` 的行不进慢测试表（"没声明耗时" ≠ "耗时 0"，K28）。"""
    conn, run = store
    rows = queries.slow_rows(conn, run.run_id)
    assert rows, "三份真跑产物都有耗时声明"
    assert all(row.time_ms is not None for row in rows)
    assert [row.time_ms for row in rows] == sorted((row.time_ms for row in rows), reverse=True)
    assert len(rows) == 18


def test_matrix_rows_are_raw_statuses(store):
    """矩阵：列 = 窗口内 run，行 = 用例，单元格是四态原样；行序 = flaky_score 降序。

    M3 的行序是"失败次数降序"；M4 起改成 `flaky_score` 降序（`plan/03` 模块③）。
    单元格仍是**四态原样**——分型只挂在 `row.profile` 上，不改状态本身。
    """
    conn, run = store
    columns, rows = queries.matrix_rows(conn, run.run_id, 20)
    assert [column.run_id for column in columns] == [run.run_id]
    assert len(rows) == 18
    assert all(len(row.statuses) == 1 for row in rows)
    scores = [row.flaky_score for row in rows]
    assert scores == sorted(scores, reverse=True), scores
    assert all(row.profile is not None for row in rows), "每行都要带分型（M4）"
    # 每条用例只有 1 次 run 参与计数（n=1 < min_runs_for_flaky）→ 一律 watch
    assert {row.label for row in rows} == {"watch"}, sorted({row.label for row in rows})



def test_matrix_rows_zero_window_is_empty_not_crash(store):
    """窗口内没有 run 时返回空列表（呈现层据此显示"窗口内没有 run"）。"""
    conn, run = store
    columns, rows = queries.matrix_rows(conn, run.run_id, 0)
    assert columns == [] and rows == []


def test_diff_rows_show_raw_status_pairs(store):
    """同一 run 与自身 diff：每条用例都是 `x→x`（原始状态对，分类留给 M4）。"""
    conn, run = store
    rows = queries.diff_rows(conn, run.run_id, run.run_id)
    assert len(rows) == 18
    assert all(row.status_before == row.status_after for row in rows)
    assert not any(row.changed for row in rows)


def test_diff_rows_report_missing_side(store):
    """任一侧缺行 → 该侧 ``None``（不补 0，也不当成"未跑"之外的任何东西）。"""
    conn, run = store
    case = queries.tree_rows(conn, run.run_id)[0].cases[0]
    rows = queries.diff_rows(conn, run.run_id + 1, run.run_id)
    target = next(row for row in rows if row.case_id == case.case_id)
    assert target.status_before is None and target.status_after == case.status


# ── run 解析 / 历史 ───────────────────────────────────────────────────


def test_resolve_run_defaults_to_latest_and_handles_bad_id(store):
    conn, run = store
    assert queries.resolve_run(conn).run_id == run.run_id
    assert queries.resolve_run(conn, run.run_id).run_id == run.run_id
    # 非整数 / 不存在的 run 一律"查不到"（调用方给退出码 3，不抛异常）
    assert queries.resolve_run(conn, "nope") is None
    assert queries.resolve_run(conn, 9999) is None


def test_previous_run_of_first_is_none(store):
    conn, run = store
    assert queries.previous_run(conn, run.run_id) is None


def test_history_is_ascending_by_run_id(store):
    """历史按 `run_id` **升序**：产物没写 `timestamp` 时它是唯一稳定的次序（K26）。"""
    conn, run = store
    case = queries.tree_rows(conn, run.run_id)[0].cases[0]
    history = queries.history(conn, case.case_id, 20)
    assert history == [(run.run_id, case.status)]


# ── 慢测试画像（M5）：回归判定接真实库 ───────────────────────────────


def _two_run_store(repo_root, tmp_path):
    """造一个**两次 run** 的库：第二次的耗时明显抬升（回归可判）。

    做法：写两份 XML（身份三元组不同），各自一个 suite / 一条同名用例；
    前段 1000ms、后段 1500ms —— ratio 1.5、delta 500ms，两条门槛都过。
    """
    from testdeck import db as _db

    def _xml(commit, ms):
        return (
            '<?xml version="1.0"?><testsuites>'
            '<testsuite name="s" tests="1" failures="0" errors="0" skipped="0" '
            'time="%.3f" branch="main" commit="%s" ci_run_id="%s">'
            '<testcase classname="C" name="t" time="%.3f"/>'
            '</testsuite></testsuites>' % (ms / 1000.0, commit, commit, ms / 1000.0)
        )

    db_path = str(tmp_path / "two_runs.db")
    first = tmp_path / "a.xml"
    second = tmp_path / "b.xml"
    first.write_text(_xml("0" * 39 + "1", 1000), encoding="utf-8")
    second.write_text(_xml("0" * 39 + "2", 1500), encoding="utf-8")
    assert cli.main(["ingest", str(first), "--db", db_path]) == exit_codes.OK
    assert cli.main(["ingest", str(second), "--db", db_path]) == exit_codes.OK
    conn = _db.open_existing(db_path)
    return conn, queries.resolve_run(conn)


def test_slow_profiles_detect_regression_on_real_store(repo_root, tmp_path):
    """**回归判定接真实库**：两次 run、耗时从 1000ms 抬到 1500ms → `regression is True`。

    - 窗口内全部样本（1000, 1500）的 p50 = 1250（线性插值的中点）、p95 = 1475；
    - 切分点 = 窗口中点（2 个 run → split=1）：`base_p50=1000`、`curr_p50=1500`；
    - ratio 1.5 ≥ 1.2 且 delta 500ms ≥ 200ms → 判回归。
    """
    conn, run = _two_run_store(repo_root, tmp_path)
    try:
        rows = queries.slow_rows(conn, run.run_id, window=20)
        assert len(rows) == 1, rows
        profile = rows[0].profile
        assert profile is not None
        assert profile.p50 == 1250 and profile.p95 == Fraction(1475, 1)
        assert profile.regression is True, (profile.base_p50, profile.curr_p50, profile.note)
        assert profile.regression_text == "yes"
        # 判定只调 slow.py：切分点 = 窗口中点（两次 run -> split=1）
        assert profile.base_p50 == 1000 and profile.curr_p50 == 1500
        assert profile.label == ""
    finally:
        conn.close()


def test_slow_profiles_are_single_sample_on_single_run(store):
    """单 run 库：窗口只有 1 个耗时样本 → 回归判不了（`None`），标注 `single_sample`。"""
    conn, run = store
    rows = queries.slow_rows(conn, run.run_id, window=20)
    assert rows
    for row in rows:
        assert row.profile is not None
        assert row.regression is None
        assert row.label == "single_sample"
        assert row.profile.p50 == row.profile.p95 == row.time_ms
