"""flaky 分型（`plan/03` 模块③ / `plan/02` 判定层）：纯函数，不碰 IO、不读时钟。

输入是**内存里的状态序列**（`[(run_seq, status), ...]` 升序），输出是不可变的
`CaseProfile`。阈值 / 窗口 / 兜底标签**全部从 `rules/flaky.json` 读**——本模块里
不得出现阈值字面量（`tests/test_no_rule_literals.py` 扫描数值常量）。

口径（`data/README.md` §四，唯一真相源）：

| 量 | 定义 |
| --- | --- |
| 分母 | 只含 `pass` / `fail`；`skip` / `missing` **既不进分母，也不制造 transition** |
| `transitions` | 相邻两个"参与计数"的 run 状态不同则 +1（中间的 skip/missing 被跳过） |
| `flaky_score` | `transitions / (n - 1)`，`n` = 参与计数的次数；`n < 2` → `0` |
| 分型 | `fail_rate == 1` → `broken`；`== 0` → `stable`；`0.05 ≤ fail_rate ≤ 0.95` 且 `transitions ≥ min_transitions` → `flaky`；其余 → `watch` |

两条**降级**（都不是"顺手算"，是口径的一部分）：

1. **窗口样本不足**：窗口内 run 数 `< min_runs_for_flaky` → 一律 `watch`
   （**不得输出 flaky**）——2 次 run 的 `transitions/(n-1)` 极不稳定。
2. **零计数样本**（K34）：`n == 0`（该用例在所有 run 都是 skip/missing）时
   `fail_rate` 是 0/0、**无定义** → 一律 `watch`。**不得判成 `stable`**：
   "一次都没真正跑过"不构成"稳定"证据，判成 stable 会让 stable 计数虚高，
   把"这个用例根本没在跑"这类真问题藏起来。

**为什么分型顺序里 `broken` 排在 `flaky` 之前**：`fail_rate == 1` 的用例
`transitions` 恒为 0，本就进不了 `flaky` 区间；但"先判恒失败"让这条**在结构上**
不可能被后置条件改写。集合互斥另有一条**独立断言**（不靠这里的顺序自证，见
`tests/test_flaky.py` 与 `bench/bench_flaky.py`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, List, Optional, Sequence, Tuple

from . import model

#: 四个分型名（`watch` 取规则包的 `fallback_label`；其余三个是稳定名）
LABEL_STABLE = "stable"
LABEL_FLAKY = "flaky"
LABEL_BROKEN = "broken"

#: 规则包 `labels` 表里登记的分型（代码侧的稳定名；规则包是"有哪些标签"的来源）
LABEL_KEYS = (LABEL_STABLE, LABEL_FLAKY, LABEL_BROKEN)


@dataclass(frozen=True)
class CaseProfile:
    """一条用例在窗口内的分型画像（**全部为精确值**，渲染是呈现层的事）。"""

    label: str
    counted_runs: int
    passes: int
    fails: int
    fail_rate: Optional[Fraction]
    transitions: int
    flaky_score: Fraction

    @property
    def is_flaky(self):
        return self.label == LABEL_FLAKY

    @property
    def is_broken(self):
        return self.label == LABEL_BROKEN

    @property
    def fail_rate_text(self):
        return model.render_exact(self.fail_rate)

    @property
    def flaky_score_text(self):
        return model.render_exact(self.flaky_score)


def label_name(rules, key, default=None):
    """分型名取自规则包的 `labels` 表；表里没这个键时退回 `default or key`。

    与参照实现（`bench/refimpl.py:_label_name`）同形——两边各自从**自己的**
    规则来源取名，漂移由 `bench/bench_flaky.py` 的逐值对账抓。
    """
    labels = rules.get("labels")
    if isinstance(labels, dict) and key in labels:
        return key
    return default or key


def fallback_label(rules):
    """兜底分型名（`watch`）——**只从规则包读**，不在代码里写死。"""
    return rules["fallback_label"]


def counted_statuses():
    """参与计数的状态（单点在 `model.COUNTED_STATUSES`，此处只做转发）。"""
    return model.COUNTED_STATUSES


def _counted(statuses: Iterable[str]) -> List[str]:
    counted = counted_statuses()
    return [status for status in statuses if status in counted]


def _transitions(counted: Sequence[str]) -> int:
    """相邻两个参与计数的 run 状态不同则 +1（skip/missing 已被剔除，不制造 transition）。"""
    return sum(1 for left, right in zip(counted, counted[1:]) if left != right)


def classify(history: Iterable[Tuple[int, str]], rules) -> CaseProfile:
    """把一条用例的历史（``[(run_seq, status), ...]`` 升序）判成一个 `CaseProfile`。

    ``rules`` 是 `rules.load_flaky_rules()` 的返回值（阈值已在加载时转成 `Decimal`）。
    """
    statuses = [status for _run_seq, status in history]
    counted = _counted(statuses)
    counted_runs = len(counted)
    passes = counted.count(model.STATUS_PASS)
    fails = counted.count(model.STATUS_FAIL)
    transitions = _transitions(counted)

    fail_rate = model.mean_fraction(fails, counted_runs)
    # n < 2 时 flaky_score = 0（单点表达式用 1 而非 2，避免与规则阈值字面量撞车）
    flaky_score = (Fraction(transitions, counted_runs - 1) if counted_runs > 1
                   else Fraction(0))

    min_rate = model.as_fraction(rules["min_fail_rate"])
    max_rate = model.as_fraction(rules["max_fail_rate"])
    min_transitions = int(rules["min_transitions"])
    min_runs = int(rules["min_runs_for_flaky"])
    fallback = fallback_label(rules)

    # 降级先判（两条都不是"顺手算"，是口径的一部分）：窗口不足 / 零计数样本。
    if len(statuses) < min_runs or counted_runs == 0:
        label = fallback
    elif fail_rate == 1:
        label = label_name(rules, LABEL_BROKEN, LABEL_BROKEN)
    elif fail_rate == 0:
        label = label_name(rules, LABEL_STABLE, LABEL_STABLE)
    elif min_rate <= fail_rate <= max_rate and transitions >= min_transitions:
        label = label_name(rules, LABEL_FLAKY, LABEL_FLAKY)
    else:
        label = fallback

    return CaseProfile(
        label=label,
        counted_runs=counted_runs,
        passes=passes,
        fails=fails,
        fail_rate=fail_rate,
        transitions=transitions,
        flaky_score=flaky_score,
    )


def label_counts(profiles: Iterable[CaseProfile]) -> dict:
    """按分型计数（返回的键集合来自规则包登记的标签 + 兜底标签）。"""
    counts = {}
    for profile in profiles:
        counts[profile.label] = counts.get(profile.label, 0) + 1
    return counts
