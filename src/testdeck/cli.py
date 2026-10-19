"""CLI 入口：参数面 + selftest + ingest / tui / export 编排。

参数语义三条（写进测试，不靠约定）：
  1. **不用 ``or DEFAULT``**：``--db ""`` 是用法错误（exit 2），不得静默回落到默认库。
  2. **按 format 分派，未知格式显式拒绝**：argparse ``choices`` -> exit 2。
  3. **中间产物全落显式路径**：本模块不写任何隐藏缓存文件。

退出码 4（``NOT_READY``）**逐命令退役**（`plan/05` §二）：``ingest`` 于 M2、
``tui`` 于 M3、``export`` 于 **M5** 各自实装后都不再返回 4——**至此三条命令全部退役**，
`cli.py` 里不再有 ``NOT_READY`` 分支（常量保留在 `exit_codes.py`，历史留档要能读）。
退役判据见 `tests/test_exit_codes.py`。
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

from . import __version__, exit_codes, export, ingest, keys, paths, rules

PROG = "testdeck"

#: 允许出现在 src/testdeck 的第三方顶层包（其余一律视为"不该有的依赖"）
ALLOWED_THIRD_PARTY = {"textual", "rich"}

#: 零网络守门：这些顶层包出现即视为违反"纯本地零上传"
FORBIDDEN_NETWORK_MODULES = {
    "socket",
    "ssl",
    "urllib",
    "urllib2",
    "http",
    "httplib",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "boto3",
}

#: 分层守门：这些模块不得被判定层 / 表示层 / 查询层 import
#: （`plan/02` §一 的依赖方向单向向下：判定层不碰入口层与 Textual；
#:   `queries.py` 不碰 `tui/`；`report_model.py` 与 `view.py` 不碰 Textual。）
LAYER_RULES = {
    "flaky.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "slow.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "diff.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    # 编排层（`plan/02` §一）：可以往下依赖基础层（`db`）与判定层，
    # 但不得碰入口层（`cli`）与 `tui/`。
    "export.py": {"testdeck.cli", "testdeck.tui", "textual"},
    "report_model.py": {"testdeck.cli", "testdeck.tui", "textual"},
    "queries.py": {"testdeck.cli", "testdeck.tui", "textual"},
    "model.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "identity.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "view.py": {"testdeck.cli", "testdeck.tui", "textual"},
}

#: 分层守门的**另一半**（"必须 import"）：光有"不许 import 什么"是半条守门——
#: 把 `app.py` 里对共用模型的引用删掉，界面照样能跑，但"md 字段与 TUI 一致"就
#: 悄悄失效了（两处各自对齐）。这条要求让那次删除**可跑红**
#: （变异验证见 `tests/test_layering.py::test_removing_report_model_reference_is_detected`）。
REQUIRED_IMPORTS = {
    "app.py": ("testdeck.report_model",),   # TUI 必须从共用模型取数（plan/02 §五）
    "queries.py": ("testdeck.model",),      # 四态字形/状态枚举必须取自单点（plan/03 模块③）
}

#: 动态导入里能静态判定的形态：``importlib.import_module("requests")`` / ``__import__("socket")``
DYNAMIC_IMPORT_FUNCS = ("import_module", "__import__")


def _ensure_utf8_stdio():
    """中文输出在 cp1252 / cp936 管道上的兜底（按 encoding 探针决定，不盲改）。"""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding in ("utf-8", "utf8", "cp65001"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="测试结果终端工作台：把多次 run 的 JUnit XML 归一到本地 SQLite。",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command")

    p_ingest = sub.add_parser("ingest", help="扫描并归一 JUnit XML 到本地库")
    p_ingest.add_argument("paths", nargs="+", help="文件、目录或 glob")
    p_ingest.add_argument("--db", default=None, help="覆盖数据库路径（回显到摘要）")
    p_ingest.add_argument(
        "--glob",
        dest="globs",
        action="append",
        default=None,
        help="扫描模式，可重复；给定时替换默认值（默认 **/junit*.xml、"
             "**/surefire-reports/*.xml、**/build/test-results/**/*.xml）",
    )
    p_ingest.add_argument(
        "--dry-run", action="store_true", help="只解析与统计，不写库（零副作用）"
    )

    p_tui = sub.add_parser("tui", help="打开三栏终端工作台")
    p_tui.add_argument("--db", default=None, help="覆盖数据库路径")
    p_tui.add_argument("--run", default=None, help="指定 run（默认最近一次）")

    p_export = sub.add_parser("export", help="导出 md / json")
    p_export.add_argument("--format", choices=["md", "json"], default="md")
    p_export.add_argument("--db", default=None, help="覆盖数据库路径")
    p_export.add_argument("--run", default=None, help="指定 run（默认最近一次）")
    p_export.add_argument(
        "--fail-on",
        choices=["flaky", "new-failures", "regressions"],
        default=None,
        help="命中即返回非零（CI 门禁）",
    )

    sub.add_parser("selftest", help="自检：键位表、退出码、规则包、零网络与分层")
    return parser


# ── selftest 的四个可证伪检查 ─────────────────────────────────────────


def _check_keys(problems):
    expected = {
        "down",
        "up",
        "first",
        "last",
        "enter",
        "flaky",
        "slow",
        "diff",
        "search",
        "export",
        "help",
        "back",
        "quit",
    }
    if set(keys.BINDINGS) != expected:
        problems.append(
            "键位表缺少或多余条目：%s" % sorted(set(keys.BINDINGS) ^ expected)
        )
    if len(keys.KEYS) != len(keys.BINDINGS):
        problems.append("键位展示表与绑定表条目数不一致")
    display = {label for label, _ in keys.KEYS}
    bound = {keys.display_label(v) for v in keys.BINDINGS.values()}
    if display != bound:
        problems.append("键位展示表与绑定表的键面不一致")
    missing = [a for a in keys.BINDINGS if not keys.description_for(a)]
    if missing:
        problems.append("键位展示表缺这些动作的文案：%s" % sorted(missing))


def _check_exit_codes(problems):
    codes = {
        exit_codes.OK,
        exit_codes.GATE_TRIGGERED,
        exit_codes.USAGE,
        exit_codes.DEPENDENCY,
        exit_codes.NOT_READY,
    }
    if codes != set(range(5)):
        problems.append("退出码不是 0–4 的连续集合")


def _check_rules(problems):
    try:
        loaded = rules.load_all()
    except rules.RulesError as exc:
        problems.append(str(exc))
        return
    flaky = loaded["flaky"]
    slow = loaded["slow"]
    view = loaded["view"]
    if flaky["min_fail_rate"] > flaky["max_fail_rate"]:
        problems.append("flaky 阈值区间倒置")
    if slow["regression_ratio"] <= 1:
        problems.append("回归比值必须 > 1")
    if view["write_generated_at"]:
        problems.append("导出被配置为写入生成时刻（破坏可重放）")
    if not view["formats"]:
        problems.append("导出格式列表为空")


def _iter_src_files(root=None):
    root = root or os.path.dirname(os.path.abspath(__file__))
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def _module_names(node):
    """从一个 Import/ImportFrom 节点取顶层包名与**候选子模块名**。

    AST 无法区分"包内名字"与"子模块"，所以 ``from X import Y`` 必须同时产出
    ``X`` 与 ``X.Y`` 两个候选——只查 ``node.module`` 会静默漏判
    ``from testdeck import db``（子模块名在 ``names`` 里）与相对导入
    （``module is None``）两种形态（实测形态，见 AGENTS.md 的守门纪律）。
    """
    names = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            names.add(parts[0])
            names.add(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            # 相对导入：src/testdeck 下的相对导入都落在 testdeck 包内
            base = "testdeck"
            if node.module:
                base = "testdeck." + node.module
            names.add(base)
            for alias in node.names:
                names.add(base + "." + alias.name)
        elif node.module:
            names.add(node.module.split(".")[0])
            names.add(node.module)
            for alias in node.names:
                names.add(node.module + "." + alias.name)
    return names


def _imported_names(tree):
    """一棵 AST 里所有 Import/ImportFrom 的候选模块名（含子模块名，见 `_module_names`）。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= _module_names(node)
    return names


def _dynamic_import_names(tree):
    """``importlib.import_module("requests")`` / ``__import__("socket")`` 这类字符串参数。

    AST 的 Import/ImportFrom 节点看不到它们；不做这一层就是"守门只防君子"
    （`plan/02` §一 点名要求覆盖动态导入）。
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        label = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else "")
        if label not in DYNAMIC_IMPORT_FUNCS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value.split(".")[0])
                names.add(arg.value)
    return names


def scan_network_problems(root=None):
    """零网络守门：扫 ``root`` 下所有 .py，返回问题清单（空 = 干净）。

    扫的是 **import 面**（含可静态判定的动态导入字符串），不是"有没有真的发请求"——
    静态判据能覆盖的只有前者，这条边界写在 `tests/test_no_network.py` 的文件头，
    不假装覆盖更多。
    """
    problems = []
    scanned = 0
    for path in _iter_src_files(root):
        scanned += 1
        rel = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (OSError, SyntaxError) as exc:
            problems.append("%s 无法解析：%s" % (rel, exc))
            continue
        net = (_imported_names(tree) | _dynamic_import_names(tree)) & FORBIDDEN_NETWORK_MODULES
        if net:
            problems.append("%s 引入网络模块：%s（本项目零网络调用）" % (rel, sorted(net)))
    if scanned == 0:
        problems.append("源码扫描面为空：一个 .py 都没扫到（判据失效）")
    return problems


def scan_layering_problems(root=None):
    """分层守门：按 `LAYER_RULES` 报违规 + 按 `REQUIRED_IMPORTS` 报"引用被删"（空 = 干净）。"""
    problems = []
    scanned = 0
    for path in _iter_src_files(root):
        scanned += 1
        rel = os.path.basename(path)
        banned = LAYER_RULES.get(rel, set())
        required = REQUIRED_IMPORTS.get(rel, ())
        if not banned and not required:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (OSError, SyntaxError) as exc:
            problems.append("%s 无法解析：%s" % (rel, exc))
            continue
        imported = _imported_names(tree) | _dynamic_import_names(tree)
        hit = imported & banned
        if hit:
            problems.append("%s 违反分层（不应 import）：%s" % (rel, sorted(hit)))
        for wanted in required:
            if wanted not in imported:
                problems.append(
                    "%s 不再 import %s（共用模型/单点引用被删——"
                    "\"两处各自对齐\"就是这么悄悄发生的）" % (rel, wanted))
    if scanned == 0:
        problems.append("源码扫描面为空：一个 .py 都没扫到（判据失效）")
    return problems


def _check_source_guards(problems):
    """零网络 + 分层：AST 扫描 src/testdeck，不读 git、不依赖 CWD。"""
    problems.extend(scan_network_problems())
    problems.extend(scan_layering_problems())
    return len(list(_iter_src_files()))


def selftest() -> int:
    """自检：只断言单点定义与常量自洽，不写库、不读网络。"""
    problems = []
    _check_keys(problems)
    _check_exit_codes(problems)
    _check_rules(problems)
    scanned = _check_source_guards(problems)

    for item in problems:
        print("[FAIL] " + item)
    if problems:
        return exit_codes.GATE_TRIGGERED
    print(
        "[OK] selftest：键位表 %d 条，退出码 0–4，规则包 3 份，源码 %d 个（零网络/分层通过）"
        % (len(keys.KEYS), scanned)
    )
    return exit_codes.OK


def _resolve_db_or_usage(raw):
    """``--db`` 解析失败 = 用法错误（exit 2），不得静默回落。

    返回 ``(path, exit_code)``：成功时 code 为 ``None``；失败时 path 为 ``None``、code 为 2。
    **不用 ``parser.error``**——它抛 ``SystemExit``，会让测试与调用方看到异常而不是退出码，
    与"CLI 统一返回退出码"的契约冲突。
    """
    try:
        return paths.resolve_db_path(raw), None
    except ValueError as exc:
        print("%s: error: %s" % (PROG, exc), file=sys.stderr)
        return None, exit_codes.USAGE


def main(argv=None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 的用法错误（含未知子命令 / 缺必填参数 / 非法 choices）统一成 2
        return exit_codes.USAGE if exc.code not in (0, None) else exit_codes.OK

    if args.command == "selftest":
        return selftest()

    if args.command == "ingest":
        # 参数面先验：--db 的合法性在编排之前判（``--db ""`` = 用法错误，不静默回落）
        db_path, code = _resolve_db_or_usage(args.db)
        if code is not None:
            return code
        return ingest.run(args.paths, db_path, globs=args.globs, dry_run=args.dry_run)

    if args.command == "tui":
        db_path, code = _resolve_db_or_usage(args.db)
        if code is not None:
            return code
        from . import tui
        return tui.run_tui(db_path, run_id=args.run)

    if args.command == "export":
        # M5 实装：模型 → md/json → stdout；`--fail-on` 命中即 1。
        db_path, code = _resolve_db_or_usage(args.db)
        if code is not None:
            return code
        return export.run(args.format, db_path, run_id=args.run, fail_on=args.fail_on)

    parser.print_help()
    return exit_codes.USAGE


if __name__ == "__main__":
    sys.exit(main())
