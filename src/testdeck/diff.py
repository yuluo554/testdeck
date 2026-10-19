"""两次 run 的用例级 diff（`plan/03` 模块④ / 模块② 的 `D` 视图）：判定层纯函数。

输入是两次 run 的**原始状态对**（`queries.diff_rows` 的 `DiffRow`，任一侧缺行记
``None``），输出是**三类分类** + 一个"其余"桶：

| 类 | 条件 | 含义 |
| --- | --- | --- |
| `new-failures` | `after == fail` 且 `before != fail` | 这次新坏的（相对 base run 新增的失败） |
| `fixed` | `before == fail` 且 `after == pass` | 上次坏、这次**跑过且过了** |
| `still-failing` | `before == fail` 且 `after == fail` | 一直坏 |
| `unchanged` | 其余组合 | 不在上面三类里的一切 |

三条口径纪律（都不是"顺手分类"，是判定的一部分）：

1. **`fixed` 要求 `after == pass`**：`fail→skip` / `fail→缺` 落 `unchanged`，
   **不是** `fixed`。没有 `pass` 就没有"修好了"的证据——把"这次没跑/被跳过"
   算成"修复"会让"修复数"虚高，正是 `--fail-on new-failures` 想抓的那种自欺。
2. **缺行（``None``）不等于任何状态**（K24/K28 的同一条纪律）：`缺→fail` 是
   `new-failures`（base 里没有、这次坏了），而 `fail→缺` 落 `unchanged`。
3. **判定不读规则包**：diff 的三类完全由**状态对**决定，没有阈值可调；
   所以本模块不 import `rules`，也不含任何数值常量。

`CLASS_ORDER` 是**展示与对账的固定顺序**（新增失败在前——它是门禁要拦的那一类）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import model

#: 三类（对账对象）+ 其余桶
NEW_FAILURES = "new-failures"
FIXED = "fixed"
STILL_FAILING = "still-failing"
UNCHANGED = "unchanged"

#: 固定展示顺序：新增失败在前（门禁拦的就是这一类），其余在后
CLASS_ORDER = (NEW_FAILURES, FIXED, STILL_FAILING, UNCHANGED)

#: 三类对账对象（DoD 逐类断言的就是这三个；`unchanged` 是兜底桶，不参与对账）
RECONCILED_CLASSES = (NEW_FAILURES, FIXED, STILL_FAILING)

#: 每类的展示标题（TUI `D` 视图与 M5 的 md 导出共用同一份文案）
CLASS_TITLES = {
    NEW_FAILURES: "新增失败",
    FIXED: "修复",
    STILL_FAILING: "仍失败",
    UNCHANGED: "其余（未分类）",
}


@dataclass(frozen=True)
class ClassifiedDiff:
    """一条用例 + 它的分类（`row` 是原始状态对，`kind` 是 `CLASS_ORDER` 之一）。"""

    kind: str
    row: object  # queries.DiffRow（这里不 import 编排层，避免判定层依赖向上）

    @property
    def case_id(self):
        return self.row.case_id

    @property
    def display(self):
        before = self.row.status_before or "(缺)"
        after = self.row.status_after or "(缺)"
        return "%s::%s  %s→%s" % (self.row.classname, self.row.name, before, after)


def classify(status_before: Optional[str], status_after: Optional[str]) -> str:
    """一对原始状态 → 分类名（`CLASS_ORDER` 之一）。判定完全由状态对决定。"""
    if status_after == model.STATUS_FAIL and status_before != model.STATUS_FAIL:
        return NEW_FAILURES
    if status_before == model.STATUS_FAIL and status_after == model.STATUS_PASS:
        return FIXED
    if status_before == model.STATUS_FAIL and status_after == model.STATUS_FAIL:
        return STILL_FAILING
    return UNCHANGED


def classify_rows(rows: Iterable[object]) -> List[ClassifiedDiff]:
    """给每条 `DiffRow` 打上分类（顺序沿用传入顺序——排序单点在 `queries`）。"""
    return [
        ClassifiedDiff(classify(row.status_before, row.status_after), row)
        for row in rows
    ]


def group_rows(classified: Sequence[ClassifiedDiff]) -> Dict[str, List[ClassifiedDiff]]:
    """按 `CLASS_ORDER` 分桶（每桶保持传入顺序；缺桶给空列表，呈现层不必判 None）。"""
    groups: Dict[str, List[ClassifiedDiff]] = {kind: [] for kind in CLASS_ORDER}
    for entry in classified:
        groups[entry.kind].append(entry)
    return groups


def counts(classified: Iterable[ClassifiedDiff]) -> Dict[str, int]:
    """每类的条数（`--fail-on new-failures` 读的就是 `counts[NEW_FAILURES] > 0`）。"""
    result = {kind: 0 for kind in CLASS_ORDER}
    for entry in classified:
        result[entry.kind] = result.get(entry.kind, 0) + 1
    return result


def new_failure_count(classified: Iterable[ClassifiedDiff]) -> int:
    """新增失败数（`plan/03` 模块⑤ 的 `--fail-on new-failures` 命中条件）。"""
    return counts(classified)[NEW_FAILURES]
