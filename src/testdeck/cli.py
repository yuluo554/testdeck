"""CLI 入口（骨架期）：只做参数面与 selftest，不含任何判定逻辑。"""

from __future__ import annotations

import argparse
import sys

from . import __version__, exit_codes, keys

PROG = "testdeck"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="测试结果终端工作台：把多次 run 的 JUnit XML 归一到本地 SQLite。",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command")

    p_ingest = sub.add_parser("ingest", help="扫描并归一 JUnit XML 到本地库")
    p_ingest.add_argument("paths", nargs="+", help="文件、目录或 glob")
    p_ingest.add_argument("--db", default=None, help="覆盖数据库路径")

    p_tui = sub.add_parser("tui", help="打开三栏终端工作台")
    p_tui.add_argument("--db", default=None, help="覆盖数据库路径")
    p_tui.add_argument("--run", default=None, help="指定 run（默认最近一次）")

    p_export = sub.add_parser("export", help="导出 md / json")
    p_export.add_argument("--format", choices=["md", "json"], default="md")
    p_export.add_argument("--db", default=None, help="覆盖数据库路径")
    p_export.add_argument(
        "--fail-on",
        choices=["flaky", "new-failures", "regressions"],
        default=None,
        help="命中即返回非零（CI 门禁）",
    )

    sub.add_parser("selftest", help="自检：键位表、退出码与纯本地约束")
    return parser


def selftest() -> int:
    """骨架期自检：只断言单点定义与常量自洽，不触碰数据库。"""
    problems = []

    expected = {"down", "up", "first", "last", "enter", "flaky", "slow", "diff",
                "search", "export", "help"}
    if set(keys.BINDINGS) != expected:
        problems.append("键位表缺少或多余条目：%s" % sorted(set(keys.BINDINGS) ^ expected))
    if len(keys.KEYS) != len(keys.BINDINGS):
        problems.append("键位展示表与绑定表条目数不一致")

    codes = {exit_codes.OK, exit_codes.GATE_TRIGGERED, exit_codes.USAGE,
             exit_codes.DEPENDENCY, exit_codes.NOT_READY}
    if codes != set(range(5)):
        problems.append("退出码不是 0–4 的连续集合")

    for item in problems:
        print("[FAIL] " + item)
    if problems:
        return exit_codes.GATE_TRIGGERED
    print("[OK] selftest：键位表 %d 条，退出码 0–4" % len(keys.KEYS))
    return exit_codes.OK


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        return selftest()
    if args.command in ("ingest", "tui", "export"):
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
