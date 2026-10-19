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
    """跨盘符输入**不得崩**（Windows 上 `os.path.relpath` 抛 ValueError）。

    这条只断言"不崩 + 正斜杠"——**平台无关**。为什么不断言"等于绝对路径"：
    Linux 上根本没有盘符概念，`os.path.relpath("Z:/elsewhere/…", "C:/repo")`
    不抛错，返回的是相对路径（首推 CI 的 ubuntu 矩阵实录：断言写死 Windows 行为
    → 两个 ubuntu 矩阵红）。真正的"回落绝对路径"逻辑由下一条用 monkeypatch
    直接钉住，跨平台都跑得到。
    """
    result = paths.relative_to_root("Z:/elsewhere/junit.xml", "C:/repo")
    assert isinstance(result, str)
    assert "\\" not in result, "必须是正斜杠形态：%r" % result


def test_relative_to_root_falls_back_when_relpath_raises(monkeypatch):
    """`os.path.relpath` 抛 ValueError（Windows 跨盘符）时，**回落绝对路径**。

    直接令 `os.path.relpath` 抛 ValueError 来复现 Windows 跨盘符，而不是靠
    "喂一个 `Z:/` 路径碰运气"——后者在 Linux 上不会触发那条分支（平台差异）。
    """
    def _boom(*_args, **_kwargs):
        raise ValueError("path is on mount 'C:', start on mount 'Z:'")

    monkeypatch.setattr(paths.os.path, "relpath", _boom)
    assert paths.relative_to_root("Z:/elsewhere/junit.xml", "C:/repo") == \
        "Z:/elsewhere/junit.xml"
