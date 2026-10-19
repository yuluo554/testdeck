"""呈现层纯函数（`plan/03` 模块② 的两条降级 + 各视图渲染）。

两条降级（窄终端单栏 / `NO_COLOR` 颜色退化）**都不依赖 Pilot**——这是 `plan/03` 的
硬要求：行为判据得能在没有终端的情况下跑红。
"""

import pytest

from testdeck import model, queries, rules
from testdeck.tui import view


def _view_rules():
    return rules.load_view_rules()


def _case(**kwargs):
    base = dict(case_id=1, suite_name="s", classname="C", name="t", status=model.STATUS_PASS,
                time_ms=1, failure_type="", failure_message="", stack_first_line="")
    base.update(kwargs)
    return queries.CaseRow(**base)


def _suite(cases, name="s", suite_id=1):
    return queries.SuiteRow(suite_id, name, "p.xml", 10, len(cases), 0, 0, 0, tuple(cases))


# ── 降级 ①：窄终端 → 单栏 ─────────────────────────────────────────────


@pytest.mark.parametrize("width,expected", [
    (120, view.THREE_COLUMN),
    (80, view.THREE_COLUMN),      # 恰好等于门槛 -> 三栏（判据是 `<`）
    (79, view.SINGLE_COLUMN),
    (40, view.SINGLE_COLUMN),
    (0, view.SINGLE_COLUMN),
])
def test_column_mode_threshold(width, expected):
    assert view.column_mode(width, _view_rules()) == expected


def test_column_mode_threshold_comes_from_rules():
    """门槛值来自 `rules/view.json`，代码里不出现宽度字面量。"""
    custom = dict(_view_rules())
    custom["min_width_single_column"] = 100
    assert view.column_mode(99, custom) == view.SINGLE_COLUMN
    assert view.column_mode(100, custom) == view.THREE_COLUMN


# ── 降级 ②：NO_COLOR / 无真彩色 → 颜色退化 ────────────────────────────


@pytest.mark.parametrize("env,isatty,expected", [
    ({"COLORTERM": "truecolor", "TERM": "xterm-256color"}, True, view.COLOR),
    ({"NO_COLOR": "1", "COLORTERM": "truecolor", "TERM": "xterm"}, True, view.MONO),
    ({"NO_COLOR": "", "COLORTERM": "truecolor", "TERM": "xterm"}, True, view.MONO),
    ({"COLORTERM": "truecolor", "TERM": "xterm"}, False, view.MONO),
    ({"COLORTERM": "truecolor", "TERM": "dumb"}, True, view.MONO),
    ({"TERM": "xterm-256color"}, True, view.MONO),
    ({}, True, view.MONO),
])
def test_style_mode_matrix(env, isatty, expected):
    assert view.style_mode(env, isatty) == expected


def test_color_never_loses_structure():
    """颜色退化只去"色"：把标记剥掉后，两种模式的文本**逐字符相同**。

    这是"保留结构、颜色退化"的可跑红判据（不是靠肉眼看截图）。
    用例取**有失败**的数据：有色调时彩色模式才会真的带标记（否则两模式本来就同形）。
    """
    case = _case(status=model.STATUS_FAIL, stack_first_line="boom", failure_message="AssertionError")
    suite = _suite([case], name="s [1/1]")
    history = [(1, model.STATUS_FAIL), (2, model.STATUS_PASS)]
    summary = {"total": 3, "fail": 1, "skip": 0, "flaky": None, "broken": None, "slow": None}
    fields = ("total", "fail", "skip", "flaky", "broken", "slow")
    renderers = [
        ("summary", lambda style: view.summary_text(summary, fields, style)),
        ("suite", lambda style: view.suite_label(suite, style)),
        ("class", lambda style: view.class_label("C", (case,), style)),
        ("case", lambda style: view.case_label(case, style)),
        ("detail", lambda style: view.detail_text(case, style)),
        ("sparkline", lambda style: view.sparkline_text(history, style)),
        ("help", lambda style: view.help_text(style)),
        ("aggregate", lambda style: view.aggregate_text("C", (case,), style)),
        ("run", lambda style: view.run_header_text(
            queries.RunRow(1, "", "", "", "", "pytest", "a.xml"), style)),
    ]
    for name, render in renderers:
        colored = render(view.COLOR)
        mono = render(view.MONO)
        assert colored != mono, "%s：彩色模式没带标记（降级判据空转）" % name
        assert view.strip_markup(colored) == view.strip_markup(mono), name
        assert not view.has_markup(mono), "%s：退化模式不该自己带标记" % name


def test_data_brackets_are_escaped_not_parsed_as_markup():
    """用例名里的 `[` 必须被转义：否则 `[1]` 会被 Rich 当成标记吃掉。"""
    case = _case(name="test_param[1]", status=model.STATUS_FAIL)
    rendered = view.case_label(case, view.COLOR)
    assert view.strip_markup(rendered) == case.label
    assert "test_param[1]" in view.strip_markup(rendered)


def test_strip_markup_keeps_escaped_brackets():
    assert view.strip_markup(view.markup("a[1]", view.COLOR, "red")) == "a[1]"
    assert view.strip_markup(view.markup("a[1]", view.MONO)) == "a[1]"


# ── summary / 未实装字段 ──────────────────────────────────────────────


def test_summary_pending_fields_are_labelled_not_faked():
    """`flaky`/`broken`/`slow` 显示为 `—` 且带"待实装"标注（不冒充有值）。"""
    summary = {"total": 4, "fail": 1, "skip": 0, "flaky": None, "broken": None, "slow": None}
    text = view.summary_text(summary, list(summary), view.MONO)
    assert "—" in text and "待实装" in text
    assert "flaky" in text and "broken" in text and "slow" in text


def test_summary_field_order_is_rendered_as_given():
    summary = {"total": 1, "fail": 2, "skip": 3, "flaky": None, "broken": None, "slow": None}
    text = view.summary_text(summary, ("skip", "total"), view.MONO)
    assert text.index("skip") < text.index("total")


# ── 缺失耗时显示 ──────────────────────────────────────────────────────


def test_missing_time_is_shown_as_dash_not_zero():
    """缺失耗时显示 `—`，绝不显示 0（"没声明"与"0 毫秒"是两件事，K28）。"""
    assert view.time_text(None) == "—"
    assert view.time_text(0) == "0 ms"
    assert "0 ms" in view.detail_text(_case(time_ms=0), view.MONO)
    assert "—" in view.detail_text(_case(time_ms=None), view.MONO)


# ── sparkline 口径 ────────────────────────────────────────────────────


def test_sparkline_skips_non_counted_runs():
    """pass=1 / fail=0；skip / missing **不绘制**（与 flaky 分母同源口径）。"""
    history = [(1, model.STATUS_PASS), (2, model.STATUS_SKIP), (3, model.STATUS_FAIL),
               (4, model.STATUS_MISSING), (5, model.STATUS_PASS)]
    values, skipped = view.sparkline_series(history)
    assert values == [1.0, 0.0, 1.0]
    assert skipped == 2
    assert "3 次参与计数" in view.sparkline_text(history, view.MONO)


def test_sparkline_of_empty_history_is_empty():
    assert view.sparkline_series([]) == ([], 0)


# ── F / S / D 渲染 ────────────────────────────────────────────────────


def test_matrix_text_uses_status_glyphs_single_source():
    """矩阵字形取自 `model.STATUS_GLYPHS`（单点），且画出 `flaky.py` 的分型标签。"""
    from testdeck import flaky, model as _model

    def _profile(label, score):
        return flaky.CaseProfile(label=label, counted_runs=4, passes=2, fails=2,
                                 fail_rate=_model.as_fraction("0.5"), transitions=2,
                                 flaky_score=_model.as_fraction(score))

    columns = [queries.RunRow(1, "", "", "", "", "pytest", "a.xml")]
    rows = [queries.MatrixRow(1, "s", "C", "t", (model.STATUS_FAIL,),
                              _profile("flaky", "1/3")),
            queries.MatrixRow(2, "s", "C", "u", (None,), _profile("broken", "0"))]
    text = view.matrix_text(columns, rows, view.MONO)
    assert model.STATUS_GLYPHS[model.STATUS_FAIL] in text
    assert "flaky" in text and "broken" in text, text
    assert "1/3" in text, text
    for glyph in (model.STATUS_GLYPHS[model.STATUS_PASS], model.STATUS_GLYPHS[model.STATUS_SKIP]):
        assert glyph in text


def test_matrix_text_handles_rows_without_profile():
    """没有分型的行也要画得出来（``profile=None`` → 标签/分数显示 `—`，不崩）。"""
    columns = [queries.RunRow(1, "", "", "", "", "pytest", "a.xml")]
    rows = [queries.MatrixRow(1, "s", "C", "t", (model.STATUS_FAIL,))]
    text = view.matrix_text(columns, rows, view.MONO)
    assert "—" in text and "t" in text


def test_matrix_text_of_empty_window_says_so():
    assert "没有 run" in view.matrix_text([], [], view.MONO)


def test_slow_text_excludes_nulls_and_states_pending():
    """行序由 `queries.slow_rows` 的 SQL 决定（降序）；呈现层不重排。

    M5 起每行还带 `slow.py` 的 p50/p95 与回归标记（挂在 `row.profile` 上）。
    """
    rows = [queries.SlowRow(2, "s", "C", "slow", 1000), queries.SlowRow(1, "s", "C", "fast", 10)]
    text = view.slow_text(rows, view.MONO)
    lines = text.splitlines()
    assert "1000 ms" in lines[0] and "10 ms" in lines[1], lines
    assert "p50" in text and "p95" in text and "reg" in text
    assert "slow.py" in text


def test_slow_text_of_empty_rows_is_explicit():
    assert "没有声明耗时" in view.slow_text([], view.MONO)


def test_diff_text_marks_missing_side_and_classifies():
    """`D` 视图按 `diff.py` 的三类分组；缺行照旧画 `(缺)`，且分类不误判为"修复"。"""
    rows = [queries.DiffRow(1, "s", "C", "t", model.STATUS_PASS, None),
            queries.DiffRow(2, "s", "C", "u", model.STATUS_PASS, model.STATUS_FAIL),
            queries.DiffRow(3, "s", "C", "v", model.STATUS_FAIL, model.STATUS_PASS)]
    text = view.diff_text(rows, view.MONO)
    assert "pass→(缺)" in text
    # 三类标题都在（新增失败 / 修复 / 仍失败）
    from testdeck import diff as _diff
    for kind in _diff.RECONCILED_CLASSES:
        assert _diff.CLASS_TITLES[kind] in text, kind
    # pass→fail 落"新增失败"桶；fail→pass 落"修复"桶
    assert "新增失败（1）" in text
    assert "修复（1）" in text
    assert "仍失败（0）" in text


# ── 帮助层来自 keys.py ────────────────────────────────────────────────


def test_help_text_covers_every_binding():
    from testdeck import keys
    text = view.help_text(view.MONO)
    for label, _description in keys.KEYS:
        assert label in text, label
    assert "keys.py" in text
