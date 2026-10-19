"""`flaky.py` 判定层：分母口径、transitions、分型顺序、两条降级、零计数样本（K34）。

判定层是**纯函数**，所以这里的用例全部是内存数据，不碰库、不碰终端。阈值一律
从 `rules.load_flaky_rules()` 取（代码里不出现阈值字面量，见 `test_no_rule_literals.py`）。
"""

from fractions import Fraction

import pytest

from testdeck import flaky, model, rules


def _rules():
    return rules.load_flaky_rules()


def _hist(*statuses):
    """``"pfskm"`` → ``[(0,"pass"),(1,"fail"),...]``（简写，只为少打字）。"""
    mapping = {"p": model.STATUS_PASS, "f": model.STATUS_FAIL,
               "s": model.STATUS_SKIP, "m": model.STATUS_MISSING}
    return [(index, mapping[char]) for index, char in enumerate(statuses)]


# ── 分母口径：skip/missing 既不进分母，也不制造 transition ─────────────


def test_denominator_counts_only_pass_and_fail():
    profile = flaky.classify(_hist("p", "f", "s", "m", "p"), _rules())
    assert profile.counted_runs == 3
    assert profile.passes == 2 and profile.fails == 1
    assert profile.fail_rate == Fraction(1, 3)


def test_skip_and_missing_do_not_create_transitions():
    """`p s p`（中间夹一个 skip）**没有**翻转：参与计数的相邻两次都是 pass。"""
    profile = flaky.classify(_hist("p", "s", "p"), _rules())
    assert profile.transitions == 0
    # 对照：`p f` 才是真翻转
    assert flaky.classify(_hist("p", "f"), _rules()).transitions == 1


def test_transitions_skip_gap_between_real_flips():
    """`p m f`：中间 missing 被跳过，`p`→`f` 仍算一次翻转。"""
    profile = flaky.classify(_hist("p", "m", "f"), _rules())
    assert profile.transitions == 1


def test_transitions_count_only_adjacent_counted_pairs():
    """`p f f p`：翻转 2 次（p→f、f→p）。"""
    profile = flaky.classify(_hist("p", "f", "f", "p"), _rules())
    assert profile.transitions == 2


# ── flaky_score ────────────────────────────────────────────────────────


def test_flaky_score_is_transitions_over_n_minus_one():
    profile = flaky.classify(_hist("p", "f", "p", "f", "p"), _rules())
    assert profile.counted_runs == 5
    assert profile.transitions == 4
    assert profile.flaky_score == Fraction(4, 4) == 1


def test_flaky_score_of_fewer_than_two_counted_runs_is_zero():
    """`n < 2` → 0（单点表达式用 1，不是 2，避免与阈值字面量撞车）。"""
    for history in (_hist(), _hist("p"), _hist("f"), _hist("p", "s", "m")):
        assert flaky.classify(history, _rules()).flaky_score == Fraction(0)


def test_flaky_score_is_exact_not_float():
    """`transitions/(n-1)` 用 `Fraction`——浮点会让"恰好等于阈值"的样本掷硬币。"""
    assert flaky.classify(_hist("p", "f", "p", "f"), _rules()).flaky_score == Fraction(1)
    # ppffp：翻转 p→f、f→p 共 2 次，n=5 → 2/4 = 1/2（精确有理数，不是 0.5 的浮点近似）
    score = flaky.classify(_hist("p", "p", "f", "f", "p"), _rules()).flaky_score
    assert score == Fraction(1, 2)
    assert isinstance(score, Fraction)


def test_non_terminating_decimal_renders_as_fraction_string():
    """非终止小数（如 1/3）如实渲染成 `p/q`，不四舍五入成假精度。"""
    # pppfffpppfff：翻转 3 次，n=12 → 3/11（非终止）
    profile = flaky.classify(_hist(*"pppfffpppfff"), _rules())
    assert profile.flaky_score == Fraction(3, 11)
    assert profile.flaky_score_text == "3/11"
    assert profile.fail_rate_text == "0.5"


# ── 分型顺序：先判恒失败 ───────────────────────────────────────────────


def test_all_fail_is_broken():
    profile = flaky.classify(_hist(*("f" * 6)), _rules())
    assert profile.label == flaky.LABEL_BROKEN
    assert profile.fail_rate == 1
    assert profile.transitions == 0


def test_all_pass_is_stable():
    profile = flaky.classify(_hist(*("p" * 6)), _rules())
    assert profile.label == flaky.LABEL_STABLE
    assert profile.fail_rate == 0


def test_alternating_is_flaky():
    profile = flaky.classify(_hist(*"pfpfpf"), _rules())
    assert profile.label == flaky.LABEL_FLAKY
    assert profile.transitions >= int(_rules()["min_transitions"])


def test_flaky_requires_min_transitions():
    """区间内但翻转不足 → 落兜底 `watch`（不是 flaky）。"""
    # fail_rate = 1/3（在 0.05..0.95 内），transitions = 2 < min_transitions=3
    profile = flaky.classify(_hist("p", "p", "p", "f", "f", "f"), _rules())
    assert profile.fail_rate == Fraction(1, 2)
    assert profile.transitions == 1  # ppp→fff 只翻一次
    assert profile.label == flaky.fallback_label(_rules())


def test_fail_rate_below_min_is_watch():
    """fail_rate 低于下界（0.05）→ watch，即便有翻转。"""
    min_rate = model.as_fraction(_rules()["min_fail_rate"])
    # 造一个 fail_rate < min_rate 的序列：很多 pass + 少量 fail 且反复翻转
    history = _hist(*("p" * 40), *("f" * 1), *("p" * 40), *("f" * 1))
    profile = flaky.classify(history, _rules())
    assert profile.fail_rate < min_rate
    assert profile.label == flaky.fallback_label(_rules())


def test_fail_rate_above_max_is_watch():
    """fail_rate 高于上界（0.95）→ watch（恒失败之外的"几乎全失败"）。"""
    max_rate = model.as_fraction(_rules()["max_fail_rate"])
    history = _hist(*("f" * 40), *("p" * 1), *("f" * 40))
    profile = flaky.classify(history, _rules())
    assert profile.fail_rate > max_rate
    assert profile.label == flaky.fallback_label(_rules())


# ── 两条降级 ───────────────────────────────────────────────────────────


def test_zero_counted_sample_falls_to_watch_not_stable():
    """**K34**：全 skip/missing 的用例 `fail_rate` 无定义 → watch，**不得 stable**。

    判成 stable 会让 stable 计数虚高，并掩盖"这个用例根本没在跑"。
    """
    for history in (_hist(*"smssm"), _hist(*"msmsm")):
        profile = flaky.classify(history, _rules())
        assert profile.label == flaky.fallback_label(_rules())
        assert profile.label != flaky.LABEL_STABLE
        assert profile.counted_runs == 0
        assert profile.fail_rate is None, "0/0 必须是无定义，不是 0"


def test_short_window_falls_to_watch_and_never_flaky():
    """窗口 run 数 < `min_runs_for_flaky` → 一律 watch（**不得输出 flaky**）。"""
    min_runs = int(_rules()["min_runs_for_flaky"])
    history = _hist(*("pf" * (min_runs - 1)))  # 交替，但样本不足
    profile = flaky.classify(history, _rules())
    assert profile.label == flaky.fallback_label(_rules())
    assert profile.label != flaky.LABEL_FLAKY


def test_short_window_threshold_comes_from_rules():
    """门槛取自规则包：把 `min_runs_for_flaky` 调大，同样的序列就落 watch。"""
    history = _hist(*"pfpfpf")
    assert flaky.classify(history, _rules()).label == flaky.LABEL_FLAKY
    stricter = dict(_rules())
    stricter["min_runs_for_flaky"] = len(history) + 1
    assert flaky.classify(history, stricter).label == flaky.fallback_label(stricter)


def test_thresholds_come_from_rules_not_hardcoded():
    """把阈值改成一组"任何序列都进不了 flaky"的值，分型必须随之改变。"""
    history = _hist(*"pfpfpf")
    assert flaky.classify(history, _rules()).label == flaky.LABEL_FLAKY
    impossible = dict(_rules())
    impossible["min_transitions"] = 999
    assert flaky.classify(history, impossible).label == flaky.fallback_label(impossible)


# ── 互斥：broken ∩ flaky == ∅（独立断言，不靠内部顺序自证）──────────────


def _profiles_for(histories):
    ruleset = _rules()
    return [flaky.classify(_hist(*seq), ruleset) for seq in histories]


def test_broken_and_flaky_sets_are_disjoint_independently():
    """拿一份固定 fixture 的两份集合求交——**不靠分类函数内部顺序自证**。

    判据是"两个集合有没有交集"，与"先判哪个分支"无关：即便把分型顺序改成
    先判 flaky，只要恒失败样本没有被判进 flaky，这条照样过；反之必红。
    """
    fixtures = [
        "ffffff", "pppppp", "pfpfpf", "pppfff", "ppffppff", "sfsfsf", "mmppmm",
        "ppppppppppf", "ffffffffffp", "pfp", "ff", "pp",
    ]
    profiles = _profiles_for(fixtures)
    broken = {seq for seq, p in zip(fixtures, profiles) if p.label == flaky.LABEL_BROKEN}
    flaky_set = {seq for seq, p in zip(fixtures, profiles) if p.label == flaky.LABEL_FLAKY}
    assert broken, "fixture 里没有恒失败样本（判据空转）"
    assert flaky_set, "fixture 里没有抖动样本（判据空转）"
    assert broken & flaky_set == set(), broken & flaky_set


def test_flaky_broken_excluded():
    """`plan/06` §一 点名的判据：**恒失败不进 flaky 列表**（独立断言）。

    与上一条同源，但这里直接用"标签名"表达 DoD 的措辞：一个 fail_rate == 1
    的样本，无论窗口多长、transitions 门槛怎么调，都不得出现在 flaky 集合里。
    """
    ruleset = _rules()
    broken_case = _hist(*("f" * 12))
    flaky_case = _hist(*"pfpfpfpfpfpf")
    broken_profile = flaky.classify(broken_case, ruleset)
    flaky_profile = flaky.classify(flaky_case, ruleset)
    assert broken_profile.label == flaky.LABEL_BROKEN
    assert flaky_profile.label == flaky.LABEL_FLAKY
    flaky_set = {name for name, profile in
                 (("broken", broken_profile), ("flaky", flaky_profile))
                 if profile.label == flaky.LABEL_FLAKY}
    assert "broken" not in flaky_set


def test_all_fail_never_lands_in_flaky_even_with_forced_order():
    """恒失败样本在任何阈值下都不会被判成 flaky（`transitions` 恒为 0）。"""
    history = _hist(*"ffffffff")
    for min_transitions in (1, 2, 3, 5):
        ruleset = dict(_rules())
        ruleset["min_transitions"] = min_transitions
        assert flaky.classify(history, ruleset).label != flaky.LABEL_FLAKY


# ── label_counts 辅助 ──────────────────────────────────────────────────


def test_label_counts_tallies_by_label():
    profiles = _profiles_for(["pppp", "ffff", "pfpfpf", "pppfff"])
    counts = flaky.label_counts(profiles)
    assert counts.get(flaky.LABEL_STABLE) == 1
    assert counts.get(flaky.LABEL_BROKEN) == 1
    assert counts.get(flaky.LABEL_FLAKY) == 1


def test_profile_renders_exact_decimal_strings():
    profile = flaky.classify(_hist(*"pfpf"), _rules())
    assert profile.flaky_score_text == "1"
    assert profile.fail_rate_text == "0.5"  # 终止小数按十进制写出


def test_classify_is_pure_no_io(monkeypatch):
    """纯函数：不读时钟、不开文件。把 `open` 换成会抛的实现，classify 仍能跑。"""
    import builtins
    ruleset = _rules()  # 规则在**打桩之前**载入（classify 自身不该碰 IO）
    real_open = builtins.open

    def _boom(*args, **kwargs):  # pragma: no cover - 走到这里说明 classify 碰了 IO
        raise AssertionError("classify 不应打开任何文件")

    monkeypatch.setattr(builtins, "open", _boom)
    try:
        profile = flaky.classify(_hist(*"pfpfpf"), ruleset)
    finally:
        monkeypatch.setattr(builtins, "open", real_open)
    assert profile.label in (flaky.LABEL_FLAKY, flaky.fallback_label(ruleset))


def test_label_names_come_from_rules():
    """分型名取自规则包 `labels` 表（不在代码里另写一套名字）。"""
    labels = _rules()["labels"]
    for key in flaky.LABEL_KEYS:
        assert key in labels, "规则包 labels 表缺 %s" % key
    assert flaky.fallback_label(_rules()) == _rules()["fallback_label"]
    # 代码侧登记的三个稳定名 + 兜底名，与规则包一一对应
    assert set(flaky.LABEL_KEYS) == {k for k in labels if k != _rules()["fallback_label"]}


def test_label_name_falls_back_when_rule_table_missing_key():
    """规则表缺某个键 → 退回代码侧稳定名（不崩、不返回空）。"""
    ruleset = dict(_rules())
    ruleset["labels"] = {}
    assert flaky.label_name(ruleset, flaky.LABEL_FLAKY, flaky.LABEL_FLAKY) == flaky.LABEL_FLAKY
