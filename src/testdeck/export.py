"""`export` 编排层（`plan/02` §一 / `plan/03` 模块⑤）：模型 → md / json → 退出码。

```
db.open_existing ──▶ report_model.build_report ──▶ render_md / render_json ──▶ stdout
                          │
                          └─▶ gate_hits(report, --fail-on) ──▶ 命中则 exit 1
```

**`--fail-on` 的判定只读模型**（`report_model.gate_hits`），不重新查库：这样
"CI 拦下来的"就是"屏幕上看到的"——两套查询会各自漂移，`plan/03` 模块⑤ 点名禁止。

退出码（`plan/05` §二 的退役表）：`0` 未命中 / `1` 门禁命中 / `2` 未知格式（argparse
`choices` 已在参数面拦下）/ `3` 库不存在或库中没有 run。

**降级**（`plan/03` 模块⑤）：库文件不存在 / 库不可读 / 无 run → exit 3 并在 stderr
点名路径与"先跑 `testdeck ingest`"。**空库不等于"没有失败"**，所以它不给 0。
"""

from __future__ import annotations

import sys

from . import db, exit_codes, report_model


def run(fmt, db_path, run_id=None, fail_on=None, stream=None, error_stream=None) -> int:
    """导出一次报告并给出退出码（打印到 ``stream`` / ``error_stream``）。"""
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr

    # 库可用性（读侧）：`open_existing` 不建目录不建表，库不存在即报错（K45 同源纪律）
    try:
        conn = db.open_existing(db_path)
    except db.DbError as exc:
        print("testdeck: %s" % exc, file=error_stream)
        return exit_codes.DEPENDENCY
    try:
        try:
            report = report_model.build_report(conn, run_id)
        except report_model.ReportError as exc:
            print("testdeck: %s" % exc, file=error_stream)
            return exit_codes.DEPENDENCY
    finally:
        conn.close()

    try:
        text = report_model.render(report, fmt)
    except ValueError as exc:
        print("testdeck: error: %s" % exc, file=error_stream)
        return exit_codes.USAGE

    print(text, end="" if text.endswith("\n") else "\n", file=stream)

    hits = report_model.gate_hits(report, fail_on)
    if hits:
        print("testdeck: --fail-on %s 命中：%s" % (fail_on, "；".join(hits)),
              file=error_stream)
        return exit_codes.GATE_TRIGGERED
    return exit_codes.OK
