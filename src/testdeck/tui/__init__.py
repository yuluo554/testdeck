"""TUI 包（唯一界面形态）：`app.py` 装配控件，`view.py` 做纯呈现，`queries.py` 在上层。

导出面只有三个入口：``TestDeckApp``（无头测试用）、``run_tui``（CLI 用）、
``load_report`` / ``load_view``（取数，可脱离 App 测试）。
"""

from .app import LoadFailed, ReportLoaded, TestDeckApp, ViewLoaded, load_report, load_view, run_tui
from . import view

__all__ = [
    "TestDeckApp",
    "run_tui",
    "load_report",
    "load_view",
    "ReportLoaded",
    "ViewLoaded",
    "LoadFailed",
    "view",
]
