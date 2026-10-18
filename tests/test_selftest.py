"""骨架期自检：键位表与退出码的单点定义不得漂移。"""

from testdeck import exit_codes, keys
from testdeck.cli import main


def test_bindings_cover_all_keys():
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
    assert set(keys.BINDINGS) == expected
    assert len(keys.KEYS) == len(keys.BINDINGS)


def test_display_keys_match_bindings():
    """展示表的键面与绑定表的键值必须是同一组（大小写与 Enter 别名归一）。"""
    display = {label for label, _ in keys.KEYS}
    bound = {("Enter" if v == "enter" else v) for v in keys.BINDINGS.values()}
    assert display == bound


def test_exit_codes_are_contiguous():
    codes = {
        exit_codes.OK,
        exit_codes.GATE_TRIGGERED,
        exit_codes.USAGE,
        exit_codes.DEPENDENCY,
        exit_codes.NOT_READY,
    }
    assert codes == set(range(5))


def test_selftest_exits_zero():
    assert main(["selftest"]) == exit_codes.OK


def test_unknown_command_is_usage_error():
    assert main([]) == exit_codes.USAGE


def test_unknown_subcommand_is_usage_error():
    assert main(["nope"]) == exit_codes.USAGE


def test_not_ready_commands_return_4_in_m0():
    """M0 期三条未实装命令返回 4；M2 起 ingest 必须退役（见 plan/05 §二）。"""
    assert main(["ingest", "some-dir"]) == exit_codes.NOT_READY
    assert main(["tui"]) == exit_codes.NOT_READY
    assert main(["export"]) == exit_codes.NOT_READY


def test_empty_db_argument_is_usage_error_not_default():
    """``--db ""`` 不得静默回落到默认库（``or DEFAULT`` 的经典坑）。"""
    assert main(["ingest", "some-dir", "--db", ""]) == exit_codes.USAGE
    assert main(["export", "--db", "   "]) == exit_codes.USAGE
    assert main(["tui", "--db", ""]) == exit_codes.USAGE


def test_unknown_format_is_rejected():
    assert main(["export", "--format", "xml"]) == exit_codes.USAGE


def test_unknown_fail_on_is_rejected():
    assert main(["export", "--fail-on", "everything"]) == exit_codes.USAGE
