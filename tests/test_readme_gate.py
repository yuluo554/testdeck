"""README 指令面 ↔ CLI 参数面 ↔ 打包配置 的三面对账（M0 版，M2–M5 随实装扩展）。

三面：
  ① README 里出现的每个 `testdeck <sub>` 子命令都必须真在 `build_parser()` 里；
  ② README 的安装行 extras 必须与 pyproject 的 optional-dependencies 双向一致；
  ③ 规则包必须被 package-data 覆盖（否则装好的 CLI 读不到规则）。
"""

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

from testdeck import cli

try:  # 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.9 / 3.10 走 tomli
    import tomli as _toml  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _pyproject():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return _toml.load(fh)


def _stdlib_names():
    """3.10+ 有 stdlib_module_names；更早版本用冻结名单（判定词表，不是参数值）。"""
    names = set(getattr(sys, "stdlib_module_names", ()))
    if names:
        return names
    return {
        "abc", "argparse", "ast", "collections", "contextlib", "csv", "dataclasses",
        "datetime", "decimal", "enum", "errno", "fnmatch", "functools", "glob",
        "hashlib", "io", "itertools", "json", "logging", "math", "os", "pathlib",
        "platform", "re", "shutil", "sqlite3", "statistics", "string", "subprocess",
        "sys", "tempfile", "textwrap", "time", "tomllib", "typing", "unicodedata",
        "unittest", "warnings", "xml", "zipfile",
    }


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


def test_dev_extras_cover_test_imports():
    """测试套件真 import 的每个第三方库都必须在 dev extra 里（测试面 = 安装面）。"""
    allowed = _dev_import_names()

    imported = set()
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                imported.add(node.module.split(".")[0])
    third_party = {name.lower() for name in imported - _stdlib_names() - {"testdeck"}}
    assert third_party, "扫描面为空：测试没有 import 任何第三方库"
    missing = third_party - allowed
    assert missing == set(), "测试引入了 dev extra 之外的第三方包：%s" % sorted(missing)


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
