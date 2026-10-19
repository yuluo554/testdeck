"""生产解析器（`testdeck.junit`）：三框架身份键、四态、耗时、坏文件、降级计数。

判据一律来自**真跑产物**（`bench/fixtures/`）与临时构造的边界样本；两者互为对照。
"""

import os

import pytest

from testdeck import junit, model


def write(path, text, encoding="utf-8"):
    path.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
    return str(path)


# ── 真跑产物：身份键与四态 ─────────────────────────────────────────────


def test_pytest_fixture_identity_and_fields(repo_root):
    path = os.path.join(repo_root, "bench", "fixtures", "pytest", "junit.xml")
    outcome = junit.parse_file(path, path)
    assert outcome.ok
    assert outcome.totals == {"tests": 6, "failures": 1, "errors": 0, "skipped": 1}
    suite = outcome.suites[0]
    assert suite.name == "pytest"          # `testsuite@name`
    assert suite.time_ms == 105            # 0.105s -> 105ms
    cases = list(outcome.cases)
    assert [c.name for c in cases][:2] == ["test_add_returns_sum", "test_add_is_commutative"]
    assert {c.classname for c in cases} == {"bench.fixtures.pytest.test_demo"}
    failure = [c for c in cases if c.status == model.STATUS_FAIL][0]
    assert failure.failure_message.startswith("AssertionError: deliberate failure fixture")
    assert failure.stack_first_line == "def test_deliberate_failure_fixture():"
    skipped = [c for c in cases if c.status == model.STATUS_SKIP][0]
    assert skipped.failure_type == "pytest.skip"
    assert skipped.failure_message == "not implemented yet: subtract()"
    assert skipped.time_ms == 0


def test_gotestsum_fixture_identity_and_fields(repo_root):
    path = os.path.join(repo_root, "bench", "fixtures", "gotestsum", "gotestsum.xml")
    outcome = junit.parse_file(path, path)
    assert outcome.ok
    assert outcome.totals == {"tests": 5, "failures": 1, "errors": 0, "skipped": 1}
    suite = outcome.suites[0]
    assert suite.name == "demo-lib"        # 包名，不是框架名
    assert suite.time_ms == 190
    by_name = {c.name: c for c in outcome.cases}
    assert by_name["TestAdd"].status == model.STATUS_PASS
    failure = by_name["TestDeliberateFailureFixture"]
    assert failure.classname == "demo-lib"
    assert failure.failure_type == ""      # gotestsum 写 `type=""`
    assert failure.failure_message == "Failed"
    assert failure.stack_first_line == "=== RUN   TestDeliberateFailureFixture"


def test_playwright_fixture_identity_and_fields(repo_root):
    path = os.path.join(repo_root, "bench", "fixtures", "playwright", "playwright.xml")
    outcome = junit.parse_file(path, path)
    assert outcome.ok
    assert outcome.totals == {"tests": 7, "failures": 1, "errors": 0, "skipped": 1}
    suite = outcome.suites[0]
    assert suite.name == "todo.spec.js"    # 实测：suite name 是**测试文件名**
    assert suite.time_ms == 6616
    by_name = {c.name: c for c in outcome.cases}
    failure = by_name["deliberate failure fixture: counter text"]
    assert failure.failure_type == "FAILURE"
    assert failure.stack_first_line.startswith("todo.spec.js:77:1")
    skipped = by_name["not implemented yet: persisted storage"]
    assert skipped.status == model.STATUS_SKIP
    assert (skipped.failure_type, skipped.failure_message, skipped.stack_first_line) == ("", "", "")


def test_three_frameworks_share_one_identity_key_shape(repo_root):
    """三框架的身份键形态一致：`(suite_name, classname, name)` 都非空、都不做归一。"""
    for framework, name in (("pytest", "junit.xml"), ("gotestsum", "gotestsum.xml"),
                            ("playwright", "playwright.xml")):
        path = os.path.join(repo_root, "bench", "fixtures", framework, name)
        outcome = junit.parse_file(path, path)
        keys = [(c.suite_name, c.classname, c.name) for c in outcome.cases]
        assert len(keys) == len(set(keys)), "%s 内部出现重复身份键" % framework
        assert all(all(part for part in (key[0], key[2])) for key in keys), framework
        assert all(key[0] == outcome.suites[0].name for key in keys), framework


# ── 结构兼容性 ────────────────────────────────────────────────────────


def test_bare_testsuite_root(tmp_path):
    """裸 `<testsuite>` 根也要能解析（不是所有工具都包 `<testsuites>`）。"""
    path = write(tmp_path / "solo.xml",
                 '<?xml version="1.0"?><testsuite name="solo" tests="2">'
                 '<testcase classname="a" name="t1"/>'
                 '<testcase classname="a" name="t2"><failure/></testcase>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    assert outcome.ok
    assert outcome.totals == {"tests": 2, "failures": 1, "errors": 0, "skipped": 0}
    assert outcome.suites[0].name == "solo"


def test_root_without_totals_is_not_read_as_zero(tmp_path):
    """pytest 的 `<testsuites>` 根不带 totals——元素重数照样数得出来（K24）。"""
    path = write(tmp_path / "junit-x.xml",
                 '<?xml version="1.0"?><testsuites name="pytest tests">'
                 '<testsuite name="pytest" tests="1"><testcase name="t"/></testsuite>'
                 "</testsuites>")
    outcome = junit.parse_file(path)
    assert outcome.totals["tests"] == 1


def test_error_element_maps_to_fail_but_counts_in_errors_bucket(tmp_path):
    """`error` 与 `failure` 都归 `fail` 态，但**元素重数分桶**（否则与声明值对不上）。"""
    path = write(tmp_path / "e.xml",
                 '<?xml version="1.0"?><testsuite name="s">'
                 '<testcase name="a"><failure message="x"/></testcase>'
                 '<testcase name="b"><error message="boom" type="RuntimeError"/></testcase>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    assert outcome.totals == {"tests": 2, "failures": 1, "errors": 1, "skipped": 0}
    statuses = {c.name: c.status for c in outcome.cases}
    assert statuses == {"a": model.STATUS_FAIL, "b": model.STATUS_FAIL}
    errored = [c for c in outcome.cases if c.name == "b"][0]
    assert (errored.failure_type, errored.failure_message) == ("RuntimeError", "boom")


def test_namespaced_tags_are_handled(tmp_path):
    path = write(tmp_path / "ns.xml",
                 '<?xml version="1.0"?><testsuites xmlns="urn:x">'
                 '<testsuite name="s"><testcase name="t"><failure message="m"/></testcase>'
                 "</testsuite></testsuites>")
    outcome = junit.parse_file(path)
    assert outcome.totals == {"tests": 1, "failures": 1, "errors": 0, "skipped": 0}


def test_parameterized_case_name_is_preserved_verbatim(tmp_path):
    """参数化用例保留完整参数串，不做截断/归一（改名即新用例）。"""
    path = write(tmp_path / "p.xml",
                 '<?xml version="1.0"?><testsuite name="s">'
                 '<testcase classname="c" name="test_x[1-2-&lt;evil&gt;]" time="1.0"/>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    (case,) = list(outcome.cases)
    assert case.name == "test_x[1-2-<evil>]"
    assert case.time_ms == 1000


# ── run 元数据 ────────────────────────────────────────────────────────


def test_run_metadata_comes_from_xml_only(tmp_path):
    path = write(tmp_path / "m.xml",
                 '<?xml version="1.0"?><testsuites branch="main" commit_sha="%s" '
                 'ci_run_id="123456" timestamp="2026-01-02T03:04:05+00:00">'
                 '<testsuite name="s"><testcase name="t"/></testsuite></testsuites>'
                 % ("a" * 40))
    outcome = junit.parse_file(path)
    assert (outcome.branch, outcome.commit_sha, outcome.ci_run_id) == ("main", "a" * 40, "123456")
    assert outcome.started_at == "2026-01-02T03:04:05+00:00"
    assert outcome.degraded == {}


def test_missing_metadata_is_empty_string_not_invented(tmp_path):
    """没有声明身份 -> 空串 + `started_at_missing` 降级；**不拿路径凑一个身份**。"""
    path = write(tmp_path / "junit-raw.xml",
                 '<?xml version="1.0"?><testsuite name="s"><testcase name="t"/></testsuite>')
    outcome = junit.parse_file(path)
    assert (outcome.branch, outcome.commit_sha, outcome.ci_run_id, outcome.started_at) == ("", "", "", "")
    assert outcome.degraded == {junit.DEGRADED_STARTED_AT: 1}


def test_non_hex_commit_is_degraded_not_crashing(tmp_path):
    path = write(tmp_path / "c.xml",
                 '<?xml version="1.0"?><testsuite name="s" commit="not-a-sha" timestamp="t">'
                 '<testcase name="t"/></testsuite>')
    outcome = junit.parse_file(path)
    assert outcome.ok and outcome.commit_sha == ""
    assert outcome.degraded.get(junit.DEGRADED_BAD_COMMIT) == 1


# ── 坏文件：四个原因码，不静默、不中断 ────────────────────────────────


def test_bad_xml_reason(tmp_path):
    path = write(tmp_path / "broken.xml",
                 '<?xml version="1.0"?><testsuites><testsuite name="s"><testcase name="t"')
    outcome = junit.parse_file(path)
    assert outcome.reason == junit.BAD_XML
    assert outcome.suites == [] and not outcome.ok


def test_bad_encoding_reason(tmp_path):
    """声明 utf-8 却塞入非法字节 -> `bad_encoding`（与 `bad_xml` 分开）。"""
    payload = b'<?xml version="1.0" encoding="utf-8"?><testsuite name="s">' + b"\xff\xfe" + b"</testsuite>"
    path = write(tmp_path / "enc.xml", payload)
    outcome = junit.parse_file(path)
    assert outcome.reason == junit.BAD_ENCODING


def test_no_testsuite_reason_for_foreign_root(tmp_path):
    path = write(tmp_path / "foreign.xml", '<?xml version="1.0"?><report><case/></report>')
    assert junit.parse_file(path).reason == junit.NO_TESTSUITE


def test_no_testsuite_reason_for_empty_testsuites(tmp_path):
    path = write(tmp_path / "empty.xml", '<?xml version="1.0"?><testsuites></testsuites>')
    assert junit.parse_file(path).reason == junit.NO_TESTSUITE


def test_no_testsuite_reason_for_empty_file(tmp_path):
    path = write(tmp_path / "void.xml", "")
    assert junit.parse_file(path).reason == junit.NO_TESTSUITE


def test_unreadable_reason_for_missing_file(tmp_path):
    outcome = junit.parse_file(str(tmp_path / "nope.xml"))
    assert outcome.reason == junit.UNREADABLE
    assert not outcome.ok


def test_reasons_are_a_fixed_tuple():
    """原因码集合是单点定义（摘要输出按它排序），不给"临时新造一个码"留口子。"""
    assert junit.REASONS == ("bad_xml", "bad_encoding", "no_testsuite", "unreadable")
    assert junit.DEGRADED_REASONS == (
        "bad_time", "missing_name", "started_at_missing", "bad_commit")


# ── 降级：单点缺失不等于整文件报废 ────────────────────────────────────


def test_bad_time_is_degraded_to_none_not_zero(tmp_path):
    path = write(tmp_path / "t.xml",
                 '<?xml version="1.0"?><testsuite name="s" time="oops">'
                 '<testcase name="a" time="oops"/>'
                 '<testcase name="b"/>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    assert outcome.degraded.get(junit.DEGRADED_BAD_TIME) == 2  # suite 与 case 各一处
    cases = {c.name: c.time_ms for c in outcome.cases}
    assert cases == {"a": None, "b": None}
    assert outcome.suites[0].time_ms is None


def test_seconds_to_ms_round_half_up(tmp_path):
    """0.0005s -> 1ms（ROUND_HALF_UP）；0.0004s -> 0ms。"""
    path = write(tmp_path / "r.xml",
                 '<?xml version="1.0"?><testsuite name="s">'
                 '<testcase name="a" time="0.0005"/><testcase name="b" time="0.0004"/>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    assert {c.name: c.time_ms for c in outcome.cases} == {"a": 1, "b": 0}
    assert model.seconds_to_ms("") is None and model.seconds_to_ms(None) is None


def test_nameless_case_is_degraded_but_still_counted(tmp_path):
    """缺 `name` 的用例不落库（身份键要求非空），但**仍计入元素重数**并记一笔降级。"""
    path = write(tmp_path / "n.xml",
                 '<?xml version="1.0"?><testsuite name="s">'
                 '<testcase classname="c"/>'
                 '<testcase classname="c" name="ok"/>'
                 "</testsuite>")
    outcome = junit.parse_file(path)
    assert outcome.totals["tests"] == 2
    assert len(list(outcome.cases)) == 1
    assert outcome.degraded.get(junit.DEGRADED_MISSING_NAME) == 1


def test_stack_first_line_skips_leading_blank_lines(tmp_path):
    path = write(tmp_path / "st.xml",
                 '<?xml version="1.0"?><testsuite name="s"><testcase name="t">'
                 "<failure>\n\n   first real line   \nsecond\n</failure>"
                 "</testcase></testsuite>")
    (case,) = list(junit.parse_file(path).cases)
    assert case.stack_first_line == "first real line"


def test_stack_first_line_is_empty_string_when_text_absent(tmp_path):
    path = write(tmp_path / "st2.xml",
                 '<?xml version="1.0"?><testsuite name="s">'
                 '<testcase name="t"><skipped/></testcase></testsuite>')
    (case,) = list(junit.parse_file(path).cases)
    assert (case.status, case.stack_first_line) == (model.STATUS_SKIP, "")


@pytest.mark.parametrize("bad", ["bad_xml", "bad_encoding", "no_testsuite", "unreadable"])
def test_bad_files_never_raise(tmp_path, bad):
    """解析器契约：坏文件只返回原因码，绝不抛异常（一批里有一个坏的不能带崩整批）。"""
    payloads = {
        "bad_xml": b'<?xml version="1.0"?><testsuites><testsuite><testcase ',
        "bad_encoding": b'<?xml version="1.0" encoding="utf-8"?>\xff\xfe<testsuite/>',
        "no_testsuite": b'<?xml version="1.0"?><nothing/>',
        "unreadable": None,
    }
    if payloads[bad] is None:
        path = str(tmp_path / "gone.xml")
    else:
        path = write(tmp_path / ("x_" + bad + ".xml"), payloads[bad])
    outcome = junit.parse_file(path)
    assert outcome.reason == bad
