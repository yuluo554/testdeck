"""README 指令面 ↔ CLI 参数面 ↔ 打包配置 的三面对账（M0 版，M2–M5 随实装扩展）。

三面：
  ① README 里出现的每个 `testdeck <sub>` 子命令都必须真在 `build_parser()` 里；
  ② README 的安装行 extras 必须与 pyproject 的 optional-dependencies 双向一致；
  ③ 规则包必须被 package-data 覆盖（否则装好的 CLI 读不到规则）。
"""

import argparse
import ast
import re
from pathlib import Path

import yaml

from testdeck import cli

import tomllib as _toml  # floor 已收 >=3.12，tomllib 内置（3.9/3.10 兜底分支随 DEC3=A 删除）

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _pyproject():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return _toml.load(fh)


def _stdlib_names(stdlib_names):
    """标准库名单**单点取自 `conftest.stdlib_names` fixture**。

    3.9 没有 `sys.stdlib_module_names`，冻结名单漏项曾在 CI 的 py3.9 矩阵把
    标准库 import 误判成第三方依赖（首推实录）。名单在 conftest 里只写一份，
    `test_no_network.py` 与本文件同源——不再各写一套。
    """
    return set(stdlib_names)


def _parser_subcommands():
    parser = cli.build_parser()
    for action in parser._actions:  # noqa: SLF001 - argparse 无公开枚举子命令的 API
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_readme_subcommands_exist_in_parser():
    readme = _read("README.md")
    mentioned = set(re.findall(r"testdeck\s+([a-z][a-z-]*)", readme))
    assert mentioned, "README 没有提到任何子命令（扫描面为空）"
    unknown = mentioned - _parser_subcommands()
    assert unknown == set(), "README 提到但 CLI 不存在的子命令：%s" % sorted(unknown)


def test_every_parser_subcommand_is_documented():
    readme = _read("README.md")
    undocumented = {
        name
        for name in _parser_subcommands()
        if ("testdeck %s" % name) not in readme and ("`%s`" % name) not in readme
    }
    assert undocumented == set(), "CLI 有但 README 未记录的子命令：%s" % sorted(undocumented)


def test_readme_extras_match_pyproject():
    readme = _read("README.md")
    extras_in_readme = set()
    for line in readme.splitlines():
        if "pip install" in line:
            for group in re.findall(r"\[([^\]]+)\]", line):
                extras_in_readme |= {e.strip() for e in group.split(",") if e.strip()}
    declared = set(_pyproject()["project"]["optional-dependencies"])
    assert extras_in_readme, "README 的安装行没有 extras（扫描面为空）"
    assert extras_in_readme == declared, (
        "README extras %s != pyproject extras %s" % (sorted(extras_in_readme), sorted(declared))
    )


def test_rule_package_data_is_declared():
    data = _pyproject()["tool"]["setuptools"]["package-data"]["testdeck"]
    assert "rules/*.json" in data
    for name in ("flaky.json", "slow.json", "view.json"):
        assert (ROOT / "src" / "testdeck" / "rules" / name).is_file()


def test_manifest_covers_rules_for_sdist():
    manifest = _read("MANIFEST.in")
    assert "src/testdeck/rules" in manifest and "*.json" in manifest


#: 分发名 → import 名（别名表；直接比较会造假红，如 Pillow→PIL）
DIST_TO_IMPORT = {"pyyaml": "yaml", "pillow": "PIL", "beautifulsoup4": "bs4"}


def _dev_import_names():
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    names = set()
    for dep in dev:
        base = re.split(r"[<>=!~;\s\[]", dep.strip())[0].lower()
        names.add(DIST_TO_IMPORT.get(base, base).lower())
    return names


def _runtime_import_names():
    """运行时依赖（`[project].dependencies`）——测试要测它们，就得能 import 到。"""
    deps = _pyproject()["project"]["dependencies"]
    names = set()
    for dep in deps:
        base = re.split(r"[<>=!~;\s\[]", dep.strip())[0].lower()
        names.add(DIST_TO_IMPORT.get(base, base).lower())
    return names


def test_dev_extras_cover_test_imports(stdlib_names):
    """测试套件真 import 的每个第三方库都必须在**安装面**里。

    安装面 = dev extra ∪ 运行时依赖：`pip install -e ".[dev]"` 会把两者一起装上，
    所以"测试 import 了 textual"（M3 的 Pilot 测试）是合法的——它本来就随包安装。
    这条门拦的是**第四方**：某个测试顺手 import 了一个没人登记、装包时不会出现的库。
    """
    allowed = _dev_import_names() | _runtime_import_names()
    stdlib = _stdlib_names(stdlib_names)

    imported = set()
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                imported.add(node.module.split(".")[0])
    third_party = {name.lower() for name in imported - stdlib - {"testdeck"}}
    assert third_party, "扫描面为空：测试没有 import 任何第三方库"
    missing = third_party - allowed
    assert missing == set(), "测试引入了安装面之外的第三方包：%s" % sorted(missing)


#: 被测试**按路径动态装载**的仓库脚本根（`conftest.load_script` / `_load_maker`）。
#: 这些文件的第三方 import 不会出现在 `tests/*.py` 的顶层 AST 里——正是本门在
#: M6 干净环境验证时漏掉 `tools/make-demo-gif.py` 的 `PIL`（Pillow 未登记 dev extra）
#: 的原因。扫面扩到这三处，同一条纪律才覆盖"测试真正会执行到的代码"。
REPO_SCRIPT_ROOTS = ("tools", "bench", "data")
#: 被装载脚本所在目录里**属于被测项目**的子目录（fixture 工程依赖，不是本仓代码）。
REPO_SCRIPT_SKIP_DIRS = {"node_modules", "__pycache__", ".tmp", ".playwright",
                         "test-results"}


def _repo_script_import_names(stdlib):
    """扫 `tools/` `bench/` `data/` 下 `.py` 的第三方 import（去掉 stdlib 与本仓包）。"""
    imported = set()
    for root_name in REPO_SCRIPT_ROOTS:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in REPO_SCRIPT_SKIP_DIRS for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    imported.add(node.module.split(".")[0])
    return {name.lower() for name in imported - stdlib - {"testdeck"}}


def test_dev_extras_cover_repo_script_imports(stdlib_names):
    """测试**动态装载**的仓库脚本（`tools/` `bench/` `data/`）的第三方 import 也必须在安装面内。

    M6 干净环境验证实录：`tests/test_demo_gif.py` 按路径装载 `tools/make-demo-gif.py`，
    而后者 `from PIL import …`——`PIL`（Pillow）当时没进 dev extra。旧门只扫
    `tests/*.py` 的顶层 AST，看不见被装载脚本的 import，于是本地（已装 Pillow）全绿、
    干净环境 6 例红。这条门把扫描面扩到那三处，让"测试跑得到的代码"与"安装面"对齐。
    """
    allowed = _dev_import_names() | _runtime_import_names()
    third_party = _repo_script_import_names(_stdlib_names(stdlib_names))
    assert third_party, "扫描面为空：tools/bench/data 下没有任何第三方 import"
    missing = third_party - allowed
    assert missing == set(), (
        "被测试装载的仓库脚本引入了安装面之外的第三方包：%s" % sorted(missing)
    )


def test_ci_workflow_parses_and_has_required_steps():
    """workflow YAML 先本地解析并断言步骤数：step name 含裸 `: ` 会让 GitHub 不建 job。"""
    workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
    jobs = workflow["jobs"]
    assert "test" in jobs
    steps = jobs["test"]["steps"]
    names = [step.get("name", "") for step in steps]
    assert len(steps) >= 6
    assert any("layout gate" in n for n in names), "CI 缺布局门步骤"
    assert any("Selftest (console script" in n for n in names), "CI 缺裸 console-script 冒烟"
    assert any("pytest" in (step.get("run") or "") for step in steps)
    # M6：四套基准接入 CI（plan/05 §五「bench 未接入 CI」的关闭条件）
    runs = [step.get("run") or "" for step in steps]
    assert any("bench/run_all.py" in r and "--probe" not in r for r in runs), \
        "CI 缺 bench 套件步骤（run_all.py 不带 --probe）"
    assert any("bench/run_all.py" in r and "--probe" in r for r in runs), \
        "CI 缺 bench 探活步骤（run_all.py --probe）"
