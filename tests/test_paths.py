"""路径口径：XDG 回落、--db 空值拒绝、跨盘符不崩。"""

import os

import pytest

from testdeck import paths


def test_xdg_data_home_wins(tmp_path):
    env = {"XDG_DATA_HOME": str(tmp_path)}
    assert paths.data_home(env) == os.path.join(str(tmp_path), "testdeck")
    assert paths.default_db_path(env) == os.path.join(
        str(tmp_path), "testdeck", "testdeck.db"
    )


def test_fallback_to_local_share_when_xdg_missing():
    env = {}
    expected = os.path.join(os.path.expanduser("~"), ".local", "share", "testdeck")
    assert paths.data_home(env) == expected


def test_blank_xdg_falls_back():
    assert paths.data_home({"XDG_DATA_HOME": "   "}) == os.path.join(
        os.path.expanduser("~"), ".local", "share", "testdeck"
    )


def test_resolve_none_returns_default(tmp_path):
    env = {"XDG_DATA_HOME": str(tmp_path)}
    assert paths.resolve_db_path(None, env) == paths.default_db_path(env)


def test_resolve_explicit_overrides():
    assert paths.resolve_db_path("C:/tmp/x.db") == "C:/tmp/x.db"


def test_resolve_empty_is_usage_error():
    with pytest.raises(ValueError):
        paths.resolve_db_path("")


def test_resolve_blank_is_usage_error():
    with pytest.raises(ValueError):
        paths.resolve_db_path("   ")


def test_normalize_path_uses_forward_slashes():
    assert paths.normalize_path("./a\\b\\c.xml") == "a/b/c.xml"


def test_relative_to_root_same_drive(tmp_path):
    root = tmp_path
    child = tmp_path / "sub" / "junit.xml"
    assert paths.relative_to_root(child, root) == "sub/junit.xml"


def test_relative_to_root_cross_drive_does_not_crash():
    """Windows 跨盘符时 os.path.relpath 抛 ValueError——必须回落绝对路径。"""
    result = paths.relative_to_root("Z:/elsewhere/junit.xml", "C:/repo")
    assert result == "Z:/elsewhere/junit.xml"
