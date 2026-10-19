"""JUnit XML 流式解析（`iterparse`，内存纪律：逐元素 `clear()`）。

口径（`plan/03` 模块① + `data/README.md` §四，实现细节不另立第二套）：

- **用例身份键** = `(suite_name, classname, name)`：`suite_name` 取 `testsuite@name`；
  `classname` 取 `testcase@classname`（缺省空串）；`name` 取 `testcase@name`。
  **参数化用例保留完整参数串，不做任何截断或归一**（改名即新用例）。
- **状态**：`failure` / `error` → `fail`；`skipped` → `skip`；三者皆无 → `pass`。
  `failure_type` 取 `type`（缺省空串）、`failure_message` 取 `message`、
  `stack_first_line` 取子元素 `text` 的第一行（去首尾空白，空则空串）。
- **耗时**：`time`（十进制秒）→ 整数毫秒，`model.seconds_to_ms`（Decimal +
  ROUND_HALF_UP）；属性缺失 → ``None``（**不补 0**）。
- **run 元数据**：`branch` / `commit[_sha]` / `ci_run_id` / `timestamp` 从根或
  `<testsuite>` 属性读；读不到写空串（不猜、不编造），并计入 `degraded`。
- **坏文件不静默、不中断整批**：`bad_xml` / `bad_encoding` / `no_testsuite` /
  `unreadable` 四个原因码，逐文件记录并继续。
- **降级计数**（不是"跳过整个文件"，是"这一项按缺失处理"）：`bad_time`（耗时非法 →
  记 ``None``）、`missing_name`（`testcase` 没有 `name` → 该用例不落库，但**仍计入
  suite 的元素重数**，否则"文件里有几条"就说不清了）、`started_at_missing`、
  `bad_commit`（非 40 位十六进制 → 记空串）。

**为什么"属性缺失"要单独表达**（实测坑，`plan/HANDOFF-M2.md` §2）：pytest 的
`<testsuites>` 根**不带 totals**；gotestsum 的根**不写 `skipped`**。把"没声明"当成
0 会让对账出现假红。本模块只做元素重数（定义上就是文件里有什么），声明值由
`bench/bench_ingest.py` 的独立通道核对。
"""

from __future__ import annotations

import codecs
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import framework, model

# ── 原因码（文件级：该文件没有被 ingest）──────────────────────────────
BAD_XML = "bad_xml"
BAD_ENCODING = "bad_encoding"
NO_TESTSUITE = "no_testsuite"
UNREADABLE = "unreadable"

#: 固定的原因码顺序（摘要输出稳定，不随发现顺序漂移）
REASONS = (BAD_XML, BAD_ENCODING, NO_TESTSUITE, UNREADABLE)

# ── 降级码（文件被 ingest 了，但某一项按缺失处理）──────────────────────
DEGRADED_BAD_TIME = "bad_time"
DEGRADED_MISSING_NAME = "missing_name"
DEGRADED_STARTED_AT = "started_at_missing"
DEGRADED_BAD_COMMIT = "bad_commit"

DEGRADED_REASONS = (
    DEGRADED_BAD_TIME,
    DEGRADED_MISSING_NAME,
    DEGRADED_STARTED_AT,
    DEGRADED_BAD_COMMIT,
)

#: 计数字段（与 `bench/bench_ingest.COUNT_FIELDS` 同口径：元素重数）
COUNT_FIELDS = ("tests", "failures", "errors", "skipped")

#: run 元数据属性名（根 / testsuite 上都认；按序取第一个非空）
BRANCH_ATTRS = ("branch",)
COMMIT_ATTRS = ("commit", "commit_sha")
RUN_ID_ATTRS = ("ci_run_id", "ci_run-id", "run_id")
STARTED_ATTRS = ("timestamp",)

STATUS_BY_TAG = {"failure": model.STATUS_FAIL, "error": model.STATUS_FAIL,
                 "skipped": model.STATUS_SKIP}

_HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_ENCODING_RE = re.compile(rb"""<\?xml[^>]*encoding=["']([A-Za-z0-9._\-]+)["']""")

#: 无 XML 声明时的兜底编码（XML 规范默认 UTF-8）
DEFAULT_ENCODING = "utf-8"


@dataclass
class ParsedCase:
    """一条 `testcase`（已归一到四态 + 毫秒）。"""

    suite_name: str
    classname: str
    name: str
    status: str
    time_ms: Optional[int]
    failure_type: str = ""
    failure_message: str = ""
    stack_first_line: str = ""


@dataclass
class ParsedSuite:
    """一个 `<testsuite>`：元素重数 + 其下的用例。"""

    name: str
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    time_ms: Optional[int] = None
    cases: List[ParsedCase] = field(default_factory=list)

    def counts(self):
        return {f: getattr(self, f) for f in COUNT_FIELDS}


@dataclass
class ParseOutcome:
    """一个文件的解析结果：``reason`` 非空 = 该文件被跳过（没有落库）。"""

    path: str
    display_path: str
    framework: str = framework.FRAMEWORK_UNKNOWN
    reason: str = ""
    branch: str = ""
    commit_sha: str = ""
    ci_run_id: str = ""
    started_at: str = ""
    suites: List[ParsedSuite] = field(default_factory=list)
    degraded: Dict[str, int] = field(default_factory=dict)

    @property
    def ok(self):
        return not self.reason

    @property
    def totals(self):
        totals = dict.fromkeys(COUNT_FIELDS, 0)
        for suite in self.suites:
            for name in COUNT_FIELDS:
                totals[name] += getattr(suite, name)
        return totals

    @property
    def cases(self):
        for suite in self.suites:
            for case in suite.cases:
                yield case

    def count_degraded(self, reason, how_many=1):
        self.degraded[reason] = self.degraded.get(reason, 0) + how_many


# ── 内部：元数据 / 用例 ───────────────────────────────────────────────


def _localname(tag):
    """去掉 `{ns}` 前缀（少数工具会带命名空间）。"""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _first_attr(elem, names):
    for name in names:
        raw = elem.get(name)
        if raw:
            return str(raw).strip()
    return ""


def _absorb_metadata(outcome, elem):
    """从根 / `<testsuite>` 上吸取 run 元数据（先到先得，不覆盖已有值）。"""
    if not outcome.branch:
        outcome.branch = _first_attr(elem, BRANCH_ATTRS)
    if not outcome.commit_sha:
        outcome.commit_sha = _first_attr(elem, COMMIT_ATTRS)
    if not outcome.ci_run_id:
        outcome.ci_run_id = _first_attr(elem, RUN_ID_ATTRS)
    if not outcome.started_at:
        outcome.started_at = _first_attr(elem, STARTED_ATTRS)


def _classify_parse_error(path):
    """区分"坏编码"与"坏 XML"：只有解析失败的那条路径才做这个额外扫描。

    做法：按 XML 声明里的编码（缺省 UTF-8）**增量解码**整个文件；解码失败说明
    问题在字节层（`bad_encoding`），否则是结构层（`bad_xml`）。成本只落在失败路径。
    """
    encoding = DEFAULT_ENCODING
    try:
        with open(path, "rb") as fh:
            match = _ENCODING_RE.search(fh.read(256))
            if match:
                encoding = match.group(1).decode("ascii", "replace")
        # 解码必须从头扫一遍：先读的那 256 字节只是用来拿编码声明，判不出完整性
        with open(path, "rb") as fh:
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                decoder.decode(chunk)
            decoder.decode(b"", True)
    except LookupError:
        # 声明了一个 Python 不认识的编码名——问题仍出在"字节怎么读"，不是结构
        return BAD_ENCODING
    except UnicodeDecodeError:
        return BAD_ENCODING
    except OSError:
        return UNREADABLE
    return None


def _stack_first_line(child):
    text = child.text or ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _case_kind(child_iter):
    """一个 testcase 的子元素 → `(kind, status, failure_type, message, stack)`。

    ``kind`` 是**元素标签**（`failure` / `error` / `skipped` / ``""``）——元素重数按
    标签分桶（`failures` 与 `errors` 是两个桶），而四态把它们合并成 `fail`。
    这两件事必须分开算：`errors` 若并进 `failures`，与框架声明值就对不上了。
    """
    for child in child_iter:
        tag = _localname(child.tag)
        if tag not in STATUS_BY_TAG:
            continue
        return (
            tag,
            STATUS_BY_TAG[tag],
            (child.get("type") or "").strip(),
            child.get("message") or "",
            _stack_first_line(child),
        )
    return "", model.STATUS_PASS, "", "", ""


def _absorb_case(elem, outcome, suite_name):
    """把一条 `testcase` 元素转成 `(ParsedCase, kind)`；缺 name 时返回 ``(None, kind)``。"""
    kind, status, failure_type, failure_message, stack = _case_kind(iter(elem))
    name = elem.get("name")
    if not name:
        # 身份键要求 name 非空（`identity.CaseIdentity`）；缺 name 的用例不落库，
        # 但**仍计入元素重数**——否则"文件里到底有几条"就说不清了。
        outcome.count_degraded(DEGRADED_MISSING_NAME)
        return None, kind
    raw_time = elem.get("time")
    time_ms = None
    if raw_time not in (None, ""):
        try:
            time_ms = model.seconds_to_ms(raw_time)
        except ValueError:
            outcome.count_degraded(DEGRADED_BAD_TIME)
            time_ms = None
    return ParsedCase(
        suite_name=suite_name,
        classname=(elem.get("classname") or "").strip(),
        name=name,
        status=status,
        time_ms=time_ms,
        failure_type=failure_type,
        failure_message=failure_message,
        stack_first_line=stack,
    ), kind


def _new_suite(elem, outcome):
    suite = ParsedSuite(name=(elem.get("name") or "").strip())
    raw_time = elem.get("time")
    if raw_time not in (None, ""):
        try:
            suite.time_ms = model.seconds_to_ms(raw_time)
        except ValueError:
            outcome.count_degraded(DEGRADED_BAD_TIME)
            suite.time_ms = None
    return suite


# ── 主入口 ────────────────────────────────────────────────────────────


def parse_file(path, display_path=None):
    """流式解析一个 JUnit XML 文件，返回 `ParseOutcome`（永不抛解析异常）。

    内存纪律：`testcase` 与 `testsuite` 的 `end` 事件处都 `clear()`，5 万用例
    （乃至 50MB 级）文件不会把整树留在内存里。
    """
    outcome = ParseOutcome(path=str(path),
                           display_path=str(display_path or path))
    try:
        stream = open(path, "rb")
    except OSError:
        outcome.reason = UNREADABLE
        return outcome

    root_tag = ""
    names = []
    properties = []
    current = None          # 当前正在累积的 testsuite
    in_case = False
    try:
        with stream:
            for event, elem in ET.iterparse(stream, events=("start", "end")):
                tag = _localname(elem.tag)
                if event == "start":
                    if not root_tag:
                        root_tag = tag
                    if tag == "testsuite":
                        current = _new_suite(elem, outcome)
                        names.append(current.name)
                        _absorb_metadata(outcome, elem)
                    elif tag == "testsuites":
                        names.append((elem.get("name") or "").strip())
                        _absorb_metadata(outcome, elem)
                    elif tag == "testcase":
                        in_case = True
                    elif tag == "property" and current is not None and not in_case:
                        properties.append(elem.get("name") or "")
                    continue
                # ── end 事件 ──
                if tag == "testcase":
                    in_case = False
                    if current is not None:
                        case, kind = _absorb_case(elem, outcome, current.name)
                        current.tests += 1
                        if kind == "failure":
                            current.failures += 1
                        elif kind == "error":
                            current.errors += 1
                        elif kind == "skipped":
                            current.skipped += 1
                        if case is not None:
                            current.cases.append(case)
                    elem.clear()
                elif tag == "testsuite":
                    if current is not None:
                        outcome.suites.append(current)
                    current = None
                    elem.clear()
    except ET.ParseError:
        # 分类顺序：① 字节层读不动（坏编码 / 不可读）先判，它比"缺根"更具体；
        # ② 一个合法根元素都没起来 = 缺根（空文件 / 非 XML 文本）；
        # ③ 起过根但中途炸 = 坏结构。
        # 三者必居其一——绝不静默（"解析失败"必须留下原因码）。
        classified = _classify_parse_error(path)
        if classified in (BAD_ENCODING, UNREADABLE):
            outcome.reason = classified
        elif not root_tag:
            outcome.reason = NO_TESTSUITE
        else:
            outcome.reason = BAD_XML
        outcome.suites = []
        return outcome
    except OSError:
        outcome.reason = UNREADABLE
        outcome.suites = []
        return outcome

    if root_tag not in ("testsuites", "testsuite") or not outcome.suites:
        # 根不是 JUnit 家族（缺根 / 空文件 / 根不是 testsuite[s] / testsuites 下无 suite）
        outcome.reason = NO_TESTSUITE
        outcome.suites = []
        return outcome

    outcome.framework = framework.detect(
        file_name=os.path.basename(str(path)),
        names=names,
        properties=properties,
    )
    if outcome.commit_sha and not _HEX40_RE.match(outcome.commit_sha):
        outcome.count_degraded(DEGRADED_BAD_COMMIT)
        outcome.commit_sha = ""
    if not outcome.started_at:
        outcome.count_degraded(DEGRADED_STARTED_AT)
    return outcome
