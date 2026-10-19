"""`ingest` 编排层：扫描 → 解析 → 归一 → 落库 → 摘要。

对应 `plan/03` 模块① 与 `plan/02` 的 CLI 契约：

```
paths/globs ──discover──▶ files ──junit.parse_file(iterparse)──▶ ParseOutcome
                                                                    │
                        db.upsert_*（四表）◀────────────────────────┘
```

**run 身份的实操口径（M2 定，K26）**：run 身份 = `(branch, commit_sha, ci_run_id)`，
三个分量**只从 XML 自己声明的元数据里读**（根 / `<testsuite>` 的 `branch` /
`commit[_sha]` / `ci_run_id` 属性）；读不到就写**空串**——不拿路径、目录名或
文件名去"凑"一个身份（那会让"未知"伪装成"已知"，也会把 K1 的空串约定架空）。

由此得到一个必须知道的边界：**没有声明身份的产物会全部落进同一个"未标注 run"**
（三元组全空串），`runs.framework` 记该 run 覆盖到的框架集合（字典序逗号连接）。
想让多份产物分成多个 run，就让 CI 在 XML 里写 `branch` / `commit` / `ci_run_id`
属性（或 `<testsuite>` 上的同名属性）。

**零副作用**：`--dry-run` 不建连接、不建目录、不写任何缓存；`--db` 覆盖值一律回显
（"写到了别处却不知道"是经典事故）。
"""

from __future__ import annotations

import glob as globlib
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from . import db, exit_codes, junit, paths
from .identity import CaseIdentity, RunIdentity

#: 默认扫描模式（目录参数按这些模式递归找产物）；`--glob` 给定时**替换**掉默认值
DEFAULT_GLOBS = (
    "**/junit*.xml",
    "**/surefire-reports/*.xml",
    "**/build/test-results/**/*.xml",
)


@dataclass
class IngestReport:
    """一次 ingest 的结果（摘要 + 计数 + 退出码），供打印与测试断言。"""

    files: int = 0
    runs: int = 0
    cases: int = 0
    occurrences: int = 0
    skipped: int = 0
    frameworks: Tuple[str, ...] = ()
    skipped_reasons: Dict[str, List[str]] = field(default_factory=dict)
    degraded_counts: Dict[str, int] = field(default_factory=dict)
    degraded_paths: Dict[str, List[str]] = field(default_factory=dict)
    db_path: str = ""
    dry_run: bool = False
    missing_paths: List[str] = field(default_factory=list)
    db_error: str = ""
    exit_code: int = exit_codes.OK

    @property
    def ok(self):
        return self.exit_code == exit_codes.OK


class IngestError(RuntimeError):
    """入参层面无法继续（路径不存在等）——对应退出码 2。"""


# ── 扫描发现 ──────────────────────────────────────────────────────────


def discover(paths_in, globs=None, cwd=None):
    """把"文件 / 目录 / glob"三种入参统一成排序后的产物清单。

    返回 ``(entries, missing)``：``entries`` 是 ``(abs_path, display_path)``，
    ``display_path`` 统一正斜杠、尽量相对扫描根（跨盘符回落绝对路径，见 `paths`）；
    ``missing`` 是不存在的入参（调用方据此给退出码 2）。
    排序键 = ``display_path``：两次 ingest 的文件顺序一致（确定性前提）。
    """
    cwd = cwd or os.getcwd()
    patterns = tuple(globs) if globs else DEFAULT_GLOBS
    found = {}
    missing = []
    for raw in paths_in:
        text = str(raw)
        candidates = []
        if os.path.isfile(text):
            candidates.append(text)
        elif os.path.isdir(text):
            for pattern in patterns:
                candidates.extend(
                    globlib.glob(os.path.join(text, pattern), recursive=True)
                )
        else:
            # "glob 形态的入参"（如 bench/fixtures/**/*.xml）：不直接命中就按模式展开
            candidates.extend(globlib.glob(text, recursive=True))
            if not candidates:
                missing.append(text)
                continue
        for candidate in candidates:
            if not os.path.isfile(candidate):
                continue
            key = os.path.normcase(os.path.abspath(candidate))
            if key in found:
                continue
            found[key] = (os.path.abspath(candidate),
                          paths.relative_to_root(candidate, cwd))
    entries = sorted(found.values(), key=lambda item: item[1])
    return entries, missing


# ── 落库 ──────────────────────────────────────────────────────────────


def _aggregate_suites(parsed_suites):
    """同一文件内**重名** suite 合并计（不同文件同名各留一行：source_path 不同）。"""
    merged = {}
    for suite in parsed_suites:
        target = merged.get(suite.name)
        if target is None:
            merged[suite.name] = junit.ParsedSuite(
                name=suite.name, tests=suite.tests, failures=suite.failures,
                errors=suite.errors, skipped=suite.skipped, time_ms=suite.time_ms,
                cases=list(suite.cases),
            )
            continue
        target.tests += suite.tests
        target.failures += suite.failures
        target.errors += suite.errors
        target.skipped += suite.skipped
        if suite.time_ms is not None:
            target.time_ms = (target.time_ms or 0) + suite.time_ms
        target.cases.extend(suite.cases)
    return list(merged.values())


def _now_iso():
    """`ingested_at`——本项目**唯一**读系统时钟的地方（元数据，不进导出/diff）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ingest(paths_in, db_path, globs=None, dry_run=False, cwd=None, clock=None):
    """跑完整 ingest，返回 `IngestReport`（不打印；打印在 `run`）。"""
    report = IngestReport(db_path=str(db_path), dry_run=bool(dry_run))
    entries, missing = discover(paths_in, globs=globs, cwd=cwd)
    report.files = len(entries)
    if missing:
        report.missing_paths = list(missing)
        report.exit_code = exit_codes.USAGE
        return report

    parsed = []
    frameworks = set()
    for abs_path, display in entries:
        outcome = junit.parse_file(abs_path, display)
        if not outcome.ok:
            report.skipped += 1
            report.skipped_reasons.setdefault(outcome.reason, []).append(display)
            continue
        parsed.append(outcome)
        frameworks.add(outcome.framework)
        for reason, count in outcome.degraded.items():
            report.degraded_counts[reason] = report.degraded_counts.get(reason, 0) + count
            bucket = report.degraded_paths.setdefault(reason, [])
            if display not in bucket:
                bucket.append(display)
    report.frameworks = tuple(sorted(frameworks))

    groups = []
    index = {}
    for outcome in parsed:
        key = (outcome.branch, outcome.commit_sha, outcome.ci_run_id)
        group = index.get(key)
        if group is None:
            group = {"key": key, "started_at": outcome.started_at,
                     "source_path": outcome.display_path, "frameworks": set(),
                     "files": []}
            index[key] = group
            groups.append(group)
        group["frameworks"].add(outcome.framework)
        group["files"].append(outcome)
    report.runs = len(groups)

    case_keys = set()
    occurrence_keys = set()
    for group in groups:
        for outcome in group["files"]:
            for suite in outcome.suites:
                for case in suite.cases:
                    case_keys.add((case.suite_name, case.classname, case.name))
                    occurrence_keys.add(group["key"] + (case.suite_name,
                                                        case.classname, case.name))
    report.cases = len(case_keys)
    report.occurrences = len(occurrence_keys)

    if not dry_run:
        # 库可用性**先验**：即使这一批一条都没解析出来，也要先确认库可写——
        # "库不可读/不可写"是依赖问题（退出码 3），不该被"恰好没解析出东西"掩盖。
        connection = None
        try:
            connection = db.connect(str(db_path))
        except db.DbError as exc:
            report.db_error = str(exc)
            report.exit_code = exit_codes.DEPENDENCY
            return report
        ingested_at = clock() if callable(clock) else (clock or _now_iso())
        try:
            with connection:  # 一个事务：要么整批落库，要么什么都不落
                for group in groups:
                    identity = RunIdentity(*group["key"])
                    run_id = db.upsert_run(
                        connection, identity,
                        started_at=group["started_at"],
                        source_path=group["source_path"],
                        framework=",".join(sorted(group["frameworks"])),
                        ingested_at=ingested_at,
                    )
                    for outcome in group["files"]:
                        for suite in _aggregate_suites(outcome.suites):
                            db.upsert_suite(
                                connection, run_id, suite.name,
                                tests=suite.tests, failures=suite.failures,
                                errors=suite.errors, skipped=suite.skipped,
                                time_ms=suite.time_ms, source_path=outcome.display_path,
                            )
                            for case in suite.cases:
                                case_id = db.upsert_case(
                                    connection,
                                    CaseIdentity(case.suite_name, case.classname, case.name),
                                )
                                db.upsert_occurrence(
                                    connection, run_id, case_id, case.status,
                                    time_ms=case.time_ms,
                                    failure_type=case.failure_type,
                                    failure_message=case.failure_message,
                                    stack_first_line=case.stack_first_line,
                                )
        except Exception as exc:  # noqa: BLE001 - 落库失败一律给退出码 3，不让半个库留下
            report.db_error = "%s: %s" % (type(exc).__name__, exc)
            report.exit_code = exit_codes.DEPENDENCY
            return report
        finally:
            if connection is not None:
                connection.close()
    return report


# ── 摘要（机读行 + 人读行，格式见 plan/03 模块①）─────────────────────


def summary_lines(report):
    line = (
        "ingest: files=%d runs=%d cases=%d occurrences=%d skipped=%d framework=%s"
        % (report.files, report.runs, report.cases, report.occurrences,
           report.skipped, ",".join(report.frameworks))
    )
    lines = [line]
    for reason in junit.REASONS:
        if reason in report.skipped_reasons:
            found = sorted(report.skipped_reasons[reason])
            lines.append("skipped: %s=%d (%s)" % (reason, len(found), ", ".join(found)))
    for reason in junit.DEGRADED_REASONS:
        if reason in report.degraded_counts:
            found = sorted(report.degraded_paths.get(reason, []))
            lines.append("degraded: %s=%d (%s)"
                         % (reason, report.degraded_counts[reason], ", ".join(found)))
    if report.files == 0:
        lines.append("note: 未发现匹配的产物文件（files=0）")
    lines.append("db: %s" % report.db_path)
    if report.dry_run:
        lines.append("dry-run: 未写库（零副作用）")
    return lines


def run(paths_in, db_path, globs=None, dry_run=False, cwd=None, stream=None):
    """CLI 入口：打印摘要/错误，返回退出码。"""
    stream = stream or sys.stdout
    report = ingest(paths_in, db_path, globs=globs, dry_run=dry_run, cwd=cwd)
    if report.missing_paths:
        for item in report.missing_paths:
            print("testdeck: error: 路径不存在：%s" % item, file=sys.stderr)
        return report.exit_code
    if report.db_error:
        print("testdeck: %s" % report.db_error, file=sys.stderr)
        return report.exit_code
    for line in summary_lines(report):
        print(line, file=stream)
    return report.exit_code
