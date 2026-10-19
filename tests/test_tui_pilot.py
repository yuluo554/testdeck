"""TUI Pilot：**纯键盘**完成"进入 → 移到失败用例 → 读到 stack 首行"（M3 DoD 第 3 条）。

还有两条 DoD 在这里落地：

- **summary 与直接 SQL 逐项相等**：屏幕上的数字与 `queries.summary`（进而与 SQL）
  逐项比——不是"看起来对"。
- **两条降级在真实 App 上生效**：窄终端（< `min_width_single_column`）→ 单栏类；
  `NO_COLOR` → mono 类（纯函数的判据在 `tests/test_view.py`，这里钉"确实落到了屏幕上"）。

Pilot 用的是 `run_test`（无头），所以这些用例在 CI 里也能跑，不需要真终端。
"""

import asyncio
import os

import pytest

from testdeck import cli, db, exit_codes, model, queries, report_model, rules
from testdeck.tui import view
from testdeck.tui.app import TestDeckApp

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)

#: 三份真跑产物：6+5+7 条用例，其中 3 条 fail（各一个 suite）
FAILING_NAMES = {
    "test_deliberate_failure_fixture",
    "TestDeliberateFailureFixture",
    "deliberate failure fixture: counter text",
}


@pytest.fixture
def db_path(repo_root, tmp_path):
    path = str(tmp_path / "pilot.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", path]) == exit_codes.OK
    return path


def _panel(app, selector):
    return str(app.query_one(selector).content)


async def _wait_for_report(app, pilot, tries=200):
    """等到报告装载完成（worker 线程回投 `ReportLoaded` 之后）再断言。

    `on_mount` 里的取数走 `@work(thread=True)`，一次 `pause()` 在满负载下**不足**
    以保证消息已回投（M4 实测：全量 pytest 下 `nav_nodes` 偶发为空）。这里轮询
    `app.report`，直到就绪或超时——判据是"报告真的到了"，不是"等固定帧数"。
    """
    for _ in range(tries):
        if app.report is not None:
            return
        await pilot.pause()
    raise AssertionError("报告在 %d 次 pause 内没有装载完成" % tries)


# ── 键盘全流程（DoD 第 3 条）──────────────────────────────────────────


def test_keyboard_only_flow_reaches_stack_first_line(db_path):
    """纯键盘：进 App → `j` 移到失败用例 → 右栏读到 stack 首行。"""

    async def flow():
        app = TestDeckApp(db_path, env={"COLORTERM": "truecolor", "TERM": "xterm"}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            assert app.nav_nodes, "树没建起来"
            # 纯键盘：一路 `j` 直到落在失败用例上（不许用鼠标/直接改索引）
            for _ in range(len(app.nav_nodes)):
                if app.current_case is not None and app.current_case.failed:
                    break
                await pilot.press("j")
                await pilot.pause()
            assert app.current_case is not None, "键盘走不到任何用例"
            assert app.current_case.failed, "键盘走不到失败用例：%s" % app.current_case.name
            assert app.current_case.name in FAILING_NAMES
            text = _panel(app, "#failure")
            assert "stack:" in text, text
            expected = app.current_case.stack_first_line
            assert expected and expected in text, (expected, text)
            # 右栏的 run 身份 + summary 也在（三栏不是"只有一棵树"）
            summary = _panel(app, "#summary")
            assert "run #" in summary and "total" in summary
            await pilot.press("q")
            await pilot.pause()

    asyncio.run(flow())


def test_fail_first_order_is_visible_on_screen(db_path):
    """屏幕上第一个**用例**节点就是失败用例（失败优先在 UI 上真的生效）。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            cases = [node.data for node in app.nav_nodes
                     if node.data is not None and node.data.kind == "case"]
            assert cases, "树里没有用例节点"
            assert cases[0].case.failed, cases[0].case.name
            await pilot.press("q")

    asyncio.run(flow())


def test_summary_panel_matches_direct_sql(db_path):
    """DoD：summary 面板上的每个已实装计数都与直接 SQL 相等。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            conn = db.open_existing(db_path)
            try:
                summary = queries.summary(conn, app.run_row.run_id)
                total = conn.execute(
                    "SELECT COUNT(*) FROM occurrences WHERE run_id = ?",
                    (app.run_row.run_id,)).fetchone()[0]
            finally:
                conn.close()
            panel = _panel(app, "#summary")
            assert summary["total"] == total == 18
            for field in ("total", "fail", "skip"):
                assert "%s %d" % (field, summary[field]) in panel, (field, panel)
            assert app.report["summary"] == summary
            await pilot.press("q")

    asyncio.run(flow())


# ── 三视图（死壳判据：只画标题不接查询 = 未交付）──────────────────────


def test_three_views_render_real_query_results(db_path):
    """`F`/`S`/`D` 三个视图都渲染**真实查询结果**（不是只有标题的死壳）。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            run_id = app.run_row.run_id
            conn = db.open_existing(db_path)
            try:
                columns, matrix = queries.matrix_rows(conn, run_id, 20)
                slow = queries.slow_rows(conn, run_id)
                diff = queries.diff_rows(conn, run_id, run_id)
            finally:
                conn.close()

            await pilot.press("F")
            for _ in range(60):
                await pilot.pause(0.02)
            body = _panel(app, "#view-body")
            assert app.view_mode == "flaky"
            assert body.splitlines()[0].startswith("flaky 矩阵")
            # 真的接了查询：矩阵里的每条用例身份都在（不是空标题）
            assert matrix, "矩阵原料为空"
            assert matrix[0].name in body, body[:200]
            assert model.STATUS_GLYPHS[model.STATUS_PASS] in body

            await pilot.press("escape")
            await pilot.pause()
            assert app.view_mode == "", "Esc 没回到三栏"

            await pilot.press("S")
            for _ in range(60):
                await pilot.pause(0.02)
            body = _panel(app, "#view-body")
            assert app.view_mode == "slow"
            assert body.splitlines()[0].startswith("慢测试")
            assert slow and slow[0].name in body, body[:200]
            assert "%d ms" % slow[0].time_ms in body
            # M5：`S` 视图不再只摆耗时——每条用例带 `slow.py` 的 p50/p95 与回归标记
            assert "p50=" in body and "p95=" in body, body[:300]
            assert "reg=" in body, body[:300]
            profile = slow[0].profile
            assert profile is not None, "慢测试画像没挂上（S 视图仍是死壳）"
            assert profile.p50_text in body, (profile.p50_text, body[:300])

            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("D")
            for _ in range(60):
                await pilot.pause(0.02)
            body = _panel(app, "#view-body")
            assert app.view_mode == "diff"
            assert body.splitlines()[0].startswith("两次 run")
            # 只有一次 run：D 视图必须明说"没有上一棒"，而不是画个空壳
            assert "没有可 diff 的上一棒" in body, body[:200]
            assert diff, "diff 原料为空"

            await pilot.press("escape")
            await pilot.pause()
            assert app.view_mode == ""
            await pilot.press("q")

    asyncio.run(flow())


def test_view_keys_only_toggle_main_area_not_new_screens(db_path):
    """`F`/`S`/`D` 是**同屏切换的主区域**（不 push 新屏），`?` 才是模态层。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            before = len(app.screen_stack)
            await pilot.press("F")
            for _ in range(40):
                await pilot.pause(0.02)
            assert len(app.screen_stack) == before, "F 不该 push 新屏"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert len(app.screen_stack) == before + 1, "? 应当 push 帮助层"
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == before
            await pilot.press("q")

    asyncio.run(flow())


# ── 两条降级在真实 App 上生效 ─────────────────────────────────────────


def test_narrow_terminal_switches_to_single_column(db_path):
    """窄终端（< 门槛）→ 单栏类生效，右栏隐藏，`Enter` 进详情页。"""

    async def flow():
        width = rules.load_view_rules()["min_width_single_column"] - 1
        app = TestDeckApp(db_path, env={"COLORTERM": "truecolor", "TERM": "xterm"}, isatty=True)
        async with app.run_test(size=(width, 30)) as pilot:
            await _wait_for_report(app, pilot)
            assert app.screen.has_class("single-column"), sorted(app.screen.classes)
            assert not app.query_one("#right").display, "单栏模式右栏应当隐藏"
            for _ in range(len(app.nav_nodes)):
                if app.current_case is not None:
                    break
                await pilot.press("j")
                await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.view_mode == "detail", app.view_mode
            assert app.current_case.name in _panel(app, "#view-body")
            await pilot.press("escape")
            await pilot.pause()
            assert app.view_mode == ""
            await pilot.press("q")

    asyncio.run(flow())


def test_wide_terminal_keeps_three_columns(db_path):
    """宽终端（= 门槛）→ 三栏（判据是 `<`，恰好等于门槛不算窄）。"""

    async def flow():
        width = rules.load_view_rules()["min_width_single_column"]
        app = TestDeckApp(db_path, env={"COLORTERM": "truecolor", "TERM": "xterm"}, isatty=True)
        async with app.run_test(size=(width, 30)) as pilot:
            await _wait_for_report(app, pilot)
            assert not app.screen.has_class("single-column"), sorted(app.screen.classes)
            assert app.query_one("#right").display
            await pilot.press("q")

    asyncio.run(flow())


def test_no_color_degrades_colors_but_keeps_structure(db_path):
    """`NO_COLOR=1` → mono 类生效；结构（计数/身份/stack）一个都不少。"""

    async def flow():
        app = TestDeckApp(db_path, env={"NO_COLOR": "1"}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            assert app.screen.has_class("mono"), sorted(app.screen.classes)
            summary = _panel(app, "#summary")
            assert "total 18" in summary and "fail 3" in summary
            for _ in range(len(app.nav_nodes)):
                if app.current_case is not None and app.current_case.failed:
                    break
                await pilot.press("j")
                await pilot.pause()
            text = _panel(app, "#failure")
            assert app.current_case.stack_first_line in text
            assert "stack:" in text
            await pilot.press("q")

    asyncio.run(flow())


def test_sparkline_widget_is_wired_to_real_history(db_path):
    """sparkline 控件的数据来自**真实历史查询**（DoD 的"接真实查询"，不是只摆个空控件）。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            # 先落到一条**失败**用例上（这样序列里应当有 0.0，而不是空列表）
            for _ in range(len(app.nav_nodes)):
                if app.current_case is not None and app.current_case.failed:
                    break
                await pilot.press("j")
                await pilot.pause()
            case = app.current_case
            assert case is not None and case.failed
            conn = db.open_existing(db_path)
            try:
                history = queries.history(conn, case.case_id,
                                          rules.load_view_rules()["sparkline_runs"])
            finally:
                conn.close()
            expected, _skipped = view.sparkline_series(history)
            assert app.query_one("#spark").data == expected, (expected, app.query_one("#spark").data)
            assert expected == [0.0], "该用例在本 run 是 fail，序列应为 [0.0]"
            # 移到非失败用例上：序列随之变化（证明它跟着光标走，不是一次性快照）
            await pilot.press("k")
            await pilot.pause()
            assert app.query_one("#spark").data != expected
            await pilot.press("q")

    asyncio.run(flow())


def test_footer_key_bar_is_rendered_from_keys(db_path):
    """键位栏（Footer）在屏上，且每个动作的文案都来自 `keys.KEYS`。"""

    async def flow():
        from testdeck import keys
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(140, 40)) as pilot:
            await _wait_for_report(app, pilot)
            # Footer 的数据源就是 App 的 active bindings（Textual 从 `BINDINGS` 生成）
            shown = {binding.binding.description for _key, binding in app.active_bindings.items()
                     if binding.binding.show and binding.binding.description}
            for action in keys.BINDINGS:
                description = keys.description_for(action)
                assert description, action
                assert description in shown, (action, description, sorted(shown))
            await pilot.press("q")

    asyncio.run(flow())


# ── 搜索（`/`）也走键盘 ───────────────────────────────────────────────


def test_search_jumps_to_matching_case(db_path):
    """`/` → 打字 → Enter：光标落到命中的用例上（纯键盘）。"""

    async def flow():
        app = TestDeckApp(db_path, env={}, isatty=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await _wait_for_report(app, pilot)
            await pilot.press("slash")
            await pilot.pause()
            assert app.query_one("#search").display
            for char in "deliberate":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            assert app.current_case is not None
            assert "deliberate" in app.current_case.name.lower(), app.current_case.name
            assert not app.query_one("#search").display, "提交后搜索框应当收起"
            await pilot.press("q")

    asyncio.run(flow())


# ── 库不可用 → 退出码 3（不是 4，也不是崩溃）────────────────────────


def test_tui_on_missing_db_is_dependency_error(tmp_path):
    """库不存在 → 退出码 3 且 stderr 点名"先跑 ingest"（`plan/03` 模块⑤ 降级条）。"""
    import io
    stream = io.StringIO()
    code = __import__("testdeck.tui.app", fromlist=["run_tui"]).run_tui(
        str(tmp_path / "nope.db"), stream=stream)
    assert code == exit_codes.DEPENDENCY
    assert "ingest" in stream.getvalue()


def test_tui_on_empty_db_is_dependency_error(tmp_path):
    """库存在但没有 run → 退出码 3（空库不等于"没有失败"，K30 的读取侧）。"""
    import io
    db_path = str(tmp_path / "empty.db")
    conn = db.connect(db_path)
    conn.close()
    stream = io.StringIO()
    code = __import__("testdeck.tui.app", fromlist=["run_tui"]).run_tui(db_path, stream=stream)
    assert code == exit_codes.DEPENDENCY
    assert "没有可用的 run" in stream.getvalue()


def test_tui_on_unknown_run_is_dependency_error(db_path):
    """`--run` 指向不存在的 run → 退出码 3。"""
    import io
    stream = io.StringIO()
    code = __import__("testdeck.tui.app", fromlist=["run_tui"]).run_tui(
        db_path, run_id=4242, stream=stream)
    assert code == exit_codes.DEPENDENCY


def test_load_report_matches_report_model(db_path):
    """取数入口 `load_report` 与 `report_model.build_report` 同形（无头通路）。"""
    from testdeck.tui.app import load_report
    report = load_report(db_path)
    conn = db.open_existing(db_path)
    try:
        expected = report_model.build_report(conn)
    finally:
        conn.close()
    assert report["run"] == expected["run"]
    assert report["summary"] == expected["summary"]
    assert report["cases"] == expected["cases"]
