"""框架识别：三份真实产物必须认出，认不出必须写 `unknown`（不猜）。"""

import os

import pytest

from testdeck import framework, junit

REAL = (
    ("pytest", "junit.xml"),
    ("gotestsum", "gotestsum.xml"),
    ("playwright", "playwright.xml"),
)


@pytest.mark.parametrize("expected,file_name", REAL)
def test_real_fixtures_are_recognised(repo_root, expected, file_name):
    """真实产物识别的端到端证据：解析结果里的 framework 字段。"""
    path = os.path.join(repo_root, "bench", "fixtures", expected, file_name)
    outcome = junit.parse_file(path, path)
    assert outcome.ok, outcome.reason
    assert outcome.framework == expected


def test_unknown_when_no_hint():
    """没有任何线索 -> unknown（宁可第三态也不猜）。"""
    assert framework.detect(file_name="report.xml") == framework.FRAMEWORK_UNKNOWN
    assert framework.detect(file_name="report.xml", names=["demo-lib"]) == "unknown"


def test_name_hint_wins_over_filename():
    """`testsuite@name` 是最高优先级线索（pytest 会把 suite 命名成 "pytest"）。"""
    got = framework.detect(file_name="playwright.xml", names=["pytest tests"])
    assert got == "pytest"


def test_playwright_and_gotestsum_need_filename_when_suite_name_is_not_a_hint():
    """实测边界：Playwright 的 suite name 是**测试文件名**，gotestsum 的是包名。"""
    assert framework.detect(file_name="playwright.xml", names=["todo.spec.js"]) == "playwright"
    assert framework.detect(file_name="gotestsum.xml", names=["demo-lib"]) == "gotestsum"


def test_property_hint_recognises_gotestsum_without_filename_hint():
    """gotestsum 会写 `<property name="go.version">`——文件名不含线索时靠它。"""
    got = framework.detect(file_name="report.xml", properties=["go.version"])
    assert got == "gotestsum"


def test_junit_filename_falls_back_to_pytest():
    """`junit.xml` 是 pytest 的默认产物名（内容无线索时的兜底，仍可能误判）。"""
    assert framework.detect(file_name="path/to/junit.xml") == "pytest"
    assert framework.detect(file_name="path/to/junit-3.xml") == "pytest"


def test_bare_unknown_name_does_not_crash():
    assert framework.detect(file_name="", names=(None, ""), properties=(None, "")) == "unknown"
