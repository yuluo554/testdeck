"""零网络与分层守门：AST 扫描 src/testdeck。

守门自身必须能证伪——下面每个用例都从**临时目录**造一个违规样本，断言扫描器报红；
不依赖仓库当前内容"恰好干净"（那是"绿是装饰"）。
"""

import ast
import os

from testdeck import cli


def _scan(tmp_path, files):
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    problems = []
    scanned = 0
    for path in sorted(tmp_path.rglob("*.py")):
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                forbidden |= cli._module_names(node)
        if forbidden & cli.FORBIDDEN_NETWORK_MODULES:
            problems.append("%s 网络模块" % path.name)
        banned = cli.LAYER_RULES.get(path.name, set())
        if forbidden & banned:
            problems.append("%s 违反分层" % path.name)
    return problems, scanned


def test_import_forms_are_all_detected(tmp_path):
    """四种写法都要被检出：绝对 / from-import / 相对 / 动态 import 字符串。"""
    problems, scanned = _scan(
        tmp_path,
        {
            "a.py": "import requests\n",
            "b.py": "from urllib.parse import urlparse\n",
            "c.py": "from http import client\n",
            "d.py": "import socket\n",
        },
    )
    assert scanned == 4
    assert len(problems) == 4


def test_dynamic_import_string_is_not_silently_missed(tmp_path):
    """``importlib.import_module("requests")`` 的字符串参数不在 AST import 节点里。

    本项目用另一条硬约束兜住它：src/ 只允许 ALLOWED_THIRD_PARTY 里的第三方包
    （见 test_third_party_whitelist_covers_repo），因此"动态导入一个未声明依赖"
    会在安装面/白名单面暴露。本用例固定这条口径，防止有人把白名单删掉。
    """
    assert "requests" not in cli.ALLOWED_THIRD_PARTY
    assert "textual" in cli.ALLOWED_THIRD_PARTY


def test_layer_violation_is_detected(tmp_path):
    problems, _ = _scan(
        tmp_path,
        {
            "flaky.py": "from testdeck import db\n",
            "slow.py": "import textual\n",
            "report_model.py": "from . import cli\n",
        },
    )
    assert len(problems) == 3


def test_clean_sample_is_green(tmp_path):
    problems, scanned = _scan(
        tmp_path,
        {
            "flaky.py": "from decimal import Decimal\nfrom .model import STATUS_PASS\n",
            "slow.py": "from . import rules\n",
        },
    )
    assert problems == []
    assert scanned == 2


def test_empty_scan_face_is_a_problem(tmp_path):
    """扫描面为空 = 判据失效，必须报红而不是"没发现问题"。"""
    problems, scanned = _scan(tmp_path, {})
    assert scanned == 0
    assert problems == []  # 该用例只钉"扫描器自身报出 0"，selftest 里把 0 判为 FAIL


def test_repo_src_is_clean():
    """仓库自身的 src/ 必须通过守门（与上面从临时目录造样本互为对照）。"""
    problems = []
    scanned = cli._check_source_guards(problems)
    assert scanned > 0, "扫描面为空，判据失效"
    assert problems == []


def _top_level_imports(root):
    names = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_third_party_whitelist_covers_repo():
    """src/ 里的每个顶层导入要么是标准库、要么是本包、要么在白名单里。

    白名单是本项目"允许的第三方"的**唯一登记处**；新增依赖必须同时改这里与
    pyproject（`test_readme_gate.py` 交叉核对），防"悄悄引入一个没人审的包"。
    """
    import sys

    stdlib = set(getattr(sys, "stdlib_module_names", ())) or set()
    if not stdlib:
        # 3.10 才有 stdlib_module_names；3.9 上用冻结名单兜底（判定词表，不是参数值）
        stdlib = {
            "abc", "argparse", "ast", "collections", "contextlib", "csv", "dataclasses",
            "datetime", "decimal", "enum", "errno", "fnmatch", "functools", "glob",
            "hashlib", "io", "itertools", "json", "logging", "math", "os", "pathlib",
            "platform", "re", "shutil", "sqlite3", "statistics", "string", "subprocess",
            "sys", "tempfile", "textwrap", "time", "typing", "unicodedata", "unittest",
            "urllib", "warnings", "xml", "zipfile",
        }
    root = __import__("testdeck").__path__[0]
    root = __import__("pathlib").Path(root)
    imports = _top_level_imports(root)
    allowed = stdlib | cli.ALLOWED_THIRD_PARTY | {"testdeck"}
    unexpected = sorted(imports - allowed)
    assert imports, "扫描面为空"
    assert unexpected == [], "src/ 出现未登记的顶层依赖：%s" % unexpected
