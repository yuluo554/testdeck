"""报告模型（`plan/03` 模块⑤）：**字段声明顺序 = md 列序 = JSON 键序 = TUI 取值来源**。

`build_report` 产出**一个纯 dict**（只有基本类型 + dataclass 快照），TUI 的 summary
与用例行从这里取，M5 的 `render_md` / `render_json` 也只消费它——所以
"md 字段与 TUI 完全一致"是**可证伪的**（同一个 dict），而不是靠两处分别对齐。

三条纪律（都有对应测试）：

1. **不写生成时刻**：`view.export.write_generated_at` 为 false（`rules.load_view_rules`
   会在为 true 时直接报错）。两次导出必须逐字节一致——写了时间戳就不可能。
2. **不含 `ingested_at`、不含绝对路径**：`ingested_at` 是元数据（`plan/02` §三 时间纪律），
   `source_path` 只以仓库内相对形式出现。
3. **键序 = 字段声明序**：`json.dumps(..., sort_keys=False)` + 末尾换行；
   md 的列顺序 = `REPORT_FIELDS`，与 JSON 的键序同一个来源。

分层纪律：本模块**不得 import Textual**（TUI 与导出都只是它的渲染器）；
`tests/test_layering.py` 用 AST 钉住。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from . import diff, flaky, model, queries, rules, slow

#: run 头部字段（导出时作为报告的元信息段；`ingested_at` **不在**其中——
#: 它是元数据、不进导出，见 `plan/02` §三）
RUN_FIELDS = queries.RUN_FIELDS

#: 用例行字段（**有序**：md 列序 = JSON 键序）。`case_id` 不入报表——
#: 它是本机自增主键，跨机器无意义；跨机器稳定的身份是 `(suite, class, name)`。
REPORT_FIELDS = (
    "suite_name",
    "classname",
    "name",
    "status",
    "time_ms",
    "failure_type",
    "failure_message",
    "stack_first_line",
)

#: 回归清单的导出列序（`plan/03` 模块⑤ 的 `--fail-on regressions` 用它）
REGRESSION_FIELDS = (
    "suite_name",
    "classname",
    "name",
    "time_ms",
    "p50",
    "p95",
    "base_p50",
    "curr_p50",
    "regression",
)

#: `--fail-on` 的三个取值（顺序即规则包 `view.export.fail_on` 的顺序；值取自规则包）
FAIL_ON_FLAKY = "flaky"
FAIL_ON_NEW_FAILURES = "new-failures"
FAIL_ON_REGRESSIONS = "regressions"


class ReportError(RuntimeError):
    """库里没有可用的 run / run 不存在（对应退出码 3）。"""


def summary_fields():
    """summary 的字段与顺序（唯一来源 = 规则包的 `view.summary_fields`）。"""
    return tuple(rules.load_view_rules()["summary_fields"])


def export_formats():
    """可导出格式（唯一来源 = 规则包的 `view.export.formats`）。"""
    return tuple(rules.load_view_rules()["formats"])


def _profile_row(profile) -> Dict[str, object]:
    """把一条 `SlowProfile` 摊成**只含基本类型**的 dict（导出的回归清单行）。"""
    return {
        "suite_name": profile.suite_name,
        "classname": profile.classname,
        "name": profile.name,
        "time_ms": profile.time_ms,
        "p50": profile.p50_text,
        "p95": profile.p95_text,
        "base_p50": model.render_exact(profile.base_p50),
        "curr_p50": model.render_exact(profile.curr_p50),
        "regression": profile.regression_text,
    }


def build_report(conn, run_id=None, window=None) -> Dict[str, object]:
    """组装一次报告：``{"run", "summary", "cases", "history", "suites", "profiles",
    "slow", "diff"}``。

    - ``run_id`` 为 ``None`` → 最近一次 run；查不到 → `ReportError`（调用方给退出码 3）。
    - ``window`` → 每条用例取多少条历史状态（默认 `view.sparkline_runs`）。
    - ``profiles`` 是 `flaky.classify` 的分型结果（`{case_id: CaseProfile}`）；
      ``slow`` 是 `slow.py` 的慢测试画像清单（回归清单也从这里取）；
      ``diff`` 是相对**上一棒 run** 的三类分类（没有上一棒时为 ``None``）。
    - ``cases`` 的每一行都是 ``{REPORT_FIELDS 顺序}`` 的 dict，顺序即导出列序。

    **判定只在这里调一次**（`flaky` / `slow` / `diff`），导出与门禁都读这个 dict——
    所以 `--fail-on` 的结论与屏幕上看到的是同一份判定，不需要（也不允许）重新查库。
    """
    view_rules = rules.load_view_rules()
    if window is None:
        window = view_rules["sparkline_runs"]
    run = queries.resolve_run(conn, run_id)
    if run is None:
        raise ReportError(
            "库中没有可用的 run（先跑 `testdeck ingest <产物>`；`--run` 指定的 run 不存在同此）"
        )

    suites = queries.tree_rows(conn, run.run_id)
    cases: List[Dict[str, object]] = []
    history: Dict[int, List] = {}
    for suite in suites:
        for case in suite.cases:
            cases.append({field: getattr(case, field) for field in REPORT_FIELDS})
            history[case.case_id] = queries.history(conn, case.case_id, window)

    profiles = queries.case_profiles(conn, run.run_id, window)
    slow_rows = queries.slow_rows(conn, run.run_id, window)
    slow_profiles = [_profile_row(row.profile) for row in slow_rows if row.profile is not None]
    regressions = [_profile_row(profile) for profile in slow.regression_list(
        row.profile for row in slow_rows if row.profile is not None)]

    before = queries.previous_run(conn, run.run_id)
    if before is None:
        classified = []
        base_run = None
    else:
        classified = diff.classify_rows(queries.diff_rows(conn, before.run_id, run.run_id))
        base_run = {field: getattr(before, field) for field in RUN_FIELDS}

    return {
        "run": {field: getattr(run, field) for field in RUN_FIELDS},
        "summary": queries.summary(conn, run.run_id, summary_fields()),
        "cases": cases,
        "history": history,
        "suites": suites,
        "profiles": profiles,
        "slow": slow_profiles,
        "diff": {
            "base_run": base_run,
            "counts": diff.counts(classified),
            "entries": [
                {"kind": entry.kind, "classname": entry.row.classname,
                 "name": entry.row.name,
                 "status_before": entry.row.status_before,
                 "status_after": entry.row.status_after}
                for entry in classified
            ],
        } if before is not None else None,
        "regressions": regressions,
    }


# ── 门禁（`--fail-on`）：只读上面的模型，不重新查库 ─────────────────────


def gate_hits(report: Dict[str, object], fail_on: Optional[str]) -> List[str]:
    """按 `fail_on` 判定是否命中；返回命中原因清单（空 = 未命中）。

    三种值（`plan/03` 模块⑤）：

    | 值 | 命中条件 |
    | --- | --- |
    | `flaky` | 分型 `flaky` 的用例数 > 0 |
    | `new-failures` | 相对 base run 新增的 `fail` 用例数 > 0 |
    | `regressions` | 回归清单非空 |

    **只读模型**：结论全部取自 `report`（`build_report` 的产物），不重新查库——
    保证"CI 拦下来的"就是"屏幕上看到的"。
    """
    if fail_on is None:
        return []
    hits: List[str] = []
    if fail_on == FAIL_ON_FLAKY:
        count = sum(1 for profile in (report.get("profiles") or {}).values()
                    if profile.label == flaky.LABEL_FLAKY)
        if count:
            hits.append("flaky=%d" % count)
    elif fail_on == FAIL_ON_NEW_FAILURES:
        counts = (report.get("diff") or {}).get("counts") or {}
        count = counts.get(diff.NEW_FAILURES, 0)
        if count:
            hits.append("new-failures=%d" % count)
    elif fail_on == FAIL_ON_REGRESSIONS:
        count = len(report.get("regressions") or [])
        if count:
            hits.append("regressions=%d" % count)
    return hits


# ── 渲染（只消费 `build_report` 的 dict）───────────────────────────────


def render_json(report: Dict[str, object]) -> str:
    """报告 → JSON（``ensure_ascii`` / ``indent`` 取自规则包）+ 末尾换行。

    **键序 = 声明序**（``sort_keys=False``）：排序会让"声明序"与"输出序"变成两套。
    """
    view_rules = rules.load_view_rules()
    payload = {
        "run": report.get("run"),
        "summary": report.get("summary"),
        "cases": report.get("cases"),
        "regressions": report.get("regressions"),
        "diff": report.get("diff"),
    }
    text = json.dumps(
        payload,
        ensure_ascii=view_rules["json_ensure_ascii"],
        sort_keys=False,
        indent=view_rules["json_indent"],
    )
    return text + "\n"


def _cell(value) -> str:
    """md 表格单元格：``None`` → ``—``；``|`` 转义、换行转 ``<br>``（不破坏表格）。"""
    if value is None:
        return "—"
    text = str(value)
    text = text.replace("|", "\\|")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return text


def render_md(report: Dict[str, object]) -> str:
    """报告 → markdown 表格。**列顺序 = `REPORT_FIELDS`（= JSON 键序）**。

    表格按**失败优先**的行序输出（`cases` 的顺序来自 `queries.tree_rows` 的排序单点），
    所以"屏幕上的顺序"与"导出的顺序"同一份。
    """
    run = report.get("run") or {}
    summary = report.get("summary") or {}
    lines: List[str] = []
    lines.append("# testdeck 报告")
    lines.append("")
    lines.append("## run")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("| --- | --- |")
    for field in RUN_FIELDS:
        lines.append("| %s | %s |" % (field, _cell(run.get(field))))
    lines.append("")
    lines.append("## summary")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("| --- | --- |")
    for field in summary_fields():
        lines.append("| %s | %s |" % (field, _cell(summary.get(field))))
    lines.append("")
    lines.append("## cases")
    lines.append("")
    lines.append("| %s |" % " | ".join(REPORT_FIELDS))
    lines.append("| %s |" % " | ".join("---" for _ in REPORT_FIELDS))
    for row in report.get("cases") or []:
        lines.append("| %s |" % " | ".join(_cell(row.get(f)) for f in REPORT_FIELDS))
    lines.append("")
    lines.append("## regressions")
    lines.append("")
    lines.append("| %s |" % " | ".join(REGRESSION_FIELDS))
    lines.append("| %s |" % " | ".join("---" for _ in REGRESSION_FIELDS))
    for row in report.get("regressions") or []:
        lines.append("| %s |" % " | ".join(_cell(row.get(f)) for f in REGRESSION_FIELDS))
    lines.append("")
    return "\n".join(lines)


def render(report: Dict[str, object], fmt: str) -> str:
    """按格式分派；未知格式抛 ``ValueError``（调用方给退出码 2）。"""
    if fmt == "md":
        return render_md(report)
    if fmt == "json":
        return render_json(report)
    raise ValueError("unknown export format: %r" % (fmt,))
