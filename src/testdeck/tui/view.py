"""呈现层（纯函数，**不 import Textual**）：降级两条 + 各视图的文本渲染。

为什么把降级放在纯函数里：`plan/03` 模块② 要求"窄终端单栏"与"`NO_COLOR` 颜色退化"
**都要有不依赖 Pilot 的快照/单元测试**。`app.py` 只把这里的结果落到 CSS 类上——
于是"屏幕上的行为"和"单元测试钉住的判据"是同一份代码，不是两份。

配色只在"色"这一维退化：``mono`` 下渲染出的文本与 ``color`` 下**逐字符相同**
（只是没有标记），结构（字段名、行、计数）一个不少——`strip_markup` 就是这条判据的
实现。
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional, Sequence, Tuple

from .. import diff, keys, model, rules, slow
from ..queries import CaseRow, DiffRow, MatrixRow, RunRow, SlowRow, SuiteRow

#: 未转义的 ``[...]`` = 标记（数据里的 ``[`` 一律先被 `escape_markup` 转义）
_TAG_RE = re.compile(r"(?<!\\)\[[^\[\]]*\]")

SINGLE_COLUMN = "single"
THREE_COLUMN = "three"
COLOR = "color"
MONO = "mono"

#: 状态 → 颜色（呈现选择，不是判定口径）
TONE_BY_STATUS = {
    model.STATUS_FAIL: "bold red",
    model.STATUS_SKIP: "yellow",
    model.STATUS_PASS: "green",
    model.STATUS_MISSING: "dim",
}


# ── 降级两条 ──────────────────────────────────────────────────────────


def column_mode(width, view_rules):
    """终端宽度 < `view.min_width_single_column` → 单栏（只留树 + 按 Enter 的详情）。"""
    return SINGLE_COLUMN if int(width) < int(view_rules["min_width_single_column"]) else THREE_COLUMN


def style_mode(env=None, isatty=True):
    """`NO_COLOR` / `TERM=dumb` / 非 tty / 无真彩色 → ``mono``（结构保留，颜色退化）。

    ``NO_COLOR`` 按规范看**有没有设置**，不看取值——``NO_COLOR=""`` 也是"要退化"
    （空值不等于"没设置"；用 ``env.get("NO_COLOR")`` 会把它当假值，实测踩过）。
    """
    env = os.environ if env is None else env
    if "NO_COLOR" in env:
        return MONO
    if not isatty:
        return MONO
    if (env.get("TERM") or "").strip().lower() in ("", "dumb"):
        return MONO
    if (env.get("COLORTERM") or "").strip().lower() not in ("truecolor", "24bit"):
        return MONO
    return COLOR


# ── 标记（markup）与结构保真 ──────────────────────────────────────────


def escape_markup(text):
    """把数据里的 ``[`` 转义成字面量——否则用例名里的方括号会被当成标记解析。"""
    return str(text).replace("[", r"\[")


def markup(text, style, tone=""):
    """``mono`` 或没有色调 → 纯文本；否则套一层 Rich 标记（内容本身照旧转义）。"""
    body = escape_markup(text)
    if style == MONO or not tone:
        return body
    return "[%s]%s[/]" % (tone, body)


def strip_markup(text):
    """去掉标记、还原转义——用来断言"结构没变、只是没了颜色"。

    只认``未转义``的 ``[...]``：数据里的方括号在渲染前一律被 `escape_markup` 转义，
    所以这个替换不会吃掉用例名里的方括号。
    """
    return _TAG_RE.sub("", str(text)).replace("\\[", "[")


def has_markup(text):
    """文本里还有没有**未转义**的标记（``mono`` 模式必须为假）。"""
    return bool(_TAG_RE.search(str(text)))


# ── 基础格式化 ────────────────────────────────────────────────────────


def time_text(time_ms: Optional[int]):
    """耗时列：``None`` 显示 ``—``（缺失**不补 0**，K28）。"""
    return "—" if time_ms is None else "%d ms" % int(time_ms)


def run_header_text(run: RunRow, style):
    """表头一行的 run 身份（空串按 K26 如实显示为 `(未标注)`）。"""
    parts = []
    for label, value in (("branch", run.branch), ("commit", run.commit_sha),
                         ("ci_run", run.ci_run_id), ("started", run.started_at),
                         ("framework", run.framework)):
        shown = value if value != "" else "(未标注)"
        parts.append("%s=%s" % (label, markup(shown, style, "dim")))
    return "run #%d  %s" % (run.run_id, "  ".join(parts))


# ── summary ──────────────────────────────────────────────────────────


#: summary 字段 → 色调（呈现选择；`fail`/`flaky`/`broken` 有值时上色）
_SUMMARY_TONES = {"fail": "bold red", "flaky": "yellow", "broken": "bold red"}


def summary_text(summary: Dict[str, Optional[int]], fields: Sequence[str], style):
    """summary 面板：字段序来自规则包；值为 ``None`` 的字段显示 ``—`` 并标注原因。

    M5 起六个字段全部实装（`flaky`/`broken` 由 `flaky.py` 填、`slow` 由 `slow.py` 填）。
    ``None`` 只剩两种可能：字段属于**后续里程碑**，或**该 run 上确实没有可判的数据**——
    两种都如实写出来，不拿 0 冒充（0 是"数过、是 0"，``None`` 是"没得数"）。
    """
    chunks = []
    for field in fields:
        value = summary.get(field)
        if value is None:
            chunks.append("%s %s" % (markup(field, style, "dim"), markup("—", style, "dim")))
            continue
        tone = _SUMMARY_TONES.get(field, "") if value else ""
        chunks.append("%s %s" % (markup(field, style, "bold"), markup(str(value), style, tone)))
    line = "  ".join(chunks)
    pending = [field for field in fields if summary.get(field) is None]
    if pending:
        line += "\n" + markup(
            "待实装／无数据：%s（None 不是 0：没得数时不猜）" % "/".join(pending), style, "dim")
    return line



# ── 树标签 ────────────────────────────────────────────────────────────


def suite_label(suite: SuiteRow, style):
    """suite 节点：``名字 [失败/用例数]``；失败子树整体色调为红。"""
    total = len(suite.cases)
    tone = TONE_BY_STATUS[model.STATUS_FAIL] if suite.fail_count else ""
    return markup("%s [%d/%d]" % (suite.name or "(未命名 suite)", suite.fail_count, total),
                  style, tone)


def class_label(classname, cases, style):
    total = len(cases)
    fails = sum(1 for case in cases if case.failed)
    tone = TONE_BY_STATUS[model.STATUS_FAIL] if fails else ""
    return markup("%s [%d/%d]" % (classname or "(无 classname)", fails, total), style, tone)


def case_label(case: CaseRow, style):
    tone = TONE_BY_STATUS.get(case.status, "")
    return markup(case.label, style, tone)


# ── 详情 / 聚合 ───────────────────────────────────────────────────────


def detail_text(case: CaseRow, style):
    """failure 原文：身份 + 四态 + 耗时 + 失败类型/消息/**stack 首行**（库里只有首行）。"""
    lines = [
        markup("%s::%s::%s" % (case.suite_name, case.classname, case.name), style, "bold"),
        "status=%s  time=%s" % (markup(case.status, style, TONE_BY_STATUS.get(case.status, "")),
                                time_text(case.time_ms)),
    ]
    if case.failure_type or case.failure_message or case.stack_first_line:
        lines.append("type: %s" % escape_markup(case.failure_type or "—"))
        lines.append("message: %s" % escape_markup(case.failure_message or "—"))
        lines.append("stack: %s" % escape_markup(case.stack_first_line or "—"))
    return "\n".join(lines)


def aggregate_text(name, cases, style):
    """选中 suite / class 节点时的聚合行（只数已落库的 occurrence）。"""
    total = len(cases)
    fails = sum(1 for case in cases if case.failed)
    skips = sum(1 for case in cases if case.status == model.STATUS_SKIP)
    return "%s：%d 用例 / %s 失败 / %s 跳过" % (
        markup(name or "(无名字)", style, "bold"),
        total,
        markup(str(fails), style, TONE_BY_STATUS[model.STATUS_FAIL] if fails else ""),
        markup(str(skips), style, TONE_BY_STATUS[model.STATUS_SKIP] if skips else ""),
    )


# ── sparkline ─────────────────────────────────────────────────────────


def sparkline_series(history: Sequence[Tuple[int, str]]):
    """pass=1 / fail=0 的序列；``skip`` / ``missing`` **不绘制**（也不进序列）。

    与 flaky 的分母口径同源（`model.COUNTED_STATUSES`）：只画"真正参与计数"的 run。
    返回 ``(values, skipped)``，``skipped`` 是被跳过的次数——面板会把它写出来，
    免得"画短了"被误读成"跑得少"。
    """
    values = []
    skipped = 0
    for _run_id, status in history:
        if status == model.STATUS_PASS:
            values.append(1.0)
        elif status == model.STATUS_FAIL:
            values.append(0.0)
        else:
            skipped += 1
    return values, skipped


def sparkline_text(history, style):
    values, skipped = sparkline_series(history)
    counted = sum(1 for _r, status in history if model.is_counted(status))
    note = "history: %d 次参与计数（pass/fail）" % counted
    if skipped:
        note += "，%d 次 skip/missing 未绘制" % skipped
    return markup(note, style, "dim")


# ── F / S / D 三个视图 ────────────────────────────────────────────────


def matrix_text(columns: Sequence[RunRow], rows: Sequence[MatrixRow], style):
    """flaky 矩阵：test × run 的四态字形（`model.STATUS_GLYPHS` 单点）+ 分型标签。

    行序由 `queries.matrix_rows` 决定（`flaky_score` 降序，同分按身份字典序）；
    分型（`flaky`/`broken`/`stable`/`watch`）与 `flaky_score` 都来自 `flaky.classify`
    （M4）——呈现层只负责把它们画出来，不重算。
    """
    if not columns:
        return markup("窗口内没有 run。", style, "dim")
    header = [markup("test × run", style, "bold")]
    header.extend(markup(this, style, "dim") for this in _run_column_labels(columns))
    lines = ["  ".join(header)]
    for row in rows:
        cells = [model.STATUS_GLYPHS.get(status, "?") for status in row.statuses]
        tone = TONE_BY_STATUS[model.STATUS_FAIL] if row.fail_count else ""
        label = row.label or "—"
        score = row.profile.flaky_score_text if row.profile is not None else "—"
        lines.append("%s  %-8s %-6s  %s::%s" % (
            markup("".join(cells), style, tone),
            markup(label, style, _label_tone(row.label)),
            markup(score, style, "dim"),
            escape_markup(row.classname),
            markup(escape_markup(row.name), style, tone),
        ))
    lines.append(markup(
        "图例：· pass  ✗ fail  - skip  ? missing／缺该 run；"
        "分型 stable/flaky/broken/watch，行序 = flaky_score 降序",
        style, "dim"))
    return "\n".join(lines)


#: 分型 → 色调（呈现选择，不是判定口径）
_LABEL_TONES = {
    "broken": "bold red",
    "flaky": "yellow",
    "stable": "green",
    "watch": "dim",
}


def _label_tone(label):
    return _LABEL_TONES.get(label, "")



def _run_column_labels(columns: Sequence[RunRow]):
    """矩阵列标签：run 号 + 身份尾缀，太密时只留 run 号。"""
    labels = []
    for run in columns:
        tail = run.commit_sha[:7] if run.commit_sha else (run.ci_run_id or "")
        labels.append(("#%d" % run.run_id) + ("@" + tail if tail else ""))
    return labels


def slow_text(rows: Sequence[SlowRow], style):
    """慢测试视图（`S`）：每条用例的 **p50 / p95 + 回归标记** + 一个量级条。

    分位数与回归判定**来自 `slow.py`**（挂在 `row.profile` 上）——呈现层只负责
    把它们画出来，不重算（口径复制成第二套正是 `plan/03` 要禁的）。条宽用
    `slow.bar_width` 的整数运算，按**本 run 最大耗时**归一。
    """
    if not rows:
        return markup("本 run 没有声明耗时的用例（缺失耗时写 NULL，不补 0）。", style, "dim")
    # 行序由调用方（`queries.slow_rows`）的 SQL `ORDER BY time_ms DESC` 决定；
    # 这里只画比例条，不重排——排序单点不复制第二份。
    top = max(row.time_ms for row in rows)
    width = int(rules.load_slow_rules()["waterfall_width"])
    lines = []
    for row in rows:
        profile = row.profile
        p50 = "—" if profile is None else (profile.p50_text or "—")
        p95 = "—" if profile is None else (profile.p95_text or "—")
        reg = "—" if profile is None else profile.regression_text
        tone = _regression_tone(profile)
        bar = "█" * slow.bar_width(row.time_ms, top, width)
        lines.append("%8s  %-8s  %-8s  %s  %s  %s" % (
            markup("%d ms" % row.time_ms, style, "bold"),
            markup("p50=%s" % p50, style, "dim"),
            markup("p95=%s" % p95, style, "dim"),
            markup("reg=%s" % reg, style, tone),
            markup(bar, style, "cyan"),
            escape_markup(row.name),
        ))
    lines.append(markup(
        "条宽 = 本 run 内该用例耗时 / 最大耗时（整数运算）；"
        "p50/p95 与 reg 来自 slow.py（reg=yes/no/?，? 表示判不了）",
        style, "dim"))
    return "\n".join(lines)


#: 回归标记 → 色调（呈现选择，不是判定口径）
_REGRESSION_TONES = {"yes": "bold red", "no": "green", "?": "dim"}


def _regression_tone(profile):
    if profile is None:
        return "dim"
    return _REGRESSION_TONES.get(profile.regression_text, "")


def diff_text(rows: Sequence[DiffRow], style):
    """两次 run 的用例级 diff：按 `diff.py` 的**三类分类**分组渲染。

    分类口径在 `diff.py`（判定层）；这里只按它的固定顺序分桶画出来。**三类都要
    出现**（新增失败 / 修复 / 仍失败），其余组合落"其余"桶——不把 `fail→skip`
    这类悄悄算成"修复"（那正是 `--fail-on new-failures` 想抓的自欺）。
    """
    if not rows:
        return markup("没有可比对的用例。", style, "dim")
    groups = diff.group_rows(diff.classify_rows(rows))
    lines = []
    for kind in diff.CLASS_ORDER:
        bucket = groups[kind]
        title = diff.CLASS_TITLES[kind]
        lines.append(markup("%s（%d）" % (title, len(bucket)), style, _label_tone(kind)))
        if not bucket:
            lines.append("  " + markup("—", style, "dim"))
            continue
        for entry in bucket:
            row = entry.row
            before = row.status_before or "(缺)"
            after = row.status_after or "(缺)"
            tone = TONE_BY_STATUS[model.STATUS_FAIL] if model.STATUS_FAIL in (before, after) else ""
            lines.append("  %s→%s  %s::%s" % (
                markup(before, style, tone),
                markup(after, style, tone),
                escape_markup(row.classname),
                markup(escape_markup(row.name), style, tone),
            ))
    return "\n".join(lines)


# ── 帮助层 ────────────────────────────────────────────────────────────


def help_text(style):
    """帮助层**从 `keys.KEYS` 生成**（键位只有这一份来源）。

    先按**裸文本**对齐再上色：``"%-6s" % markup(...)`` 会按标记串的长度补空格，
    于是"彩色版"与"退化版"的列宽不同——那就不是"只去色"了（实测踩过）。
    """
    lines = [markup("键位（来源：keys.py）", style, "bold")]
    for label, text in keys.KEYS:
        lines.append("  %s %s" % (markup("%-6s" % label, style, "cyan"), escape_markup(text)))
    return "\n".join(lines)
