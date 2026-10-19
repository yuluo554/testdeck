"""慢测试与回归（`plan/03` 模块④ / `plan/02` 判定层）：纯函数，不碰 IO、不读时钟。

口径（`data/README.md` §四，唯一真相源）：

| 量 | 定义 |
| --- | --- |
| 分位数 | 线性插值：索引 `(n - 1) * p`，取 floor / ceil 两点按小数部分插值 |
| 缺失耗时 | `None` **不进样本、不补 0**（K28） |
| 回归判定 | `curr / base >= ratio` **且** `curr - base >= delta_ms`（两处边界都计入，`>=`） |
| 回归不可判 | `base == 0` → `undefined_base`；任一侧无样本 → `missing_window` |

阈值与分位数**全部从 `rules/slow.json` 读**——本模块里不得出现阈值字面量
（`tests/test_no_rule_literals.py` 扫描数值常量；只豁免 `0` / `1` 这类结构常量）。

**为什么"不可判"返回 `None` 而不是 `False`**：`False` 是"判过了、没回归"的结论，
`None` 是"判不了"。把两者混同，CI 门禁就会在样本不足时**静默放行**——而那恰恰是
它该拦住的情形（与 K34 对零计数 `fail_rate` 的处理同一条纪律）。

**切分点不在本模块发明**：`regression(base_p50, curr_p50, rules)` 只接两个**已算好的**
分位数。"窗口前段 / 后段怎么切"由**输入侧**给出——合成台账显式存 `regression_split`，
TUI 侧由编排层按窗口中点切（`queries.slow_profiles`）。判定层不猜切分
（`data/README.md` §四「回归窗口」）。

**瀑布条宽度**：`bar_width(time_ms, max_time_ms, width)` 用**整数运算**做四舍五入
（余数加倍与除数比较），不走浮点除法、也不用 Python `round()`——后者的银行家舍入
在 `.5` 边界给出与"四舍五入"不同的答案（`round(0.5) == 0`），会让同样的数据
因表示方式不同而落在条宽两侧。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, List, Optional, Sequence, Tuple

from . import model

#: 回归不可判的两个原因码（与 `bench/refimpl.py` 同形，供逐值对账）
NOTE_UNDEFINED_BASE = "undefined_base"
NOTE_MISSING_WINDOW = "missing_window"

#: 两条**样本量降级**的标注（`plan/03` 模块④）
LABEL_SINGLE_SAMPLE = "single_sample"
LABEL_INSUFFICIENT_HISTORY = "insufficient_history"


# ── 分位数（线性插值）───────────────────────────────────────────────────


def samples(timings: Iterable[Optional[int]]) -> List[int]:
    """缺失耗时（``None``）**不进样本、不补 0**（K28：缺失 ≠ 0）。"""
    return [t for t in timings if t is not None]


def percentile(values: Sequence[int], p) -> Optional[Fraction]:
    """线性插值分位数：索引 ``(n - 1) * p``，floor / ceil 两点按小数部分插值。

    - 输入按值**升序排序**（稳定；输入顺序不影响结果）；
    - 空样本 → ``None``（不是 0：没有样本不等于"耗时为 0"）；
    - 单样本 → 该值；
    - ``p`` 可为规则包里的 ``Decimal`` / 十进制字符串 / ``Fraction``，一律走
      `model.as_fraction`（**不用 float**——浮点会让边界样本掷硬币）。

    与 `bench/refimpl.py:percentile` 是两份独立实现，漂移由 `bench/bench_slow.py`
    的逐值对账抓（参照实现不得 import 生产模块）。
    """
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    if n == 1:
        return Fraction(ordered[0])
    idx = Fraction(n - 1) * model.as_fraction(p)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return Fraction(ordered[lo])
    frac = idx - lo
    return Fraction(ordered[lo]) + (Fraction(ordered[hi]) - Fraction(ordered[lo])) * frac


def p50(timings: Sequence[Optional[int]], rules) -> Optional[Fraction]:
    """窗口内 p50（缺失耗时先剔出样本）。"""
    return percentile(samples(timings), rules["p50"])


def p95(timings: Sequence[Optional[int]], rules) -> Optional[Fraction]:
    """窗口内 p95。"""
    return percentile(samples(timings), rules["p95"])


# ── 回归判定（两处边界都计入）──────────────────────────────────────────


def regression(base_p50, curr_p50, rules) -> Tuple[Optional[bool], str]:
    """``curr / base >= ratio`` **且** ``curr - base >= delta_ms``（边界计入）。

    返回 ``(hit, note)``：

    - ``hit`` 是 ``True`` / ``False``（判过了）或 ``None``（**判不了**）；
    - 任一侧无样本（``None``）→ ``(None, "missing_window")``；
    - ``base_p50 == 0`` → ``(None, "undefined_base")``——比值为 0/0，不判回归，
      也**不谎报"无回归"**；
    - 其余 → ``(bool, "ratio=…(>=/<) delta=…ms(>=/<)")``。

    全程精确有理数（`Fraction`）：`ratio` 恰为 1.2、`delta` 恰为 200ms 这类边界
    必须精确落侧，浮点会让"恰好等于阈值"的样本随机落两侧。
    """
    ratio = model.as_fraction(rules["regression_ratio"])
    delta = int(rules["regression_delta_ms"])
    if base_p50 is None or curr_p50 is None:
        return None, NOTE_MISSING_WINDOW
    base = Fraction(base_p50)
    curr = Fraction(curr_p50)
    if base == 0:
        return None, NOTE_UNDEFINED_BASE
    actual_ratio = curr / base
    actual_delta = curr - base
    hit = actual_ratio >= ratio and actual_delta >= delta
    note = "ratio=%s(%s) delta=%sms(%s)" % (
        model.render_exact(actual_ratio),
        ">=" if actual_ratio >= ratio else "<",
        model.render_exact(actual_delta),
        ">=" if actual_delta >= delta else "<",
    )
    return hit, note


def sample_label(total_samples: int, base_samples: int, curr_samples: int) -> str:
    """样本量降级标注（`plan/03` 模块④ 的两条）。

    - 总样本 ``0`` → ``insufficient_history``（一个耗时样本都没有：p50/p95 都无定义）；
    - 总样本恰 ``1`` → ``single_sample``（p50 == p95 == 该值，比不出趋势）；
    - 样本够多但回归窗口任一侧无样本 → ``insufficient_history``（回归判定落
      ``missing_window``）；
    - 其余 → 空串（样本够）。

    **顺序**：`single_sample` 先判——只有 1 个样本时"趋势比不出来"是更贴切的描述；
    两侧样本不足的 `insufficient_history` 留给"样本不止一个、但切分后某侧为空"。
    """
    if total_samples == 0:
        return LABEL_INSUFFICIENT_HISTORY
    if total_samples <= 1:
        return LABEL_SINGLE_SAMPLE
    if base_samples == 0 or curr_samples == 0:
        return LABEL_INSUFFICIENT_HISTORY
    return ""


def is_slow(time_ms: Optional[int], rules) -> bool:
    """该耗时是否达到"慢"的门槛（``slow_ms`` 来自规则包）。

    ``None``（没声明耗时）**不算慢**——缺失不等于 0，也不等于"慢"。
    summary 的 `slow` 字段读的就是这个（阈值单点在规则包，代码里不出现字面量）。
    """
    if time_ms is None:
        return False
    return int(time_ms) >= int(rules["slow_ms"])


# ── 瀑布条宽度（整数运算）───────────────────────────────────────────────


def bar_width(time_ms: int, max_time_ms: int, width: int) -> int:
    """瀑布条宽度 = ``round(time_ms / max_time_ms * width)``，**整数运算**。

    - ``max_time_ms == 0`` → 全宽 0（不能除零，也不谎报"有耗时"）；
    - 四舍五入用"余数加倍与除数比较"实现：`round()` 的银行家舍入在 ``.5`` 边界
      给出与"四舍五入"不同的答案，浮点除法又会引入表示抖动。

    显示宽度（`width`）来自 `rules/slow.json` 的 ``waterfall_width``。
    """
    divisor = int(max_time_ms)
    if divisor == 0:
        return 0
    quotient, remainder = divmod(int(time_ms) * int(width), divisor)
    return quotient + (1 if remainder + remainder >= divisor else 0)


# ── 单用例的慢测试画像（给 `S` 视图与导出门禁用）───────────────────────


@dataclass(frozen=True)
class SlowProfile:
    """一条用例的慢测试画像（**全部为精确值**，渲染是呈现层的事）。

    ``p50`` / ``p95`` 取**窗口内全部耗时样本**；``base_p50`` / ``curr_p50`` 取
    窗口前段 / 后段（切分点由调用方给出，见模块 docstring）；``regression`` 是
    `regression` 的三态结论，``label`` 是样本量降级标注。
    """

    case_id: int
    suite_name: str
    classname: str
    name: str
    time_ms: Optional[int]
    p50: Optional[Fraction]
    p95: Optional[Fraction]
    base_p50: Optional[Fraction]
    curr_p50: Optional[Fraction]
    regression: Optional[bool]
    note: str
    label: str
    samples: int
    base_samples: int
    curr_samples: int

    @property
    def is_regression(self):
        return self.regression is True

    @property
    def p50_text(self):
        return model.render_exact(self.p50)

    @property
    def p95_text(self):
        return model.render_exact(self.p95)

    @property
    def regression_text(self):
        """回归列的三态渲染：``True`` / ``False`` / ``?``（判不了，K28 同源纪律）。"""
        if self.regression is None:
            return "?"
        return "yes" if self.regression else "no"


def profile_case(case_id, suite_name, classname, name, time_ms, timings,
                 split, rules) -> SlowProfile:
    """把一条用例的窗口耗时序列判成 `SlowProfile`（``split`` 由**调用方**给出）。

    ``timings`` 按 run 升序（含缺失的 ``None`` 占位）；``split`` 是前段/后段的切分点：

    - ``split`` 是 ``int``（``0 <= split <= len(timings)``）→ 按它切前段/后段；
    - ``split`` 为 ``None``（或越界）→ **没有回归窗口**：``base_p50`` / ``curr_p50``
      都是 ``None``，回归判定落 `missing_window`。**不发明切分点**——"没有窗口"
      与"窗口是空的前段"不是一回事（`data/README.md` §四「回归窗口」）。

    判定只调本模块的 `percentile` / `regression`——调用方不复制口径。
    """
    window = list(timings)
    if isinstance(split, bool) or not isinstance(split, int) \
            or split <= 0 or split >= len(window):
        base_timings: List[Optional[int]] = []
        curr_timings: List[Optional[int]] = []
        has_window = False
    else:
        base_timings = window[:split]
        curr_timings = window[split:]
        has_window = True
    base_p50 = p50(base_timings, rules) if has_window else None
    curr_p50 = p50(curr_timings, rules) if has_window else None
    hit, note = regression(base_p50, curr_p50, rules)
    total = len(samples(window))
    base_count = len(samples(base_timings))
    curr_count = len(samples(curr_timings))
    label = sample_label(total, base_count, curr_count)
    return SlowProfile(
        case_id=case_id, suite_name=suite_name, classname=classname, name=name,
        time_ms=time_ms,
        p50=p50(window, rules), p95=p95(window, rules),
        base_p50=base_p50, curr_p50=curr_p50,
        regression=hit, note=note, label=label,
        samples=total, base_samples=base_count, curr_samples=curr_count,
    )


def regression_list(profiles: Iterable[SlowProfile]) -> List[SlowProfile]:
    """回归清单：``regression is True`` 的画像（`--fail-on regressions` 读它）。

    只收 ``True``——``None``（判不了）不进清单：把"判不了"当成"回归"会误报，
    当成"无回归"会漏报，两种都不诚实（`plan/03` 模块④ 降级条）。
    """
    return [profile for profile in profiles if profile.regression is True]
