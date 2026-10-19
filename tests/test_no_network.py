"""零网络守门（`plan/02` §一）：AST 扫描 `src/`，禁止网络模块与动态导入。

**判据边界（如实写在最前面）**：静态扫描能覆盖的是"import 面"——网络模块名与
可静态判定的动态导入字符串（`importlib.import_module("requests")`）。它**不能**覆盖
"自己拼串再 `__import__`"这类刻意绕过。第二道兜底是"src/ 只允许登记过的第三方包"
（`cli.ALLOWED_THIRD_PARTY`，本文件最后一条），所以"动态导入一个未声明依赖"会在
安装面/白名单面暴露；更远的那一层是人工评审——本守门不假装覆盖它。

**守门自身必须可证伪**：每条判据都从**临时副本**造违规样本（`mutate_src`），
不依赖"仓库当前恰好干净"（那是"绿是装饰"）。
"""

import ast
import shutil
from pathlib import Path

from testdeck import cli

SRC = Path(__file__).resolve().parents[1] / "src"


def _copy_src(tmp_path, target="testdeck"):
    """把真实 `src/` 复制到临时目录，返回副本的根（供变异后扫描）。"""
    dest = tmp_path / "src"
    shutil.copytree(SRC, dest)
    return dest


def _inject(root, rel, line):
    """在副本里追加一行（文件不存在则新建——`flaky.py` 之类要 M4/M5 才存在）。"""
    path = root / "testdeck" / rel
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = ""
    path.write_text(text + "\n" + line + "\n", encoding="utf-8")


def test_repo_src_is_clean():
    """仓库自身：网络面必须干净（非空跑：先确认扫描面不是空的）。"""
    scanned = [path for path in cli._iter_src_files() if path.endswith(".py")]
    assert scanned, "扫描面为空，判据失效"
    assert cli.scan_network_problems() == []


def test_all_import_forms_are_detected(tmp_path):
    """四种写法都要被检出：绝对 / from-import / 相对根 / 子模块。"""
    root = _copy_src(tmp_path)
    for rel, line in (
        ("probe_a.py", "import requests"),
        ("probe_b.py", "from urllib.parse import urlparse"),
        ("probe_c.py", "from http import client"),
        ("probe_d.py", "import socket"),
    ):
        _inject(root, rel, line)
    problems = cli.scan_network_problems(root)
    assert len(problems) == 4, problems


def test_dynamic_import_string_is_detected(tmp_path):
    """``importlib.import_module("requests")`` 的字符串参数不在 Import 节点里。

    这是**变异验证**的反面样本：守门若只扫 Import 节点，这里会静默漏判。
    """
    root = _copy_src(tmp_path)
    _inject(root, "probe_dyn.py", "import importlib\nimportlib.import_module('requests')")
    _inject(root, "probe_dunder.py", "__import__('socket')")
    problems = cli.scan_network_problems(root)
    assert len(problems) == 2, problems
    assert all("网络模块" in item for item in problems)


def test_deleting_the_scan_call_is_detected(tmp_path, monkeypatch):
    """守门**自身**的变异：把扫描函数换成"永远返回空"，本文件的断言必须红。

    这条防的是"守门被摘掉但测试仍绿"——比在源码里注入违规更狠。
    """
    root = _copy_src(tmp_path)
    _inject(root, "probe.py", "import socket")
    assert cli.scan_network_problems(root), "注入后本应报红（判据失效）"
    monkeypatch.setattr(cli, "scan_network_problems", lambda root=None: [])
    assert cli.scan_network_problems(root) == [], "被摘掉的守门仍报红？"
    # 说明：上面两行钉住的是"注入确实能红 + 摘掉确实能绿"这对反差，
    # 也就是"这条断言真的在测扫描器，而不是在测常量"。


def test_empty_scan_face_is_a_problem(tmp_path):
    """扫描面为空 = 判据失效，必须报出来而不是"没发现问题"。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.scan_network_problems(str(empty)) == ["源码扫描面为空：一个 .py 都没扫到（判据失效）"]


def test_whitelist_keeps_unregistered_third_party_out(stdlib_names):
    """src/ 里的每个顶层导入要么是标准库、要么是本包、要么在白名单里。

    白名单是本项目"允许的第三方"的**唯一登记处**（与 pyproject 由
    `test_readme_gate.py` 交叉核对）。它也是动态导入的兜底：动态导入一个
    未登记依赖，会在安装面/白名单面暴露。

    标准库名单从 `conftest.stdlib_names` fixture 取（**单点**）：3.9 没有
    `sys.stdlib_module_names`，冻结名单漏项曾在 CI 的 py3.9 矩阵把标准库 import
    误判成第三方依赖（首推实录）——名单只此一份，`test_readme_gate.py` 同源。
    """
    stdlib = stdlib_names
    imported = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                imported.add(node.module.split(".")[0])
    assert imported, "扫描面为空"
    allowed = stdlib | cli.ALLOWED_THIRD_PARTY | {"testdeck"}
    unexpected = sorted(imported - allowed)
    assert unexpected == [], "src/ 出现未登记的顶层依赖：%s" % unexpected
    assert "requests" not in cli.ALLOWED_THIRD_PARTY
    assert "textual" in cli.ALLOWED_THIRD_PARTY
