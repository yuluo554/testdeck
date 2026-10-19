#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fixture 脱敏扫描（M1）：入库产物里不得出现本机绝对路径、机器名或真实域名。

判据落**文件内容**，不读 git。用法：``py -3.12 bench/fixtures/scan_leaks.py``
退出码：0 干净 / 1 发现泄漏。
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"node_modules", "test-results", "__pycache__"}
#: 产物与源码：整套模式都查
ARTIFACT_SUFFIXES = {".xml", ".json", ".js", ".go", ".mod", ".py"}
#: 文档：只查**具体的**机器标识
DOC_SUFFIXES = {".md"}

#: 扫描器自身与产出器：它们的源码里**必然**出现这些模式的样子（`hostname=`、
#: `[A-Za-z]:[\\/]`），那是代码不是泄漏。排除它们，否则扫描器永远自报红。
SKIP_FILES = {"scan_leaks.py", "regen_fixtures.py"}

#: 泄漏模式。`windows-abs-path` 用 `(?<![A-Za-z])` 前瞻排除 URI 里的
#: `https://`（其中 `s:` 后面跟 `//`，会被朴素的 `[A-Za-z]:[\\/]` 误判）。
PATTERNS = (
    ("windows-abs-path", r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    ("posix-abs-path", r"/(?:home|Users)/"),
    ("hostname-attr", r"hostname\s*="),
    ("machine-name", r"LAPTOP-[A-Z0-9]+"),
    ("real-domain", r"https?://(?!news\.ycombinator\.com|github\.com|go\.dev|"
                    r"registry\.npmmirror\.com|goproxy\.cn)[a-z0-9.-]+\.[a-z]{2,}"),
)

#: `README.md` 要**说明**"我们删掉了 `hostname` 属性""绝对路径被改写成相对路径"
#: 这类规则，于是必然写出 `hostname="…"` 这样的**抽象**样例。文档只查"具体的机器
#: 标识"（真机器名 / 真盘符路径），不查抽象模式描述——否则守门会去罚它自己的说明书。
MACHINE_IDENTIFIER_LABELS = {"windows-abs-path", "posix-abs-path", "machine-name"}


def _patterns_for(suffix):
    if suffix in DOC_SUFFIXES:
        return [p for p in PATTERNS if p[0] in MACHINE_IDENTIFIER_LABELS]
    return list(PATTERNS)


def scan(root):
    """扫描 ``root`` 下的入库文件，返回 ``(problems, scanned_count)``。"""
    problems = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in ARTIFACT_SUFFIXES and suffix not in DOC_SUFFIXES:
                continue
            if name in SKIP_FILES:
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, os.path.dirname(root))
            scanned += 1
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for label, pattern in _patterns_for(suffix):
                for match in re.finditer(pattern, text):
                    snippet = text[max(0, match.start() - 20):match.end() + 20]
                    problems.append("%s: [%s] …%s…" % (rel, label, snippet.strip()))
    return problems, scanned


def main():
    problems, scanned = scan(HERE)
    for item in problems:
        print("FAIL  " + item)
    print("扫描 %d 个文件；结论：%s" % (scanned, "干净" if not problems else "%d 处泄漏" % len(problems)))
    if scanned == 0:
        print("FAIL  扫描面为空（判据失效）")
        return 1
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
