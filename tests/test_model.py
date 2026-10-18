"""耗时与四态的单点定义（边界值必须被真踩到）。"""

import pytest

from testdeck import model


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.001", 1),
        ("0.0005", 1),      # 0.5ms -> ROUND_HALF_UP -> 1
        ("0.0004", 0),      # 0.4ms -> 0
        ("1.2345", 1235),   # 1234.5 -> 1235（银行家舍入会给 1234）
        ("1.2344", 1234),
        ("2", 2000),
        (" 3.5 ", 3500),
        ("0", 0),
    ],
)
def test_seconds_to_ms_round_half_up(raw, expected):
    assert model.seconds_to_ms(raw) == expected


def test_round_half_up_differs_from_bankers_rounding():
    """2.5 在 Python ``round`` 下是 2（银行家舍入），ROUND_HALF_UP 必须是 3。"""
    assert model.seconds_to_ms("0.0025") == 3
    assert round(2.5) == 2


def test_missing_time_is_none_not_zero():
    assert model.seconds_to_ms(None) is None
    assert model.seconds_to_ms("") is None
    assert model.seconds_to_ms("   ") is None


@pytest.mark.parametrize("bad", ["abc", "NaN", "Infinity", "1,5"])
def test_bad_time_raises_value_error(bad):
    with pytest.raises(ValueError):
        model.seconds_to_ms(bad)


def test_statuses_and_counted_subset():
    assert model.STATUSES == ("pass", "fail", "skip", "missing")
    assert model.COUNTED_STATUSES == ("pass", "fail")
    assert set(model.STATUS_GLYPHS) == set(model.STATUSES)


def test_is_counted_excludes_skip_and_missing():
    assert model.is_counted("pass")
    assert model.is_counted("fail")
    assert not model.is_counted("skip")
    assert not model.is_counted("missing")


def test_validate_status_rejects_unknown():
    with pytest.raises(ValueError):
        model.validate_status("error")
