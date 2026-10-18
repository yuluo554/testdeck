"""CLI 入口（M0 骨架期）：参数面 + selftest；ingest/tui/export 在 M2–M5 实装。

参数语义三条（写进测试，不靠约定）：
  1. **不用 ``or DEFAULT``**：``--db ""`` 是用法错误（exit 2），不得静默回落到默认库。
  2. **按 format 分派，未知格式显式拒绝**：argparse ``choices`` -> exit 2。
  3. **中间产物全落显式路径**：本模块不写任何隐藏缓存文件。
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

from . import __version__, db, exit_codes, keys, paths, rules

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

#: 分层守门：这些模块不得被判定层 / 表示层 import
LAYER_RULES = {
    "flaky.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "slow.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "report_model.py": {"testdeck.cli", "testdeck.tui", "textual"},
    "model.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
    "identity.py": {"testdeck.cli", "testdeck.tui", "testdeck.db", "textual"},
}


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
        help="扫描模式，可重复（默认 **/junit*.xml）",
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
    }
    if set(keys.BINDINGS) != expected:
        problems.append(
            "键位表缺少或多余条目：%s" % sorted(set(keys.BINDINGS) ^ expected)
        )
    if len(keys.KEYS) != len(keys.BINDINGS):
        problems.append("键位展示表与绑定表条目数不一致")
    display = {label for label, _ in keys.KEYS}
    bound = {("Enter" if v == "enter" else v) for v in keys.BINDINGS.values()}
    if display != bound:
        problems.append("键位展示表与绑定表的键面不一致")


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


def _iter_src_files():
    root = os.path.dirname(os.path.abspath(__file__))
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


def _check_source_guards(problems):
    """零网络 + 分层：AST 扫描 src/testdeck，不读 git、不依赖 CWD。"""
    scanned = 0
    for path in _iter_src_files():
        scanned += 1
        rel = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (OSError, SyntaxError) as exc:
            problems.append("%s 无法解析：%s" % (rel, exc))
            continue
        forbidden = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                forbidden |= _module_names(node)
        net = forbidden & FORBIDDEN_NETWORK_MODULES
        if net:
            problems.append("%s 引入网络模块：%s（本项目零网络调用）" % (rel, sorted(net)))
        banned = LAYER_RULES.get(rel, set())
        hit = {name for name in forbidden if name in banned}
        if hit:
            problems.append("%s 违反分层（不应 import）：%s" % (rel, sorted(hit)))
    if scanned == 0:
        problems.append("源码扫描面为空：一个 .py 都没扫到（判据失效）")
    return scanned


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


def _open_db_or_dependency(db_path):
    try:
        return db.connect(db_path)
    except db.DbError as exc:
        print("%s: %s" % (PROG, exc), file=sys.stderr)
        return None


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

    if args.command in ("ingest", "tui", "export"):
        # 参数面先验：--db 的合法性在"尚未实现"之前判——否则 M0 期测不到这条语义
        _db_path, code = _resolve_db_or_usage(getattr(args, "db", None))
        if code is not None:
            return code
        print(
            "%s：M0 骨架期尚未实现（见 plan/05 里程碑）；"
            "先跑 `%s selftest` 验证安装面。" % (args.command, PROG),
            file=sys.stderr,
        )
        return exit_codes.NOT_READY

    parser.print_help()
    return exit_codes.USAGE


if __name__ == "__main__":
    sys.exit(main())
