"""四态与耗时的单点定义。

状态枚举、耗时单位与舍入规则都只在这里出现；`flaky.py` / `slow.py` /
`queries.py` 一律从这里取，不得另写字面量。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

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


def seconds_to_ms(value):
    """XML 十进制秒 -> 整数毫秒，ROUND_HALF_UP。

    ``None`` / 空串 -> ``None``（缺失不等于 0，不能补零）。
    非法数值抛 ``ValueError``，由解析层计入 ``skipped:bad_time``。
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
