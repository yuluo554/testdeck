"""Textual 三栏工作台（`plan/03` 模块②）：组装控件 + 事件，别的什么都不做。

装配纪律（都是可跑红的判据，不是口头约定）：

- **键位全部来自 `keys.py`**：``BINDINGS`` 由 ``keys.BINDINGS`` 生成，Footer 与帮助层
  用 ``keys.KEYS``。任何地方另写键位字面量都会被 `tests/test_keys_single_source.py` 扫红。
- **大库查询走 worker 线程**：``@work(thread=True)`` + ``post_message``，UI 不阻塞；
  线程里每次自开一条**已存在的**库连接（sqlite 连接不跨线程复用）。
- **两条降级由 `view.py` 的纯函数决定**（窄终端 → 单栏；`NO_COLOR`/无真彩色 → 颜色退化），
  这里只把结果落到 CSS 类上——所以两条降级都有不依赖 Pilot 的单元测试。
- **summary 从 `report_model.build_report` 取**（与 M5 的导出同一模型；
  `tests/test_layering.py` 断言这条引用还在）。
- `F`/`S`/`D` 是**同屏切换的主区域**，三者都渲染真实查询结果（死壳判据见 `plan/03`）。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Sparkline, Static, Tree

from .. import db, exit_codes, keys, queries, report_model, rules
from . import view


# ── 数据装载（模块级纯函数：可以在没有 App 的情况下测试）────────────────


def load_report(db_path, run_id=None, window=None):
    """打开**已存在**的库，组装一次报告（含树与历史）。库/run 不可用 → `DbError`/`ReportError`。"""
    conn = db.open_existing(db_path)
    try:
        return report_model.build_report(conn, run_id, window)
    finally:
        conn.close()


def load_view(db_path, kind, run_id):
    """取 F/S/D 三个视图的原料（只取数：分型/分位数/分类都不在这里）。"""
    conn = db.open_existing(db_path)
    try:
        if kind == "flaky":
            window = rules.load_view_rules()["sparkline_runs"]
            return queries.matrix_rows(conn, run_id, window)
        if kind == "slow":
            return queries.slow_rows(conn, run_id)
        before = queries.previous_run(conn, run_id)
        if before is None:
            return None
        return queries.diff_rows(conn, before.run_id, run_id)
    finally:
        conn.close()


# ── 消息 ──────────────────────────────────────────────────────────────


class ReportLoaded(Message):
    def __init__(self, report):
        self.report = report
        super().__init__()


class LoadFailed(Message):
    def __init__(self, detail):
        self.detail = detail
        super().__init__()


class ViewLoaded(Message):
    def __init__(self, kind, payload=None, detail=""):
        self.kind = kind
        self.payload = payload
        self.detail = detail
        super().__init__()


@dataclass(frozen=True)
class NodeData:
    """树节点的载荷（渲染标签需要的全部信息；不持有控件引用）。"""

    kind: str                      # "suite" / "class" / "case"
    name: str
    case: Optional[queries.CaseRow] = None
    cases: Tuple[queries.CaseRow, ...] = ()


class HelpScreen(ModalScreen):
    """帮助层：内容由 `view.help_text` 从 `keys.KEYS` 生成（键位只有一份来源）。"""

    BINDINGS = [
        Binding(keys.BINDINGS["back"], "dismiss", keys.description_for("back")),
        Binding(keys.BINDINGS["quit"], "dismiss", keys.description_for("quit")),
        Binding(keys.BINDINGS["enter"], "dismiss", keys.description_for("enter")),
        Binding(keys.BINDINGS["help"], "dismiss", keys.description_for("help")),
    ]

    def __init__(self, text):
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static(self._text, id="help")

    def action_dismiss(self):
        self.dismiss(None)


# ── App ───────────────────────────────────────────────────────────────


class TestDeckApp(App):
    #: 类名以 `Test` 开头会让 pytest 试图收集它（`PytestCollectionWarning`）——
    #: 显式声明"这不是测试类"，把噪声关掉而不是让每次跑测试都带一条警告。
    __test__ = False

    CSS = """
    #body { height: 1fr; }
    #tree { width: 2fr; border: round $accent; }
    #right { width: 3fr; }
    #summary { height: auto; padding: 0 1; }
    #failure { height: 1fr; padding: 0 1; border-top: solid $panel; }
    #spark { height: 3; padding: 0 1; }
    #search { display: none; }
    #view-body { display: none; height: 1fr; padding: 0 1; border: round $accent; overflow: auto; }
    Screen.view-open #body { display: none; }
    Screen.view-open #view-body { display: block; }
    Screen.single-column #right { display: none; }
    Screen.mono #summary, Screen.mono #failure, Screen.mono #view-body { color: auto; }
    """

    #: 键位来自 `keys.BINDINGS`；`enter` 用 priority 抢在 Tree 自己的 enter 之前
    BINDINGS = [
        Binding(key, action, keys.description_for(action),
                priority=(action == "enter"))
        for action, key in keys.BINDINGS.items()
    ]

    def __init__(self, db_path, run_id=None, env=None, isatty=None):
        super().__init__()
        self.db_path = db_path
        self.requested_run = run_id
        self._env = env
        self._isatty = isatty
        self.report: Optional[Dict[str, object]] = None
        self.run_row: Optional[queries.RunRow] = None
        self.suites: List[queries.SuiteRow] = []
        self.current_case: Optional[queries.CaseRow] = None
        self.view_mode = ""
        self.nav_nodes: List = []
        self.nav_index = 0

    # ── 装配 ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            yield Tree("suite → class → test", id="tree")
            with Vertical(id="right"):
                yield Static("加载中…", id="summary")
                yield Static("", id="failure")
                yield Sparkline([], id="spark")
        yield Static("", id="view-body")
        yield Input(placeholder="过滤用例名（Enter 跳转，Esc 关闭）", id="search")
        yield Footer()

    def on_mount(self):
        tree = self.query_one("#tree", Tree)
        # 导航完全由 keys.py 的键驱动（树自己的方向键/enter 不再参与），
        # 否则"树光标的位置"与"我们记的 nav_index"会各走各的。
        tree.can_focus = False
        # 搜索框**默认不可聚焦**：否则 Textual 会把首焦点给它，`j`/`F` 之类全被它吃掉
        # （实测：输入框里敲 `j` 只会多一个字符）。按 `/` 时才临时打开。
        self.query_one("#search", Input).can_focus = False
        tree.root.expand()
        self._apply_degradation()
        self._load_report(self.requested_run)

    def on_ready(self):
        """首帧之后把焦点清空——`App` 默认把焦点给第一个可聚焦控件，本项目不要焦点。"""
        self.set_focus(None)

    def on_resize(self, _event):
        self._apply_degradation()

    def _style(self):
        env = os.environ if self._env is None else self._env
        isatty = sys.stdout.isatty() if self._isatty is None else self._isatty
        return view.style_mode(env, isatty)

    def _apply_degradation(self):
        """把 `view.py` 的两个纯函数结果落到 CSS 类上（屏幕行为 = 被测试钉住的判据）。"""
        width = self.size.width or 0
        single = view.column_mode(width, rules.load_view_rules()) == view.SINGLE_COLUMN
        if self.screen is not None:
            self.screen.set_class(single, "single-column")
            self.screen.set_class(self._style() == view.MONO, "mono")

    # ── 取数（worker 线程；UI 不阻塞）─────────────────────────────────

    @work(thread=True, exclusive=True, group="report")
    def _load_report(self, run_id):
        try:
            report = load_report(self.db_path, run_id)
        except (db.DbError, report_model.ReportError) as exc:
            self.post_message(LoadFailed(str(exc)))
            return
        self.post_message(ReportLoaded(report))

    @work(thread=True, exclusive=True, group="view")
    def _load_view(self, kind):
        run = self.run_row
        if run is None:
            return
        try:
            payload = load_view(self.db_path, kind, run.run_id)
        except (db.DbError, report_model.ReportError) as exc:
            self.post_message(ViewLoaded(kind, detail=str(exc)))
            return
        self.post_message(ViewLoaded(kind, payload=payload))

    def on_report_loaded(self, message):
        self.report = message.report
        self.run_row = queries.RunRow(
            *[message.report["run"][field] for field in queries.RUN_FIELDS])
        self.suites = list(message.report["suites"])
        style = self._style()
        self.query_one("#summary", Static).update(
            view.run_header_text(self.run_row, style) + "\n"
            + view.summary_text(message.report["summary"],
                                report_model.summary_fields(), style))
        self._render_tree(style)

    def on_load_failed(self, message):
        self.query_one("#summary", Static).update(
            view.markup("无法加载：%s" % message.detail, self._style(), "bold red"))
        self.query_one("#failure", Static).update(
            view.markup("先跑 `testdeck ingest <产物...>` 把 run 落库，再打开 `testdeck tui`。",
                        self._style(), "dim"))

    def on_view_loaded(self, message):
        style = self._style()
        payload = message.payload
        if message.kind == "flaky":
            columns, rows = payload if payload else ([], [])
            body = view.matrix_text(columns, rows, style)
        elif message.kind == "slow":
            body = view.slow_text(payload or [], style)
        else:
            if payload is None:
                body = view.markup("窗口内只有一次 run：没有可 diff 的上一棒。", style, "dim")
            else:
                body = view.diff_text(payload, style)
        if message.detail:
            body = view.markup(message.detail, style, "bold red")
        self.query_one("#view-body", Static).update(
            view.markup(self._view_title(message.kind), style, "bold") + "\n" + body)

    # ── 树 ────────────────────────────────────────────────────────────

    def _render_tree(self, style):
        tree = self.query_one("#tree", Tree)
        tree.root.remove_children()
        nodes = []
        for suite in self.suites:
            suite_node = tree.root.add(Text.from_markup(view.suite_label(suite, style)),
                                       data=NodeData("suite", suite.name, cases=suite.cases))
            suite_node.expand()
            nodes.append(suite_node)
            for classname, cases in suite.class_groups:
                class_node = suite_node.add(
                    Text.from_markup(view.class_label(classname, cases, style)),
                    data=NodeData("class", classname, cases=tuple(cases)))
                class_node.expand()
                nodes.append(class_node)
                for case in cases:
                    case_node = class_node.add_leaf(
                        Text.from_markup(view.case_label(case, style)),
                        data=NodeData("case", case.name, case=case, cases=(case,)))
                    nodes.append(case_node)
        self.nav_nodes = nodes
        self.nav_index = 0
        if nodes:
            tree.move_cursor(nodes[0])
            self._select_index(0)

    def _select_index(self, index):
        if not self.nav_nodes:
            return
        index = max(0, min(index, len(self.nav_nodes) - 1))
        self.nav_index = index
        node = self.nav_nodes[index]
        self.query_one("#tree", Tree).move_cursor(node)
        data = node.data
        style = self._style()
        if data is not None and data.kind == "case":
            self.current_case = data.case
            self._show_case(data.case, style)
        else:
            self.current_case = None
            label = data.name if data is not None else ""
            self.query_one("#failure", Static).update(
                view.aggregate_text(label, data.cases if data else (), style))
            self.query_one("#spark", Sparkline).data = []

    def _show_case(self, case, style):
        self.query_one("#failure", Static).update(view.detail_text(case, style))
        history = (self.report or {}).get("history", {}).get(case.case_id, [])
        values, _skipped = view.sparkline_series(history)
        self.query_one("#spark", Sparkline).data = values
        if self.view_mode == "detail":
            self.query_one("#view-body", Static).update(
                view.markup("用例详情（单栏）", style, "bold") + "\n" + view.detail_text(case, style))

    def _move(self, delta):
        if self.view_mode:
            return
        self._select_index(self.nav_index + delta)

    # ── 视图切换（F / S / D：同屏主区域）──────────────────────────────

    _VIEW_TITLES = {
        "flaky": "flaky 矩阵（F）：test × run 四态",
        "slow": "慢测试（S）：p50/p95 与回归标记",
        "diff": "两次 run 的用例级 diff（D）",
        "detail": "用例详情",
    }

    def _view_title(self, kind):
        return self._VIEW_TITLES.get(kind, kind)

    def _open_view(self, kind):
        if self.run_row is None:
            return
        self.view_mode = kind
        if self.screen is not None:
            self.screen.add_class("view-open")
        self.query_one("#view-body", Static).update(
            view.markup(self._view_title(kind), self._style(), "bold") + "\n加载中…")
        if kind == "detail" and self.current_case is not None:
            self._show_case(self.current_case, self._style())
            return
        self._load_view(kind)

    def _close_view(self):
        if not self.view_mode:
            return
        self.view_mode = ""
        if self.screen is not None:
            self.screen.remove_class("view-open")

    # ── 动作（全部由 keys.py 的键触发）───────────────────────────────

    def action_down(self):
        self._move(1)

    def action_up(self):
        self._move(-1)

    def action_first(self):
        if not self.view_mode:
            self._select_index(0)

    def action_last(self):
        if not self.view_mode:
            self._select_index(len(self.nav_nodes) - 1)

    def action_enter(self):
        search = self.query_one("#search", Input)
        if search.display and search.has_focus:
            self._submit_search(search.value)
            return
        if self.view_mode:
            self._close_view()
            return
        single = self.screen.has_class("single-column") if self.screen else False
        if single and self.current_case is not None:
            self._open_view("detail")
            return
        node = self.nav_nodes[self.nav_index] if self.nav_nodes else None
        if node is not None and node.children:
            node.toggle()

    def action_flaky(self):
        self._open_view("flaky")

    def action_slow(self):
        self._open_view("slow")

    def action_diff(self):
        self._open_view("diff")

    def action_search(self):
        search = self.query_one("#search", Input)
        search.can_focus = True
        search.display = True
        search.focus()

    def action_export(self):
        self.notify("导出走 `testdeck export --format md|json [--fail-on ...]`（见 README）",
                    severity="information")

    def action_help(self):
        self.push_screen(HelpScreen(view.help_text(self._style())))

    def action_back(self):
        search = self.query_one("#search", Input)
        if search.display:
            search.display = False
            search.can_focus = False
            self.set_focus(None)
            return
        if self.view_mode:
            self._close_view()

    def action_quit(self):
        self.exit()

    # ── 搜索（`/`）───────────────────────────────────────────────────

    def _submit_search(self, term):
        search = self.query_one("#search", Input)
        search.display = False
        search.can_focus = False
        self.set_focus(None)
        term = (term or "").strip().lower()
        if not term:
            return
        for index, node in enumerate(self.nav_nodes):
            data = node.data
            if data is None:
                continue
            haystack = "::".join([data.name or "", data.case.classname if data.case else ""])
            if term in haystack.lower():
                self._close_view()
                self._select_index(index)
                self.notify("命中：%s" % (data.name or ""))
                return
        self.notify("没有匹配 `%s` 的用例" % term, severity="warning")

    def on_input_submitted(self, event):
        self._submit_search(event.value)


def run_tui(db_path, run_id=None, stream=None) -> int:
    """`testdeck tui` 的 CLI 入口：先验库/run（失败 → 3），再起 App。"""
    stream = stream or sys.stderr
    try:
        conn = db.open_existing(db_path)
    except db.DbError as exc:
        print("testdeck: %s" % exc, file=stream)
        return exit_codes.DEPENDENCY
    try:
        run = queries.resolve_run(conn, run_id)
    finally:
        conn.close()
    if run is None:
        print("testdeck: 库中没有可用的 run（%s）；先跑 `testdeck ingest <产物...>`。"
              % db_path, file=stream)
        return exit_codes.DEPENDENCY

    app = TestDeckApp(db_path, run_id=run.run_id)
    try:
        app.run()
    except Exception as exc:  # noqa: BLE001 - 终端不可用时报一句话给退出码 3，不把栈糊到用户脸上
        print("testdeck: 无法启动终端界面（%s: %s）" % (type(exc).__name__, exc), file=stream)
        return exit_codes.DEPENDENCY
    return exit_codes.OK
