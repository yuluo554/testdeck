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
        "back",
        "quit",
    }
    assert set(keys.BINDINGS) == expected
    assert len(keys.KEYS) == len(keys.BINDINGS)


def test_display_keys_match_bindings():
    """展示表的键面与绑定表的键值必须是同一组（大小写与 Enter/Esc 别名归一）。"""
    display = {label for label, _ in keys.KEYS}
    bound = {keys.display_label(v) for v in keys.BINDINGS.values()}
    assert display == bound


def test_every_binding_has_a_display_description():
    """每个动作都要有展示文案（Footer 与帮助层从 `keys.KEYS` 生成，缺一条就是空栏）。"""
    missing = [action for action in keys.BINDINGS if not keys.description_for(action)]
    assert missing == []


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


def test_not_ready_retired_for_ingest_in_m2():
    """原 `test_not_ready_commands_return_4_in_m0` 的**退役版**（`plan/05` §二）。

    M2 实装 `ingest` 后，退出码 4 对它退役：入参不存在是**用法错误**（2），
    不再是"尚未实现"（4）。完整的退役判据在 `tests/test_exit_codes.py`。
    """
    assert main(["ingest", "some-dir"]) == exit_codes.USAGE
    assert main(["ingest", "some-dir"]) != exit_codes.NOT_READY


def test_not_ready_retired_for_tui_in_m3():
    """M3 实装 `tui` 后，退出码 4 对它退役（库不存在 = 依赖缺失 3，不是"尚未实现"）。"""
    assert main(["tui", "--db", "definitely-not-here.db"]) == exit_codes.DEPENDENCY
    assert main(["tui", "--db", "definitely-not-here.db"]) != exit_codes.NOT_READY


def test_not_ready_retired_for_export_in_m5():
    """M5 实装 `export` 后，退出码 4 对它退役（库不存在 = 依赖缺失 3）。"""
    assert main(["export", "--db", "definitely-not-here.db"]) == exit_codes.DEPENDENCY
    assert main(["export", "--db", "definitely-not-here.db"]) != exit_codes.NOT_READY


def test_empty_db_argument_is_usage_error_not_default():
    """``--db ""`` 不得静默回落到默认库（``or DEFAULT`` 的经典坑）。"""
    assert main(["ingest", "some-dir", "--db", ""]) == exit_codes.USAGE
    assert main(["export", "--db", "   "]) == exit_codes.USAGE
    assert main(["tui", "--db", ""]) == exit_codes.USAGE


def test_unknown_format_is_rejected():
    assert main(["export", "--format", "xml"]) == exit_codes.USAGE


def test_unknown_fail_on_is_rejected():
    assert main(["export", "--fail-on", "everything"]) == exit_codes.USAGE
