"""分层守门（`plan/02` §一）：AST 断言依赖方向单向向下。

```
入口层   cli.py / tui/          （可以往下依赖任何一层）
编排层   ingest.py / export.py / queries.py
判定层   flaky.py / slow.py / diff.py   ← 不得 import 入口层、DB、Textual
表示层   model.py / identity.py / report_model.py
基础层   db.py / paths.py / rules.py / keys.py / exit_codes.py
```

两条判据合起来才叫"单向向下"：

1. **不许 import 什么**（`cli.LAYER_RULES`）；
2. **必须 import 什么**（`cli.REQUIRED_IMPORTS`）——把 `app.py` 里对 `report_model`
   的引用删掉，界面照样跑得起来，但"md 字段与 TUI 一致"（`plan/02` §五 的决策）就
   悄悄失效了。第 2 条让那次删除**可跑红**，这正是本文件要求的变异验证。

所有判据都在**临时副本**上做变异验证，不靠"仓库当前恰好干净"。
"""

import shutil
from pathlib import Path

from testdeck import cli

SRC = Path(__file__).resolve().parents[1] / "src"


def _copy_src(tmp_path):
    dest = tmp_path / "src"
    shutil.copytree(SRC, dest)
    return dest


def _append(root, rel, line):
    """在副本里追加一行（文件不存在则新建——`flaky.py` 之类要 M4/M5 才存在）。"""
    path = root / "testdeck" / rel
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(text + "\n" + line + "\n", encoding="utf-8")


def _rewrite(root, rel, old, new, count=1):
    """按相对 `testdeck/` 的路径改写副本里的文件（支持 `tui/app.py` 这类子目录）。"""
    path = root / "testdeck" / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, "变异目标不存在（判据漂移）：%s 里找不到 %r" % (rel, old)
    path.write_text(text.replace(old, new, count), encoding="utf-8")


# ── 第 1 条：不许 import 什么 ─────────────────────────────────────────


def test_repo_layering_is_clean():
    assert cli.scan_layering_problems() == []


def test_each_layer_rule_is_reachable(tmp_path):
    """每条 LAYER_RULES 都要能被真扫到（否则登记了却没人扫 = 装饰）。"""
    root = _copy_src(tmp_path)
    injections = {
        "flaky.py": "import textual",
        "slow.py": "from testdeck import db",
        "diff.py": "from testdeck import cli",
        "export.py": "from testdeck import tui",
        "report_model.py": "import textual",
        "queries.py": "from testdeck import tui",
        "view.py": "import textual",
        "model.py": "from testdeck import db",
        "identity.py": "from testdeck import cli",
    }
    assert set(injections) == set(cli.LAYER_RULES), (
        "LAYER_RULES 与注入表不同步：%s" % sorted(set(cli.LAYER_RULES) ^ set(injections)))
    for rel, line in injections.items():
        _append(root, rel, line)
    problems = cli.scan_layering_problems(root)
    assert len(problems) == len(injections), problems


def test_clean_copy_stays_green(tmp_path):
    """对照组：只复制不改的副本必须干净（防"扫描器见谁咬谁"）。"""
    assert cli.scan_layering_problems(_copy_src(tmp_path)) == []


# ── 第 2 条：必须 import 什么（本次的变异验证）────────────────────────


def test_removing_report_model_reference_is_detected(tmp_path):
    """**变异验证**：删掉 `app.py` 里对 `report_model` 的引用 → 守门必须红。

    这是 `plan/02` §一 点名要求的那次变异。删掉之后 App 仍然能跑（只是 summary
    不再来自共用模型），所以只有这条"必须 import"的判据能把它拦住。
    """
    root = _copy_src(tmp_path)
    assert cli.scan_layering_problems(root) == []
    _rewrite(root, "tui/app.py", "from .. import db, exit_codes, keys, queries, report_model, rules",
             "from .. import db, exit_codes, keys, queries, rules")
    problems = cli.scan_layering_problems(root)
    assert any("testdeck.report_model" in item for item in problems), problems


def test_removing_model_reference_from_queries_is_detected(tmp_path):
    """`queries.py` 不再取四态单点 → 守门红（状态字形/枚举会出现第二份）。"""
    root = _copy_src(tmp_path)
    _rewrite(root, "queries.py", "from . import flaky, model, rules", "from . import flaky, rules")
    problems = cli.scan_layering_problems(root)
    assert any("testdeck.model" in item for item in problems), problems


def test_app_actually_reads_the_shared_model():
    """正向断言：`app.py` 里确实在**用** `report_model`（不只是 import 了它）。"""
    text = (SRC / "testdeck" / "tui" / "app.py").read_text(encoding="utf-8")
    assert "report_model.build_report(" in text
    assert "report_model.summary_fields(" in text
