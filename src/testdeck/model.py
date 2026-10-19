"""四态、耗时与**精确有理数渲染**的单点定义。

状态枚举、耗时单位、舍入规则与"百分比值怎么渲染"都只在这里出现；
`flaky.py` / `slow.py` / `queries.py` 一律从这里取，不得另写字面量。

**为什么渲染也要单点**：`data/README.md` §四 规定 `fail_rate` / `flaky_score` / p50 / p95
一律以精确有理数（`Fraction`）运算、渲染为**终止十进制串**（不终止时用 `p/q`），
且**禁用 float**。判定层与参照实现（`bench/refimpl.py`）各自实现这条渲染规则，
两者是否漂移由 `bench/bench_flaky.py` 的逐值对账抓（参照实现不得 import 生产模块）。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext
from fractions import Fraction

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"
STATUS_MISSING = "missing"

#: 四态（顺序即矩阵单元格图例顺序，不随实现漂移）
STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_SKIP, STATUS_MISSING)

#: 参与 fail_rate / flaky_score 计数的状态；skip 与 missing 不进分母、不制造 transition
COUNTED_STATUSES = (STATUS_PASS, STATUS_FAIL)

#: 矩阵单元格图例（唯一来源，TUI 与导出共用）
STATUS_GLYPHS = {
    STATUS_PASS: "\u00b7",      # ·
    STATUS_FAIL: "\u2717",      # ✗
    STATUS_SKIP: "-",
    STATUS_MISSING: "?",
}

#: 精确十进制渲染时 `Decimal` 上下文的精度（只影响"终止小数有多长"，
#: 不影响判定——判定全程走 `Fraction`）
RENDER_PRECISION = 80

#: 把分母约成"只含 2 与 5 的幂"时要试除的素数（终止小数的充要条件）
_TERMINATING_PRIMES = (2, 5)



def seconds_to_ms(value):
    """XML 十进制秒 -> 整数毫秒，ROUND_HALF_UP。

    ``None`` / 空串 -> ``None``（缺失不等于 0，不能补零）。
    非法数值抛 ``ValueError``，由解析层按**单项降级**处理（`time_ms` 记 ``None``，
    并计入摘要的 `degraded: bad_time`）——不整文件报废，也不静默当成 0。
    """
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        seconds = Decimal(text)
    except InvalidOperation:
        raise ValueError("not a decimal number: %r" % (value,))
    if not seconds.is_finite():
        raise ValueError("not a finite number: %r" % (value,))
    return int((seconds * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def is_counted(status):
    """该状态是否进入 fail_rate / flaky_score 的统计面。"""
    return status in COUNTED_STATUSES


def validate_status(status):
    if status not in STATUSES:
        raise ValueError("unknown status: %r" % (status,))
    return status


# ── 精确有理数 → 展示串（`data/README.md` §四 的"百分比值渲染"）──────────


def as_fraction(value):
    """把规则里的十进制字符串（``"0.05"`` / ``"1.2"``）或 ``Decimal`` 转成精确 `Fraction`。

    **不用 float**：`fail_rate` 的 5%/95% 边界与回归比值 1.2 必须精确比较——
    浮点会让"恰好等于阈值"的样本随机落到某一侧（`test_rules.py` 用
    `0.1 + 0.2 != 0.3` 反证过这条）。
    """
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        raise TypeError("阈值不得用 float 传入（浮点会让边界判定掷硬币）")
    return Fraction(str(value))


def render_exact(value):
    """`Fraction` → 精确十进制串（**终止**小数）；不终止时用 ``p/q``；``None`` → ``None``。

    这条渲染规则是**唯一**的：`flaky.py` / `slow.py` 与导出都调它。参照实现
    （`bench/refimpl.py`）有一份独立实现，两者漂移由 `bench/bench_flaky.py` 的对账抓。
    """
    if value is None:
        return None
    if not isinstance(value, Fraction):
        value = as_fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    reduced = value.denominator
    for prime in _TERMINATING_PRIMES:
        while reduced % prime == 0:
            reduced //= prime
    if reduced != 1:
        # 1/3 这类非终止小数：用 p/q 如实写出，不四舍五入成假精度
        return "%d/%d" % (value.numerator, value.denominator)
    with localcontext() as ctx:
        ctx.prec = RENDER_PRECISION
        dec = Decimal(value.numerator) / Decimal(value.denominator)
    return format(dec, "f")


def mean_fraction(total, count):
    """``total / count`` 的精确 `Fraction`；``count == 0`` → ``None``（分母无定义）。

    零计数样本（全 skip/missing）的 `fail_rate` 就是 0/0：这里返回 ``None`` 而不是
    ``Fraction(0)``——"一次都没跑过"与"跑过且从没失败"必须区分开（K34）。
    """
    if not count:
        return None
    return Fraction(int(total), int(count))

