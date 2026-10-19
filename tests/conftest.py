"""测试公共装置：按**文件路径**装载 `bench/` 与 `data/synth/` 下的脚本。

为什么不在测试模块顶层 `import refimpl` / `import gen_runs`：
`tests/test_readme_gate.py::test_dev_extras_cover_test_imports` 会 AST 扫描
`tests/*.py` 的顶层导入，断言"测试 import 的第三方包都在 dev extra 里"。
`refimpl` / `gen_runs` / `bench_ingest` / `run_all` 是**仓库内脚本**（不是已发布的
第三方包），顶层导入会被那条门误判为"未登记的依赖"。按路径装载既避开误判，
也让这几个脚本保持"既能当命令行脚本跑、也能被测试加载"的形态。
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def isolated_data_home(tmp_path_factory, monkeypatch):
    """全局：把默认库路径指到临时目录（测试**绝不碰用户的默认库**）。

    M3 实测踩过两次，都是"测试依赖环境"的典型：

    - `["ingest", "."]` 会把仓库里的 fixture 写进 `~/.local/share/testdeck/`；
    - 本机默认库**恰好有数据**时，`["tui"]` 会真的把 TUI 起起来并挂住整个测试进程
      （后台跑 pytest 卡在 23% 不动）。

    隔离之后，"默认库不存在"在任何机器上都成立——判据不再随环境翻转。
    需要自己指定 `XDG_DATA_HOME` 的用例（如 `test_ingest` 的 dry-run 快照）照常覆盖。
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path_factory.mktemp("xdg")))


def load_script(rel_path, module_name):
    """按相对路径装载一个仓库内脚本。"""
    path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stdlib_module_names():
    """标准库顶层模块名集合，**跨 3.9–3.12 都可靠**。

    `sys.stdlib_module_names` 是 **3.10** 才有的；3.9 上取不到，只能用冻结名单。
    首版冻结名单漏了 8 个真实标准库模块（`__future__` / `codecs` / `fractions` /
    `asyncio` / `builtins` / `importlib` / `struct` / `random`），于是 CI 的 py3.9
    两个矩阵把「标准库 import」误判成「未登记的第三方依赖」——**本机只有 3.12，
    这条缺陷在首推前不可能暴露**（首推 CI 实录）。

    修法：3.9 上同时并入 `sys.builtin_module_names`（编译进解释器的模块，含
    `builtins`），再补一份**穷尽式**的纯 Python 标准库名单。名单写在本函数一处，
    `test_no_network.py` 与 `test_readme_gate.py` 都从这里取——**消除重复的第二套口径**
    （两处各写一份时，漏项只在其中一处被修的概率很高）。
    """
    names = set(getattr(sys, "stdlib_module_names", ()))
    names |= set(sys.builtin_module_names)
    # 3.9 冻结兜底：3.10 的 stdlib_module_names 里与本项目相关的一批顶层模块。
    # 判据是"标准库"，不是"参数值"——不追求逐版本穷尽，只求覆盖 3.9 实跑会出现的。
    names |= {
        "__future__", "_thread", "abc", "argparse", "array", "ast", "asyncio",
        "base64", "binascii", "bisect", "builtins", "bz2", "calendar", "codecs",
        "collections", "concurrent", "configparser", "contextlib", "copy", "csv",
        "ctypes", "dataclasses", "datetime", "decimal", "difflib", "dis", "email",
        "encodings", "enum", "errno", "faulthandler", "fnmatch", "fractions",
        "functools", "gc", "getopt", "getpass", "gettext", "glob", "gzip", "hashlib",
        "heapq", "hmac", "html", "http", "importlib", "inspect", "io", "ipaddress",
        "itertools", "json", "keyword", "linecache", "locale", "logging", "lzma",
        "math", "mimetypes", "mmap", "multiprocessing", "netrc", "numbers",
        "operator", "os", "pathlib", "pickle", "pkgutil", "platform", "plistlib",
        "pprint", "profile", "pstats", "pty", "queue", "random", "re", "readline",
        "reprlib", "secrets", "select", "selectors", "shlex", "shutil", "signal",
        "site", "smtplib", "socket", "sqlite3", "ssl", "stat", "statistics", "string",
        "stringprep", "struct", "subprocess", "sys", "sysconfig", "tarfile",
        "tempfile", "textwrap", "threading", "time", "timeit", "token", "tokenize",
        "tomllib", "traceback", "tracemalloc", "types", "typing", "unicodedata",
        "unittest", "urllib", "uuid", "venv", "warnings", "wave", "weakref",
        "webbrowser", "xml", "xmlrpc", "zipfile", "zipimport", "zlib",
    }
    return names


@pytest.fixture(scope="session")
def stdlib_names():
    """把 `stdlib_module_names()` 暴露成 fixture（测试取用**不需 import conftest**）。"""
    return stdlib_module_names()


@pytest.fixture(scope="session")
def repo_root():
    return ROOT


@pytest.fixture(scope="session")
def refimpl():
    return load_script(os.path.join("bench", "refimpl.py"), "td_refimpl")


@pytest.fixture(scope="session")
def gen_runs():
    return load_script(os.path.join("data", "synth", "gen_runs.py"), "td_gen_runs")


@pytest.fixture(scope="session")
def bench_ingest():
    return load_script(os.path.join("bench", "bench_ingest.py"), "td_bench_ingest")


@pytest.fixture(scope="session")
def bench_flaky():
    return load_script(os.path.join("bench", "bench_flaky.py"), "td_bench_flaky")


@pytest.fixture(scope="session")
def bench_slow():
    return load_script(os.path.join("bench", "bench_slow.py"), "td_bench_slow")


@pytest.fixture(scope="session")
def bench_export():
    return load_script(os.path.join("bench", "bench_export.py"), "td_bench_export")


@pytest.fixture(scope="session")
def run_all():
    return load_script(os.path.join("bench", "run_all.py"), "td_run_all")


@pytest.fixture(scope="session")
def scan_leaks():
    """入库 fixture 的脱敏守门（`bench/fixtures/scan_leaks.py`）。

    以 fixture 暴露，而不是在测试里 `from conftest import …`：后者会被
    `test_readme_gate.py::test_dev_extras_cover_test_imports` 的 AST 扫描
    （`ast.walk` 连函数体内的 import 也收）判成"测试引入了第三方包"。
    """
    return load_script(os.path.join("bench", "fixtures", "scan_leaks.py"), "td_scan_leaks")
