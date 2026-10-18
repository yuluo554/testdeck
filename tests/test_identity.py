"""身份键：未知值必须写空串（NULL 会绕过唯一索引的幂等），参数串不被归一。"""

import pytest

from testdeck.identity import CaseIdentity, RunIdentity

SHA = "0" * 39 + "1"


def test_run_identity_key_is_triple():
    run = RunIdentity("main", SHA, "1000000000")
    assert run.key == ("main", SHA, "1000000000")


def test_run_identity_is_hashable_and_orderable():
    a = RunIdentity("main", SHA, "1000000000")
    b = RunIdentity("main", SHA, "1000000001")
    assert a < b
    assert len({a, b}) == 2


def test_run_identity_rejects_short_sha():
    with pytest.raises(ValueError):
        RunIdentity("main", "abc123", "1")


def test_run_identity_allows_empty_commit_as_unknown():
    assert RunIdentity("main", "", "1").commit_sha == ""


def test_run_identity_rejects_none():
    with pytest.raises(ValueError):
        RunIdentity(None, SHA, "1")


def test_case_identity_keeps_parameterized_name_verbatim():
    name = "test_add[1+2-expected3]"
    case = CaseIdentity("suite", "pkg.TestX", name)
    assert case.name == name
    assert case.key == ("suite", "pkg.TestX", name)


def test_case_identity_rejects_empty_name():
    with pytest.raises(ValueError):
        CaseIdentity("suite", "cls", "")


def test_case_identity_display_skips_empty_parts():
    assert CaseIdentity("suite", "", "test_a").display == "suite :: test_a"
