"""README 版本指针守门（SI-048）。

背景（2026-10-25 实测）：`v0.1.1` 的 tag 树里 README `:24-25` 仍写
「`v0.1.0` 已打 annotated tag 并发布 GitHub Release（附手工源码包
`testdeck-0.1.0.tar.gz`）」—— 版本号与产物名都是上一版，而本仓确实发过 v0.1.1
（附件 `testdeck-0.1.1.tar.gz`，803,049 B）。README 全文没有出现过 `0.1.1`。

判据（定位到**声明性那一行**，不做全文存在性判断 —— presence ≠ correctness）：

  ① README「发布态」段落里出现的 tag 名 `vX.Y.Z` == 当前版本；
  ② README 里出现的源码包文件名 `testdeck-X.Y.Z.tar.gz` == 当前版本。

⚠ 刻意**不**断言「README 必须出现当前版本号」：本仓 README 的自我定位是
「只写『版本 + 能力』，随包读者请以 Release 页为准判断发布状态」。
所以本门只查**它自己选择要写的那些指针**是否写对，不强迫它新增声明
（给不记版本的 README 硬加指针属反向破坏，见 SI-048 证据列）。

③ 是**门本身的负控**：喂合成的旧版本文本，两条必须报错。
"""

from __future__ import annotations

import re
from pathlib import Path

from testdeck import __version__

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


#: 发布态段落：从「M6（发布态）」起，到下一个以 `**` 开头的加粗小标题或 `##` 为止。
def _release_paragraph(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        if "发布态" in line and line.lstrip().startswith("**"):
            started = True
            out.append(line)
            continue
        if started:
            if line.lstrip().startswith("## ") or (
                line.lstrip().startswith("**") and "发布态" not in line
            ):
                break
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- 审计函数

def audit_release_paragraph_tag(text: str, version: str) -> list[str]:
    """① 发布态段落里的 tag 名必须等于当前版本。"""
    para = _release_paragraph(text)
    if not para:
        return ["README 找不到「发布态」段落（'**M6（发布态）**' 开头）"]
    found = re.findall(r"`v(\d+\.\d+\.\d+)`", para)
    if not found:
        return ["发布态段落里找不到 `vX.Y.Z` tag 名 —— 该指针被删或改写了形态"]
    return [f"发布态段落的 tag = v{v}，期望 v{version}" for v in found if v != version]


def audit_sdist_asset_name(text: str, version: str) -> list[str]:
    """② README 里的源码包文件名必须等于当前版本。"""
    found = re.findall(r"testdeck-(\d+\.\d+\.\d+)\.tar\.gz", text)
    if not found:
        return ["README 找不到 testdeck-X.Y.Z.tar.gz 源码包名 —— 该指针被删"]
    return [
        f"README 源码包名 = testdeck-{v}.tar.gz，期望 testdeck-{version}.tar.gz"
        for v in found
        if v != version
    ]


# ---------------------------------------------------------------- 真文件断言

def test_readme_release_tag_matches_version():
    """① —— 发布态段落的 tag 必须等于当前版本。"""
    problems = audit_release_paragraph_tag(_readme(), __version__)
    assert problems == [], "\n".join(problems)


def test_readme_sdist_name_matches_version():
    """② —— 源码包文件名必须等于当前版本。"""
    problems = audit_sdist_asset_name(_readme(), __version__)
    assert problems == [], "\n".join(problems)


# ---------------------------------------------------------------- ③ 负控

def test_negative_control_release_tag_detects_stale():
    stale = (
        "**M6（发布态）**：`v0.9.8` 已打 annotated tag 并发布 GitHub Release"
        "（附手工源码包 `testdeck-0.9.8.tar.gz`）；\n"
    )
    assert audit_release_paragraph_tag(stale, "0.9.9") != []
    ok = stale.replace("0.9.8", "0.9.9")
    assert audit_release_paragraph_tag(ok, "0.9.9") == []


def test_negative_control_release_tag_detects_missing_paragraph():
    assert audit_release_paragraph_tag("## 状态\n无发布段落\n", "0.9.9") != []


def test_negative_control_sdist_name_detects_stale():
    stale = "附件 `testdeck-0.9.8.tar.gz`"
    assert audit_sdist_asset_name(stale, "0.9.9") != []
    assert audit_sdist_asset_name("附件 `testdeck-0.9.9.tar.gz`", "0.9.9") == []


def test_negative_control_sdist_name_detects_missing():
    assert audit_sdist_asset_name("无源码包名", "0.9.9") != []
