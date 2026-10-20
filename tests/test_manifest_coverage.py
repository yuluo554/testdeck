"""MANIFEST.in 覆盖面守门（0.1.1 起，DEC1=A）。

背景：v0.1.0 附件树 pytest = 471/5——tests 里有测试直接读 `.github/workflows/ci.yml`
与 `docs/demo/demo.gif`，但 MANIFEST.in 只打了 `tests *.py`，引用面文件没进 sdist
（见 plan/RELEASE-M6.md 追加①）。本测试断言两条 include 行在场，防止回退。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_covers_test_reference_files():
    """MANIFEST.in 必须覆盖测试引用面：ci.yml include 行 + docs 递归行（各恰好一条）。"""
    text = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()]
    assert any(ln.startswith("include ") and ".github/workflows/ci.yml" in ln for ln in lines), (
        "MANIFEST.in 缺 include .github/workflows/ci.yml——附件树 test_readme_gate 会红（D1 回退）"
    )
    assert any(ln.startswith("recursive-include docs ") for ln in lines), (
        "MANIFEST.in 缺 recursive-include docs ——附件树 test_demo_gif 会红（D1 回退）"
    )
