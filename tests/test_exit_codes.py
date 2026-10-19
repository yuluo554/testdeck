"""退出码退役（`plan/05` §二）：**已实装命令不得再返回 4**。

退役不是删常量：`NOT_READY` 留在 `exit_codes.py`（历史留档要能读），只是不再被
任何命令返回。本文件的第二条断言把"`NOT_READY` 不再出现在 `cli.py` 的任何分支里"
写成可跑红的 AST 判据——比 grep 更精确（它认得清是哪条分支）。

**M5 退役进度（至此全部完成）**：`ingest`（M2 退役）、`tui`（M3 退役）、
`export`（M5 退役）——三条命令都实装，`UNIMPLEMENTED` 已清空。
"""

import ast
import os

import pytest

from testdeck import cli, exit_codes

#: 截至本里程碑（M5）已实装的命令（三条全实装）
IMPLEMENTED = ("ingest", "tui", "export")
#: 未到各自里程碑的命令——M5 起为空（退出码 4 全面退役）
UNIMPLEMENTED = ()


@pytest.fixture(autouse=True)
def isolated_data_home(tmp_path, monkeypatch):
    """把默认库路径指到临时目录——**测试绝不碰用户的默认库**。

    两个原因：① 本机默认库可能真的有数据（`tui` 会真的把 TUI 起起来并挂住测试）；
    ② `["ingest", "."]` 这类入参会**写**默认库（M2 实测踩过：跑一次测试就在
    `~/.local/share/testdeck/` 留下一个库）。隔离之后，"默认库不存在"这条语义
    在任何机器上都成立，判据不再依赖环境。
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


def _fixture_ok(repo_root):
    return os.path.join(repo_root, "bench", "fixtures", "pytest", "junit.xml")


def test_not_ready_constant_is_kept_for_history():
    """退役 ≠ 删常量：历史留档（`plan/05` §二 的退役表）要能读到这个码。"""
    assert exit_codes.NOT_READY == 4


@pytest.mark.parametrize("argv", [
    ["ingest", "."],
    ["ingest", "definitely-not-here", "--db", "x.db"],
    ["ingest", "some-dir", "--db", ""],
    ["ingest", "some-dir", "--dry-run"],
])
def test_ingest_never_returns_not_ready(argv):
    """M2 起 `ingest` 已实装：任何入参形态都不得返回 4（只能 0 / 2 / 3）。"""
    assert cli.main(argv) in (exit_codes.OK, exit_codes.USAGE, exit_codes.DEPENDENCY)
    assert cli.main(argv) != exit_codes.NOT_READY


@pytest.mark.parametrize("argv", [
    ["tui"],                                  # 默认库（不存在）
    ["tui", "--db", "definitely-not-here.db"],
    ["tui", "--db", ""],
    ["tui", "--run", ""],
])
def test_tui_never_returns_not_ready(argv):
    """M3 起 `tui` 已实装：任何入参形态都不得返回 4。

    库不存在 / run 不存在是**依赖缺失**（3），`--db ""` 是**用法错误**（2）——
    没有一种情形该说"尚未实现"。
    """
    assert cli.main(argv) in (exit_codes.OK, exit_codes.USAGE, exit_codes.DEPENDENCY)
    assert cli.main(argv) != exit_codes.NOT_READY


def test_ingest_on_real_fixture_returns_ok(repo_root, tmp_path):
    assert cli.main(["ingest", _fixture_ok(repo_root), "--db",
                     str(tmp_path / "s.db")]) == exit_codes.OK


def test_tui_on_real_store_returns_ok_without_terminal(repo_root, tmp_path, monkeypatch):
    """`tui` 在真库上走到"起 App"这一步；起终端本身被桩替换（CI 里没有 tty）。

    这条钉的是**分发路径**：`cli.main(["tui", ...])` 真的把参数交给了 `tui.run_tui`，
    而不是走老的"尚未实现"分支。
    """
    db_path = str(tmp_path / "tui.db")
    assert cli.main(["ingest", _fixture_ok(repo_root), "--db", db_path]) == exit_codes.OK
    calls = []

    from testdeck import tui as tui_pkg

    def fake_run(db_path_arg, run_id=None, stream=None):
        calls.append((db_path_arg, run_id))
        return exit_codes.OK

    monkeypatch.setattr(tui_pkg, "run_tui", fake_run)
    assert cli.main(["tui", "--db", db_path]) == exit_codes.OK
    assert calls and calls[0][0] == db_path


@pytest.mark.parametrize("argv", [
    ["export"],                                  # 默认库（不存在）
    ["export", "--db", "definitely-not-here.db"],
    ["export", "--db", ""],
    ["export", "--format", "md", "--db", "nope.db"],
    ["export", "--format", "json", "--fail-on", "flaky", "--db", "nope.db"],
])
def test_export_never_returns_not_ready(argv):
    """M5 起 `export` 已实装：任何入参形态都不得返回 4（只能 0 / 1 / 2 / 3）。

    库不存在 / 无 run 是**依赖缺失**（3），`--db ""` / 未知 `--format` / 未知
    `--fail-on` 是**用法错误**（2），门禁命中是 **1**——没有一种情形该说"尚未实现"。
    """
    assert cli.main(argv) in (exit_codes.OK, exit_codes.GATE_TRIGGERED,
                              exit_codes.USAGE, exit_codes.DEPENDENCY)
    assert cli.main(argv) != exit_codes.NOT_READY


def test_export_on_real_store_returns_ok(repo_root, tmp_path):
    """`export` 在真库上真的走到渲染并打印（不是老"尚未实现"分支）。"""
    db_path = str(tmp_path / "export.db")
    assert cli.main(["ingest", _fixture_ok(repo_root), "--db", db_path]) == exit_codes.OK
    assert cli.main(["export", "--db", db_path, "--format", "md"]) == exit_codes.OK
    assert cli.main(["export", "--db", db_path, "--format", "json"]) == exit_codes.OK


def test_export_gate_hits_return_1_on_real_store(repo_root, tmp_path):
    """真库上 `--fail-on` 命中 -> 1；未命中 -> 0（门禁真的在判）。"""
    db_path = str(tmp_path / "gate.db")
    assert cli.main(["ingest", _fixture_ok(repo_root), "--db", db_path]) == exit_codes.OK
    # 三份 fixture 只有 1 个 run、每条用例 counted_runs<=1 -> 一律 watch，
    # 故 `flaky` / `new-failures` / `regressions` 都未命中
    for value in ("flaky", "new-failures", "regressions"):
        assert cli.main(["export", "--db", db_path, "--fail-on", value]) == exit_codes.OK


def test_export_on_empty_db_is_dependency_error(tmp_path):
    """库存在但没有 run -> exit 3（空库不等于"没有失败"）。"""
    from testdeck import db as _db

    db_path = str(tmp_path / "empty.db")
    _db.connect(db_path).close()
    assert cli.main(["export", "--db", db_path]) == exit_codes.DEPENDENCY


def _commands_in_not_ready_branch():
    """AST 扫描 `cli.py`：返回 `NOT_READY` 的那条分支，其条件里点名了哪些命令。"""
    with open(cli.__file__, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=cli.__file__)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        returns_not_ready = any(
            isinstance(inner, ast.Return)
            and "NOT_READY" in ast.dump(inner.value or ast.Constant(None))
            for inner in node.body
        )
        if not returns_not_ready:
            continue
        names = {
            inner.value for inner in ast.walk(node.test)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
        }
        found.append(names)
    return found


def test_cli_has_no_not_ready_branch_left():
    """**M5 收尾判据**：三条命令全部实装后，`cli.py` 里不该再有返回 4 的分支。

    `NOT_READY` 只允许作为**常量引用**存在（`exit_codes.NOT_READY`），
    不得再被任何分支返回——`plan/05` §二 的退役表到此收尾。
    """
    branches = _commands_in_not_ready_branch()
    assert branches == [], "cli.py 仍有返回 NOT_READY 的分支：%s" % branches
    assert set(UNIMPLEMENTED) == set(), "退役未收尾：仍有未实装命令 %s" % sorted(UNIMPLEMENTED)
    assert exit_codes.NOT_READY == 4, "常量保留（历史留档要能读）"
