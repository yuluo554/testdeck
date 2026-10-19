#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""布局门自身的变异验证（8 组）：故意弄坏被测对象，门必须变红；还原后必须全绿。

用法：
    py -3.12 tools/verify-layout-gate.py

退出码：0 = 全部组按预期变红且还原后全绿；1 = 有组没红（门是假门）或还原失败。

三条防"静默 no-op"的纪律（实测踩过）：
  ① 替换前 assert marker 存在；
  ② 替换后 assert 文件字节已变；
  ③ 还原后 assert 字节与原文一致，且不留 .bak。
全流程包在 try/finally 里，任何异常都还原。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "tools", "check-sprint-layout.py")


def run_gate():
    proc = subprocess.run(
        [sys.executable, GATE],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def mutate_file(rel, old, new):
    path = os.path.join(ROOT, rel)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        original = fh.read()
    assert old in original, "marker 不存在（变异没发生）：%s :: %r" % (rel, old[:40])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(original.replace(old, new, 1))
    return path, original


def restore(path, original):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        current = fh.read()
    assert current != original, "变异没发生（写入后字节未变）：%s" % path
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(original)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        assert fh.read() == original, "还原失败：%s" % path


def move_away(rel):
    path = os.path.join(ROOT, rel)
    assert os.path.isfile(path), "待删对象不存在：%s" % rel
    tmp = path + ".mutbak"
    os.replace(path, tmp)
    return path, tmp


def move_back(path, tmp):
    os.replace(tmp, path)
    assert os.path.isfile(path), "还原失败：%s" % path
    assert not os.path.exists(tmp), "残留 .mutbak：%s" % tmp


CASES = []


def case(name, expect_id):
    def deco(fn):
        CASES.append((name, expect_id, fn))
        return fn

    return deco


@case("M1 删 AGENTS.md", "LAYOUT.FILES")
def _m1():
    return ("delete", "AGENTS.md")


@case("M2 一个副本里把 M0 翻成 ⬜", "LAYOUT.STATUS")
def _m2():
    return (
        "edit",
        "plan/05-里程碑与发布.md",
        "| M0 | 方法论装订 + plan/00–06 + 可运行骨架（CLI 参数面 / 键位单点 / 退出码 / 规则包 / selftest） |",
        "| M0 | ⬜ 方法论装订 + plan/00–06 + 可运行骨架（CLI 参数面 / 键位单点 / 退出码 / 规则包 / selftest） |",
    )


@case("M3 把已 ✅ 的 M2 写回 plan/06 缺口格", "LAYOUT.GAPS")
def _m3():
    # 注：marker 必须跟着**当前**缺口表首行走（每次收窄/关闭缺口后都要重排）。
    # 门是"已 ✅ 的里程碑不得再出现在缺口格里"——所以伪造的缺口格里写 M2。
    return (
        "edit",
        "plan/06-交付对标与决策.md",
        "| G1 | **已关闭**：慢测试的分位数与回归判定已接到",
        "| G1 | M2 三栏视图尚未验证（伪造缺口） |",
    )


@case("M4 删 plan/02（计划套件缺一份）", "LAYOUT.FILES")
def _m4():
    return ("delete", "plan/02-架构与技术选型.md")


@case("M5 删 plan/00 顶部装订行（整行移除）", "LAYOUT.BINDING_HEAD")
def _m5():
    return (
        "delete_line",
        "plan/00-README总览.md",
        "> 方法论：`ai-tool-project-sprint`（装订 2026-10-18）｜布局门：`py -3.12 tools/check-sprint-layout.py`｜续接对话第一件事 = 跑它",
    )


@case("M6 删 plan/06 的『缺口』表头（判据表搬走）", "LAYOUT.GAPS")
def _m6():
    return (
        "delete_line",
        "plan/06-交付对标与决策.md",
        "| 编号 | 缺口 | 关闭条件 | 归属 |",
    )


@case("M7 删下一棒交接单 HANDOFF-M1", "LAYOUT.HANDOFFS")
def _m7():
    return ("delete", "plan/HANDOFF-M1.md")


@case("M8 发布留档的『tag 后』栏标题去标记（两栏变一栏）", "LAYOUT.RELEASE")
def _m8():
    # LAYOUT.RELEASE 在 M6 完成后才生效（发布门）。它要求留档同时有
    # "§一 …tag 前" 与 "§二 …tag 后" 两栏小节——把后一栏标题里的 "tag 后" 去掉，
    # 两栏判据应立刻变红（这是发布门自身可证伪的证据）。
    return (
        "edit",
        "plan/RELEASE-M6.md",
        "## 二、tag 之后追加事实（tag 后回填）",
        "## 二、后续追加事实（回填）",
    )


def apply_variant(kind, *args):
    if kind == "delete":
        return ("move",) + move_away(args[0])
    if kind == "edit":
        rel, old, new = args
        path, original = mutate_file(rel, old, new)
        with open(path, "r", encoding="utf-8") as fh:
            assert fh.read() != original, "变异没发生"
        return ("restore", path, original)
    if kind == "delete_line":
        rel, line = args
        path = os.path.join(ROOT, rel)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        assert line in original, "整行不存在：%r" % line[:40]
        mutated = "\n".join(ln for ln in original.split("\n") if ln != line)
        assert mutated != original, "删行后字节未变"
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(mutated)
        return ("restore", path, original)
    raise AssertionError("unknown variant kind: %s" % kind)


def undo(handle):
    if handle[0] == "move":
        move_back(handle[1], handle[2])
    else:
        restore(handle[1], handle[2])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    code, output = run_gate()
    if code != 0:
        print("基线不是全绿，先修门/修布局：\n" + output)
        return 1
    print("基线：全绿")

    failures = []
    for name, expect_id, factory in CASES:
        handle = None
        try:
            handle = apply_variant(*factory())
            code, output = run_gate()
            hit = any(
                line.startswith("FAIL") and expect_id in line for line in output.splitlines()
            )
            ok = code == 1 and hit
            print("%s  %-42s -> rc=%d %s" % ("PASS" if ok else "FAIL", name, code, expect_id))
            if not ok:
                failures.append(name)
                print("      门输出:\n" + "\n".join("      " + l for l in output.splitlines()))
        finally:
            if handle is not None:
                undo(handle)
            code2, output2 = run_gate()
            if code2 != 0:
                failures.append(name + "（还原后未复绿）")
                print("      还原后仍未绿:\n" + output2)

    print("=" * 60)
    print(
        "结论：%s"
        % (
            "%d 组变异全部按预期变红，还原后全绿" % len(CASES)
            if not failures
            else "FAIL %s" % failures
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
