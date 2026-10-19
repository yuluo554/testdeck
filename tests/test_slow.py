"""`slow.py` 判定层：分位数插值、缺失耗时、回归边界与两条降级（`plan/03` 模块④）。

判定层是**纯函数**，所以这里的用例全是内存数据，不碰库、不碰终端。阈值一律从
`rules.load_slow_rules()` 取（代码里不出现阈值字面量，见 `test_no_rule_literals.py`）。

**与参照实现的对照**：`tests/test_bench_refimpl.py` 也有一组分位数/回归用例，但那是
**参照实现**（`bench/refimpl.py`，阈值取自台账快照）的算术正确性。两组用例独立存在，
互不引用——这正是"两份实现互为对照"的落地：若两边各自漂移，两组用例都会红。
"""

from fractions import Fraction

import pytest

from testdeck import model, rules, slow


def _rules():
    return rules.load_slow_rules()


# ── 分位数（线性插值，索引 (n-1)*p）──────────────────────────────────


def test_percentile_constant_window():
    assert slow.percentile([1000, 1000, 1000], _rules()["p50"]) == 1000


def test_percentile_interpolates_between_neighbours():
    """索引 (n-1)*p：n=2, p=0.5 -> idx=0.5 -> 取 0 与 10 的中点。"""
    assert slow.percentile([0, 10], _rules()["p50"]) == 5


def test_percentile_p95_linear_interpolation():
    """n=5, p=0.95 -> idx=3.8 -> v[3] + (v[4]-v[3])*0.8 = 3.8（精确有理数）。"""
    assert slow.percentile([0, 1, 2, 3, 4], _rules()["p95"]) == Fraction(38, 10)


def test_percentile_single_sample_and_empty():
    assert slow.percentile([7], _rules()["p50"]) == 7
    assert slow.percentile([], _rules()["p50"]) is None


def test_percentile_input_order_does_not_matter():
    """输入按值升序排序（稳定）：乱序输入与升序输入给同一个答案。"""
    shuffled = [900, 100, 500, 300, 700]
    assert slow.percentile(shuffled, _rules()["p50"]) == \
        slow.percentile(sorted(shuffled), _rules()["p50"])


def test_percentile_is_exact_not_float():
    """非终止小数（1/3 类）按精确 `Fraction` 保留，不四舍五入成假精度。"""
    value = slow.percentile([0, 1, 2], Fraction(1, 3))
    assert isinstance(value, Fraction)
    assert value == Fraction(2, 3)


def test_percentile_threshold_comes_from_rules_not_hardcoded():
    """把 p 改成 0 / 1，结果必须是端点——分位数确实读了传入的 p。"""
    assert slow.percentile([10, 20, 30], "0") == 10
    assert slow.percentile([10, 20, 30], "1") == 30


# ── 缺失耗时：不补 0、不进样本（K28）────────────────────────────────


def test_missing_time_is_excluded_not_zero():
    """`None` 不进样本——若补 0，p50 会被拉低。"""
    assert slow.samples([1000, None, 2000]) == [1000, 2000]
    assert slow.samples([None, None]) == []
    # 全缺失 -> p50 无定义（None），不是 0
    assert slow.p50([None, None, None], _rules()) is None


def test_missing_time_changes_percentile_versus_zero_fill():
    """对照：把 None 当 0 会给出不同的 p50（证明"补 0"是会改变结论的缺陷）。"""
    with_missing = slow.p50([100, 200, None], _rules())
    with_zero = slow.p50([100, 200, 0], _rules())
    assert with_missing != with_zero, (with_missing, with_zero)


# ── 回归判定：两处边界都计入（>=）────────────────────────────────────


def test_regression_boundary_ratio_and_delta_exact():
    """ratio 恰 1.2 且 delta 恰 200ms -> 判回归（两边界都是 >=）。"""
    hit, note = slow.regression(1000, 1200, _rules())
    assert hit is True and ">=" in note


def test_regression_ratio_exact_but_delta_below():
    hit, _ = slow.regression(900, 1080, _rules())  # ratio 恰 1.2，delta 180ms
    assert hit is False


def test_regression_ratio_below_and_above():
    assert slow.regression(1000, 1199, _rules())[0] is False
    assert slow.regression(1000, 1201, _rules())[0] is True


def test_regression_delta_exact_and_below_and_above():
    assert slow.regression(500, 700, _rules())[0] is True   # delta 恰 200
    assert slow.regression(500, 699, _rules())[0] is False  # delta 199
    assert slow.regression(500, 701, _rules())[0] is True   # delta 201


def test_regression_undefined_base_is_not_a_verdict():
    """base_p50 == 0 -> 不判回归（返回 None），也不谎报"无回归"（False）。"""
    hit, note = slow.regression(0, 500, _rules())
    assert hit is None and note == slow.NOTE_UNDEFINED_BASE
    assert slow.regression(None, 500, _rules())[0] is None
    assert slow.regression(500, None, _rules())[1] == slow.NOTE_MISSING_WINDOW


def test_regression_thresholds_come_from_rules():
    """把阈值改成一组"任何输入都判不了回归"的值，判定必须随之改变。"""
    assert slow.regression(1000, 1200, _rules())[0] is True
    stricter = dict(_rules())
    stricter["regression_ratio"] = model.as_fraction("99")
    stricter["regression_delta_ms"] = 10 ** 9
    assert slow.regression(1000, 1200, stricter)[0] is False


def test_regression_uses_exact_fractions_not_float():
    """ratio 恰等于阈值时不能掷硬币：1000 -> 1200 恰好 1.2。"""
    hit, note = slow.regression(Fraction(1000), Fraction(1200), _rules())
    assert hit is True
    assert "ratio=1.2(>=)" in note


# ── 两条降级（样本量）────────────────────────────────────────────────


def test_single_sample_is_labelled():
    """只有一个样本 -> p50 == p95 == 该值，标注 `single_sample`。"""
    profile = slow.profile_case(1, "s", "C", "t", 100, [100], 0, _rules())
    assert profile.label == slow.LABEL_SINGLE_SAMPLE
    assert profile.p50 == profile.p95 == 100
    assert profile.regression is None


def test_insufficient_history_is_labelled():
    """回归窗口任一侧无样本 -> `insufficient_history`（判定落 missing_window）。"""
    profile = slow.profile_case(1, "s", "C", "t", 100, [100, 200], 0, _rules())
    assert profile.label == slow.LABEL_INSUFFICIENT_HISTORY
    assert profile.regression is None


def test_no_samples_at_all_is_insufficient_history():
    profile = slow.profile_case(1, "s", "C", "t", None, [None, None], 1, _rules())
    assert profile.label == slow.LABEL_INSUFFICIENT_HISTORY
    assert profile.p50 is None and profile.p95 is None


def test_ample_samples_have_no_label():
    profile = slow.profile_case(1, "s", "C", "t", 1200, [1000, 1000, 1200, 1200], 2, _rules())
    assert profile.label == ""
    assert profile.regression is True


# ── 瀑布条宽度（整数运算）────────────────────────────────────────────


@pytest.mark.parametrize("time_ms,max_ms,width,expected", [
    (0, 1000, 40, 0),
    (1000, 1000, 40, 40),
    (500, 1000, 40, 20),
    (1000, 0, 40, 0),          # max == 0 -> 全宽 0（不除零）
    (333, 1000, 40, 13),       # 13.32 -> 13
    (335, 1000, 40, 13),       # 13.4 -> 13
])
def test_bar_width_is_integer_arithmetic(time_ms, max_ms, width, expected):
    assert slow.bar_width(time_ms, max_ms, width) == expected


def test_bar_width_rounds_half_up_not_bankers():
    """`.5` 边界向上取整：`round()` 的银行家舍入会给出不同的答案。

    1 * 1 / 2 = 0.5 -> 四舍五入为 1（`round(0.5)` 却是 0）。
    """
    assert slow.bar_width(1, 2, 1) == 1
    assert round(0.5) == 0, "（对照）Python round 是银行家舍入——正是本实现不走它的理由"


def test_bar_width_is_monotonic():
    """耗时越大条越宽（不出现"更慢反而更短"）。"""
    widths = [slow.bar_width(t, 1000, 40) for t in (0, 100, 250, 500, 750, 1000)]
    assert widths == sorted(widths)


# ── is_slow（summary 的 slow 字段口径）───────────────────────────────


def test_is_slow_uses_rule_threshold():
    threshold = int(_rules()["slow_ms"])
    assert slow.is_slow(threshold - 1, _rules()) is False
    assert slow.is_slow(threshold, _rules()) is True
    assert slow.is_slow(threshold + 1, _rules()) is True


def test_is_slow_treats_missing_time_as_not_slow():
    """缺失耗时既不是 0 也不是"慢"——缺失不构成"慢"的证据。"""
    assert slow.is_slow(None, _rules()) is False


# ── 回归清单 / 渲染 ──────────────────────────────────────────────────


def test_regression_list_collects_only_true():
    """`--fail-on regressions` 读的就是这份清单：只收 `regression is True`。"""
    yes = slow.profile_case(1, "s", "C", "a", 1200, [1000, 1000, 1200, 1200], 2, _rules())
    no = slow.profile_case(2, "s", "C", "b", 300, [300, 300, 300, 300], 2, _rules())
    undecided = slow.profile_case(3, "s", "C", "c", 500, [500], 0, _rules())
    assert yes.regression is True and no.regression is False and undecided.regression is None
    assert slow.regression_list([yes, no, undecided]) == [yes]


def test_regression_text_is_three_state():
    """回归列三态渲染：yes / no / ?（`?` = 判不了，不是"无回归"）。"""
    yes = slow.profile_case(1, "s", "C", "a", 1200, [1000, 1000, 1200, 1200], 2, _rules())
    no = slow.profile_case(2, "s", "C", "b", 300, [300, 300, 300, 300], 2, _rules())
    undecided = slow.profile_case(3, "s", "C", "c", 500, [500], 0, _rules())
    assert (yes.regression_text, no.regression_text, undecided.regression_text) == ("yes", "no", "?")


def test_profile_renders_exact_decimal_strings():
    profile = slow.profile_case(1, "s", "C", "t", 1000, [1000, 1000], 1, _rules())
    assert profile.p50_text == "1000"
    assert profile.p95_text == "1000"


def test_percentile_is_pure_no_io(monkeypatch):
    """纯函数：不读时钟、不开文件。把 `open` 换成会抛的实现，判定仍能跑。"""
    import builtins

    ruleset = _rules()  # 规则在**打桩之前**载入（判定自身不该碰 IO）
    real_open = builtins.open

    def _boom(*args, **kwargs):  # pragma: no cover - 走到这里说明判定碰了 IO
        raise AssertionError("slow 判定不应打开任何文件")

    monkeypatch.setattr(builtins, "open", _boom)
    try:
        value = slow.percentile([1, 2, 3], ruleset["p50"])
        hit, _note = slow.regression(1000, 1200, ruleset)
    finally:
        monkeypatch.setattr(builtins, "open", real_open)
    assert value == 2
    assert hit is True
