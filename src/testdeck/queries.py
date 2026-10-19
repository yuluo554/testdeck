"""只读查询层（`plan/02` 编排层 / `plan/03` 模块②）：TUI 与导出共用的一层 SQL。

三条纪律：

1. **只读**：只发 ``SELECT``；不建表、不写库、不读时钟（判定与展示必须可重放）。
2. **返回纯 dataclass / dict，绝不返回 Textual 对象**——所以除了 Pilot 之外，
   还有一条"无头"通路可以把 UI 上的数字逐项对回 SQL（M3 DoD 第 4 条）。
3. **失败优先排序的单点在本模块**：树（TUI）与导出都调 `tree_rows` / `order_*`，
   别处再写一份排序就会出现"屏幕上的顺序"和"导出里的顺序"两套口径。

分类与分位数**不在本模块的代码里**：`flaky` / `broken` 两个 summary 字段与矩阵的
行序由 M4 的 `flaky.py` 填；`slow` 与慢测试画像由 M5 的 `slow.py` 填（本模块只
**调用**它，不复制它的口径——依赖方向是编排层 → 判定层，合法）。

**窗口切分点**（`plan/03` 模块④ / `data/README.md` §四「回归窗口」）：合成台账把
`regression_split` 显式存在**输入侧**；库里的窗口没有这一列，所以本模块按**窗口中点**
（``len(window) // 2``）切前段/后段——切分点是"编排层的取数决定"，判定层
（`slow.py`）不发明它。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import flaky, model, rules, slow

#: summary 里**由 SQL 直出**的三个计数
COUNTED_SUMMARY_FIELDS = ("total", "fail", "skip")

#: summary 里**由判定层填**的字段：`flaky`/`broken` 由 `flaky.py`（M4）算，
#: `slow` 由 `slow.py`（M5）算。
PROFILE_SUMMARY_FIELDS = ("flaky", "broken")

#: summary 里"慢测试"那一格的口径：**本 run 里有耗时声明且达到 `slow_ms` 的用例数**
SLOW_SUMMARY_FIELD = "slow"

#: summary 里属于**后续里程碑**口径、此刻还没实装的字段。
#: M5 起为空（六个字段全部实装）——保留这个名字是为了让"不猜"这条纪律
#: 始终有一条可跑红的判据（`tests/test_queries.py::test_pending_summary_fields_are_not_guessed`
#: 断言这个集合里没有字段还是 ``None``；集合为空时它等价于"全都实装"）。
PENDING_SUMMARY_FIELDS = ()


RUN_FIELDS = ("run_id", "branch", "commit_sha", "ci_run_id", "started_at",
              "framework", "source_path")
SUITE_FIELDS = ("suite_id", "name", "source_path", "time_ms", "tests", "failures",
                "errors", "skipped")
CASE_FIELDS = ("case_id", "suite_name", "classname", "name", "status", "time_ms",
               "failure_type", "failure_message", "stack_first_line")


@dataclass(frozen=True)
class RunRow:
    run_id: int
    branch: str
    commit_sha: str
    ci_run_id: str
    started_at: str
    framework: str
    source_path: str


@dataclass(frozen=True)
class CaseRow:
    """一条 occurrence + 它的用例身份（`cases` 表 + `occurrences` 表连接的结果）。"""

    case_id: int
    suite_name: str
    classname: str
    name: str
    status: str
    time_ms: Optional[int]
    failure_type: str
    failure_message: str
    stack_first_line: str

    @property
    def failed(self):
        return self.status == model.STATUS_FAIL

    @property
    def label(self):
        """树上的用例标签：失败/跳过的前缀字形来自 `model.STATUS_GLYPHS`（单点）。"""
        glyph = model.STATUS_GLYPHS.get(self.status, "")
        if self.status in (model.STATUS_FAIL, model.STATUS_SKIP):
            return "%s %s" % (glyph, self.name)
        return self.name


@dataclass(frozen=True)
class SuiteRow:
    """一个 suite 节点：`cases` 已按**树序**（class 分组 → class 序 → case 序）排好。

    `cases` 里同一 ``classname`` 的行是连续的，所以呈现层按连续段切 class 节点即可，
    不需要再各自排一遍（排序单点 = `tree_rows`）。
    """

    suite_id: int
    name: str
    source_path: str
    time_ms: Optional[int]
    tests: int
    failures: int
    errors: int
    skipped: int
    cases: Tuple[CaseRow, ...] = ()

    @property
    def fail_count(self):
        return sum(1 for case in self.cases if case.failed)

    @property
    def class_groups(self):
        """``[(classname, (case, ...)), ...]``——连续同名列合并（保持树序）。"""
        groups = []
        for case in self.cases:
            if groups and groups[-1][0] == case.classname:
                groups[-1][1].append(case)
            else:
                groups.append((case.classname, [case]))
        return [(name, tuple(cases)) for name, cases in groups]


@dataclass(frozen=True)
class MatrixRow:
    """矩阵的一行：一条用例在窗口内各 run 的状态（``None`` = 该 run 没这条用例）。

    ``profile`` 是 `flaky.classify` 的结果（M4）：行序按 `flaky_score` 降序，
    分型（`flaky`/`broken`/`stable`/`watch`）也来自它——**判定在 `flaky.py`，
    这里只是把结果摆进矩阵**。
    """

    case_id: int
    suite_name: str
    classname: str
    name: str
    statuses: Tuple[Optional[str], ...]
    profile: Optional["flaky.CaseProfile"] = None

    @property
    def fail_count(self):
        return sum(1 for status in self.statuses if status == model.STATUS_FAIL)

    @property
    def label(self):
        return "" if self.profile is None else self.profile.label

    @property
    def flaky_score(self):
        return 0 if self.profile is None else self.profile.flaky_score



@dataclass(frozen=True)
class SlowRow:
    """有耗时声明的一条用例（缺失耗时**不补 0**，直接不进这张表）。"""

    case_id: int
    suite_name: str
    classname: str
    name: str
    time_ms: int
    profile: Optional["slow.SlowProfile"] = None

    @property
    def p50(self):
        return None if self.profile is None else self.profile.p50

    @property
    def p95(self):
        return None if self.profile is None else self.profile.p95

    @property
    def regression(self):
        return None if self.profile is None else self.profile.regression

    @property
    def label(self):
        return "" if self.profile is None else self.profile.label


@dataclass(frozen=True)
class DiffRow:
    """两次 run 的**原始状态对**（不做"新增失败/修复/仍失败"分类——那是 M4 `diff.py`）。"""

    case_id: int
    suite_name: str
    classname: str
    name: str
    status_before: Optional[str]
    status_after: Optional[str]

    @property
    def changed(self):
        return self.status_before != self.status_after


# ── run 维度 ──────────────────────────────────────────────────────────


def _run_row(row):
    return None if row is None else RunRow(*row)


def runs(conn) -> List[RunRow]:
    """全部 run，按 `run_id` 升序（= ingest 顺序，见 `history` 的次序说明）。"""
    cur = conn.execute("SELECT %s FROM runs ORDER BY run_id" % ", ".join(RUN_FIELDS))
    return [RunRow(*row) for row in cur.fetchall()]


def resolve_run(conn, run_id=None) -> Optional[RunRow]:
    """``run_id`` 为 ``None`` → 最近一次 run（`run_id` 最大）；查不到返回 ``None``。

    非整数的 ``run_id`` 一律当作"查不到"（调用方据此给退出码 3），不抛异常——
    CLI 的用法错误（exit 2）只留给参数面，不留给"库里有没有这条 run"。
    """
    if run_id is None:
        row = conn.execute(
            "SELECT %s FROM runs ORDER BY run_id DESC LIMIT 1" % ", ".join(RUN_FIELDS)
        ).fetchone()
        return _run_row(row)
    try:
        key = int(run_id)
    except (TypeError, ValueError):
        return None
    row = conn.execute(
        "SELECT %s FROM runs WHERE run_id = ?" % ", ".join(RUN_FIELDS), (key,)
    ).fetchone()
    return _run_row(row)


def previous_run(conn, run_id) -> Optional[RunRow]:
    """`run_id` 之前最近的一次 run（没有则 ``None``）——`D` 视图的"上一棒"。"""
    row = conn.execute(
        "SELECT %s FROM runs WHERE run_id < ? ORDER BY run_id DESC LIMIT 1"
        % ", ".join(RUN_FIELDS),
        (int(run_id),),
    ).fetchone()
    return _run_row(row)


# ── 用例 / suite ──────────────────────────────────────────────────────

_CASE_SELECT = (
    "SELECT o.case_id, c.suite_name, c.classname, c.name, o.status, o.time_ms, "
    "o.failure_type, o.failure_message, o.stack_first_line "
    "FROM occurrences o JOIN cases c ON c.case_id = o.case_id "
)


def run_cases(conn, run_id) -> List[CaseRow]:
    """该 run 的全部 occurrence（**未排序**；排序单点在 `tree_rows`）。"""
    cur = conn.execute(
        _CASE_SELECT + "WHERE o.run_id = ? ORDER BY c.suite_name, c.classname, c.name",
        (int(run_id),),
    )
    return [CaseRow(*row) for row in cur.fetchall()]


def suite_rows(conn, run_id) -> List[SuiteRow]:
    """该 run 的 suite 行（按 `suite_id` 升序 = XML 出现序），暂不带 cases。"""
    cur = conn.execute(
        "SELECT %s FROM suites WHERE run_id = ? ORDER BY suite_id" % ", ".join(SUITE_FIELDS),
        (int(run_id),),
    )
    return [
        SuiteRow(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], ())
        for row in cur.fetchall()
    ]


# ── 失败优先排序（**单点**）────────────────────────────────────────────


def fail_first_key(fail_count, secondary):
    """失败优先的排序键：同父节点下 ``fail_count > 0`` 的子树在前，其余按 `secondary`。

    这是"失败优先"在代码里的**唯一**落点：树、矩阵、瀑布都从这里取。
    """
    return (0 if fail_count > 0 else 1, secondary)


def order_cases(cases: Sequence[CaseRow]) -> List[CaseRow]:
    """同一 class 下的用例：失败在前，组内按 ``name`` 字典序。"""
    return sorted(cases, key=lambda case: fail_first_key(1 if case.failed else 0, case.name))


def order_classes(groups: Sequence[Tuple[str, Sequence[CaseRow]]]):
    """同一 suite 下的 class：有失败的 class 在前，组内按 ``classname`` 字典序。"""
    return sorted(
        groups,
        key=lambda item: fail_first_key(sum(1 for c in item[1] if c.failed), item[0]),
    )


def tree_rows(conn, run_id) -> List[SuiteRow]:
    """失败优先树（suite → class → case，三层各自失败优先）。

    suite 序：失败子树在前，组内按 `suite_id`（XML 出现序）升序——**不是**按名字，
    因为同一文件里的 suite 出现序是"框架自己的顺序"，名字排序会把它改掉。
    """
    pending: Dict[str, List[CaseRow]] = {}
    for case in run_cases(conn, run_id):
        pending.setdefault(case.suite_name, []).append(case)

    suites = []
    for row in suite_rows(conn, run_id):
        cases = pending.pop(row.name, [])
        ordered: List[CaseRow] = []
        buckets: Dict[str, List[CaseRow]] = {}
        for case in cases:
            buckets.setdefault(case.classname, []).append(case)
        for _classname, group in order_classes(list(buckets.items())):
            ordered.extend(order_cases(group))
        suites.append(
            SuiteRow(row.suite_id, row.name, row.source_path, row.time_ms, row.tests,
                     row.failures, row.errors, row.skipped, tuple(ordered))
        )

    # 防御：occurrence 的 suite_name 在 suites 表里没有对应行（理论上不该发生）——
    # 宁可多显示一个合成节点，也不静默丢掉用例。
    for name in sorted(pending):
        cases = order_cases(pending[name])
        suites.append(SuiteRow(-1, name, "", None, len(cases), 0, 0, 0, tuple(cases)))

    return sorted(suites, key=lambda suite: fail_first_key(suite.fail_count, suite.suite_id))


# ── summary / 详情 / 历史 ─────────────────────────────────────────────


def summary(conn, run_id, fields=None) -> Dict[str, Optional[int]]:
    """summary 字典（键序 = `view.json` 的 ``summary_fields``）。

    ``total`` / ``fail`` / ``skip`` 由 SQL 直出；``flaky`` / ``broken`` 由
    `flaky.py` 对**本 run 的每条用例**按窗口历史分型后计数（M4）；``slow`` 由
    `slow.py` 按**本 run 的耗时**计数（M5，见 `slow_summary_count`）。

    键序取自规则包，所以"屏幕上先显示哪个字段"也只有一个来源。
    """
    names = list(fields) if fields is not None else list(rules.load_view_rules()["summary_fields"])
    counts = dict.fromkeys(model.STATUSES, 0)
    cur = conn.execute(
        "SELECT status, COUNT(*) FROM occurrences WHERE run_id = ? GROUP BY status",
        (int(run_id),),
    )
    for status, how_many in cur.fetchall():
        counts[status] = how_many
    derived = {
        "total": sum(counts.values()),
        "fail": counts[model.STATUS_FAIL],
        "skip": counts[model.STATUS_SKIP],
    }
    derived.update(profile_summary_counts(conn, run_id))
    derived[SLOW_SUMMARY_FIELD] = slow_summary_count(conn, run_id)
    return {name: derived.get(name) for name in names}


def slow_summary_count(conn, run_id) -> int:
    """本 run 里"达到慢门槛"的用例数（判定**只调 `slow.is_slow`**，阈值取自规则包）。

    "没声明耗时"（``time_ms IS NULL``）不计入——缺失不等于 0，也不等于"慢"（K28）。
    """
    slow_rules = rules.load_slow_rules()
    cur = conn.execute(
        "SELECT time_ms FROM occurrences WHERE run_id = ? AND time_ms IS NOT NULL",
        (int(run_id),),
    )
    return sum(1 for (time_ms,) in cur.fetchall() if slow.is_slow(time_ms, slow_rules))


def profile_summary_counts(conn, run_id, window=None) -> Dict[str, int]:
    """本 run 的用例按窗口历史分型后，`flaky` / `broken` 各有多少条。

    窗口取 `view.sparkline_runs`（与矩阵同一窗口），所以"summary 里的 flaky 数"
    与"矩阵里标 flaky 的行数"是同一份判定结果，不是两套。
    """
    if window is None:
        window = rules.load_view_rules()["sparkline_runs"]
    profiles = case_profiles(conn, run_id, window)
    present = {
        row[0] for row in conn.execute(
            "SELECT DISTINCT case_id FROM occurrences WHERE run_id = ?", (int(run_id),))
    }
    result = {name: 0 for name in PROFILE_SUMMARY_FIELDS}
    for case_id in present:
        profile = profiles.get(case_id)
        if profile is None:
            continue
        if profile.label in result:
            result[profile.label] += 1
    return result


def case_profiles(conn, run_id, window) -> Dict[int, "flaky.CaseProfile"]:
    """窗口内每条用例的分型（`{case_id: CaseProfile}`）。

    历史序列取自 `window_runs`（升序）；判定**只调 `flaky.classify`**——本函数
    不复制任何阈值/顺序（判定层是 `flaky.py`，依赖方向编排 → 判定）。
    """
    flaky_rules = rules.load_flaky_rules()
    columns = window_runs(conn, run_id, window)
    column_ids = [run.run_id for run in columns]
    histories: Dict[int, List[Tuple[int, str]]] = {}
    if column_ids:
        placeholders = ", ".join("?" for _ in column_ids)
        cur = conn.execute(
            "SELECT case_id, run_id, status FROM occurrences "
            "WHERE run_id IN (%s) ORDER BY case_id, run_id" % placeholders,
            tuple(column_ids),
        )
        for case_id, row_run, status in cur.fetchall():
            histories.setdefault(case_id, []).append((row_run, status))
    return {case_id: flaky.classify(history, flaky_rules)
            for case_id, history in histories.items()}



def case_detail(conn, run_id, case_id) -> Optional[CaseRow]:
    """一条用例在该 run 的详情（含 failure 原文素材）；查不到返回 ``None``。"""
    row = conn.execute(
        _CASE_SELECT + "WHERE o.run_id = ? AND o.case_id = ?",
        (int(run_id), int(case_id)),
    ).fetchone()
    return None if row is None else CaseRow(*row)


def history(conn, case_id, window) -> List[Tuple[int, str]]:
    """最近 ``window`` 次 run 的状态序列，按 `run_id` **升序**。

    次序用 `runs.run_id`：它是 ingest 顺序，也是"产物没写 `started_at`"时唯一稳定的
    次序（K26 的必然结果——时间戳可能为空串，排序不能靠它）。
    """
    window = int(window)
    cursor = conn.execute(
        "SELECT run_id, status FROM occurrences WHERE case_id = ? "
        "ORDER BY run_id DESC LIMIT ?",
        (int(case_id), window),
    )
    rows = cursor.fetchall()
    return [(row[0], row[1]) for row in reversed(rows)]


# ── 三个视图（F / S / D）的取数：只取原始数据，不做分型/分位数/分类 ──────


def window_runs(conn, run_id, window) -> List[RunRow]:
    """截止 `run_id` 的最近 ``window`` 次 run（升序，含自身）。"""
    cur = conn.execute(
        "SELECT %s FROM runs WHERE run_id <= ? ORDER BY run_id DESC LIMIT ?"
        % ", ".join(RUN_FIELDS),
        (int(run_id), int(window)),
    )
    rows = [RunRow(*row) for row in cur.fetchall()]
    return list(reversed(rows))


def matrix_rows(conn, run_id, window) -> Tuple[List[RunRow], List[MatrixRow]]:
    """test × run 状态矩阵：``(run 列, 行)``。

    行序 = 窗口内 **`flaky_score` 降序**，同分按 ``(suite_name, classname, name)``
    字典序（`plan/03` 模块③）。`flaky_score` 与四类分型由 `flaky.classify` 判
    （M4）——本函数只负责把状态摆成矩阵并把判定结果挂上去，**不复制判定**。
    """
    columns = window_runs(conn, run_id, window)
    column_ids = [run.run_id for run in columns]
    statuses: Dict[int, Dict[int, str]] = {}
    identity: Dict[int, Tuple[str, str, str]] = {}
    if column_ids:
        placeholders = ", ".join("?" for _ in column_ids)
        cur = conn.execute(
            "SELECT o.case_id, c.suite_name, c.classname, c.name, o.run_id, o.status "
            "FROM occurrences o JOIN cases c ON c.case_id = o.case_id "
            "WHERE o.run_id IN (%s)" % placeholders,
            tuple(column_ids),
        )
        for case_id, suite_name, classname, name, run, status in cur.fetchall():
            identity[case_id] = (suite_name, classname, name)
            statuses.setdefault(case_id, {})[run] = status

    profiles = case_profiles(conn, run_id, window)
    rows = []
    for case_id, (suite_name, classname, name) in identity.items():
        row = MatrixRow(
            case_id, suite_name, classname, name,
            tuple(statuses.get(case_id, {}).get(run) for run in column_ids),
            profiles.get(case_id),
        )
        rows.append(row)
    # 行序单点：flaky_score 降序（同分按身份字典序）。`flaky_score` 是精确 Fraction，
    # 排序可精确；取负号用于升序排序实现降序，避免 `reverse=True` 把同分组的字典序也翻过来。
    rows.sort(key=lambda row: (-row.flaky_score, row.suite_name, row.classname, row.name))
    return columns, rows



def slow_rows(conn, run_id, window=None) -> List[SlowRow]:
    """该 run 里**有耗时声明**的用例，按耗时降序（同耗时按身份字典序），各挂慢测试画像。

    ``time_ms IS NULL`` 的行不出现（"没声明耗时"不等于"耗时 0"，K28）。
    画像（p50 / p95 / 回归）由 `slow.profile_case` 判——本函数只把结果挂上去，
    **不复制口径**（判定层是 `slow.py`，依赖方向编排 → 判定）。
    窗口默认取 `view.sparkline_runs`，切分点 = 窗口中点（见模块头注）。
    """
    if window is None:
        window = rules.load_view_rules()["sparkline_runs"]
    profiles = slow_profiles(conn, run_id, window)
    cur = conn.execute(
        "SELECT o.case_id, c.suite_name, c.classname, c.name, o.time_ms "
        "FROM occurrences o JOIN cases c ON c.case_id = o.case_id "
        "WHERE o.run_id = ? AND o.time_ms IS NOT NULL "
        "ORDER BY o.time_ms DESC, c.suite_name, c.classname, c.name",
        (int(run_id),),
    )
    return [SlowRow(*row, profiles.get(row[0])) for row in cur.fetchall()]


def slow_profiles(conn, run_id, window) -> Dict[int, "slow.SlowProfile"]:
    """窗口内每条用例的慢测试画像（``{case_id: SlowProfile}``）。

    历史耗时序列取自 `window_runs`（升序，含**缺失的 run** 补 ``None`` 占位——
    "这一棒没声明耗时"与"没这一棒"在样本上等价，都不进样本）；切分点 = 窗口中点。
    判定**只调 `slow.py`**——本函数不复制任何阈值/公式。
    """
    slow_rules = rules.load_slow_rules()
    columns = window_runs(conn, run_id, window)
    column_ids = [run.run_id for run in columns]
    split = len(column_ids) // 2
    timings: Dict[int, Dict[int, Optional[int]]] = {}
    identity: Dict[int, Tuple[str, str, str]] = {}
    current: Dict[int, Optional[int]] = {}
    if column_ids:
        placeholders = ", ".join("?" for _ in column_ids)
        cur = conn.execute(
            "SELECT o.case_id, c.suite_name, c.classname, c.name, o.run_id, o.time_ms "
            "FROM occurrences o JOIN cases c ON c.case_id = o.case_id "
            "WHERE o.run_id IN (%s)" % placeholders,
            tuple(column_ids),
        )
        for case_id, suite_name, classname, name, row_run, time_ms in cur.fetchall():
            identity[case_id] = (suite_name, classname, name)
            timings.setdefault(case_id, {})[row_run] = time_ms
        # 本 run 的耗时（画像的 `time_ms` 列取本 run 的值）
        cur = conn.execute(
            "SELECT case_id, time_ms FROM occurrences WHERE run_id = ?", (int(run_id),))
        for case_id, time_ms in cur.fetchall():
            current[case_id] = time_ms

    profiles: Dict[int, "slow.SlowProfile"] = {}
    for case_id, (suite_name, classname, name) in identity.items():
        series = [timings.get(case_id, {}).get(run) for run in column_ids]
        profiles[case_id] = slow.profile_case(
            case_id, suite_name, classname, name, current.get(case_id), series,
            split, slow_rules,
        )
    return profiles


def diff_rows(conn, run_before, run_after) -> List[DiffRow]:
    """两次 run 的用例级**原始状态对**（任一侧缺行 → 该侧 ``None``）。"""
    cur = conn.execute(
        "SELECT c.case_id, c.suite_name, c.classname, c.name, b.status, a.status "
        "FROM cases c "
        "LEFT JOIN occurrences b ON b.case_id = c.case_id AND b.run_id = ? "
        "LEFT JOIN occurrences a ON a.case_id = c.case_id AND a.run_id = ? "
        "WHERE b.case_id IS NOT NULL OR a.case_id IS NOT NULL "
        "ORDER BY c.suite_name, c.classname, c.name",
        (int(run_before), int(run_after)),
    )
    return [DiffRow(*row) for row in cur.fetchall()]
