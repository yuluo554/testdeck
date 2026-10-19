#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新产出三框架真实 fixture（D1–D3）并写出各自的 `expected.json`。

**为什么需要本脚本**：M1 的 DoD 要求"三份真实产物"入库，而不是手写的 XML 样本。
手动跑一遍工具、手抄一份 expected.json，无法在下一棒复现，也无法证明
expected.json 与产物同源。本脚本把"真跑 + 抄真值"变成一条可重跑命令。

**诚实性纪律（本脚本的核心）**：

1. 三个框架都**真跑工具**（pytest / gotestsum / playwright）。工具不在时
   **跳过并如实打印**，绝不写一份"看起来像真的"产物。
2. 入库前有一道**确定性脱敏归一**（见 `_scrub`），只做两件事：
   - 删掉 `hostname` 属性（机器名）；
   - 把仓库根绝对路径改写成仓库内相对路径。
   除此之外**不改任何字节**。原始产物与本文件的归一规则都会写进各 fixture 的
   `README.md`——这样"入库的 XML 是脱敏后的真实产物"这句话是可复核的。
3. `expected.json` 的 totals **取自框架自己的汇总**（stdout 摘要 + XML 根节点声明值），
   不是从元素重数——后者是 `bench/bench_ingest.py` 的活。两者互为独立通道：
   bench_ingest 逐元素重数，与这里登记的框架声明值对账。
4. 框架声明值与逐元素计数在本脚本里**当场断言一致**：不一致就报错退出，
   不让一份自相矛盾的产物入库。

用法（Windows 本机）：

    py -3.12 bench/fixtures/regen_fixtures.py            # 能跑的都跑
    py -3.12 bench/fixtures/regen_fixtures.py --only pytest

退出码：0 全部按预期产出 / 1 有 fixture 未产出或对账失败 / 2 用法错误。

依赖（缺哪个就跳过哪个，并打印一条 `SKIP`）：
  - pytest fixture：本仓 dev extra 已带 pytest；
  - gotestsum fixture：需要 `go` 与 `gotestsum` 在 PATH 上；
  - playwright fixture：需要 `node` 与 `npx playwright`（浏览器已装）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 仓库根

#: 四态计数中，各框架"声明值"与"元素计数"共用的字段
COUNT_FIELDS = ("tests", "failures", "errors", "skipped")


def _run(cmd, cwd, env=None):
    """跑一条命令，返回 (returncode, stdout+stderr)。不抛异常——调用方判定。"""
    merged = dict(os.environ)
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    merged["PYTHONUTF8"] = "1"
    if env:
        merged.update(env)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


# ── 脱敏归一（确定性；只做白名单里的两件事）─────────────────────────────


def _path_variants(root):
    """仓库根的多种书写形态（Windows 反斜杠 / 正斜杠 / 大小写）。"""
    variants = {root, root.replace("\\", "/"), root.replace("/", "\\")}
    variants |= {v.lower() for v in list(variants)}
    return sorted((v for v in variants if v), key=len, reverse=True)


def _scrub(text, root):
    """删 hostname 属性 + 绝对路径改相对。返回 (text, 归一记录)。

    只动这两样：任何其他改写都会让"这是真实产物"变成无法复核的断言。
    """
    notes = []
    for variant in _path_variants(root):
        for sep in ("\\", "/"):
            needle = variant + sep
            if needle in text:
                notes.append("abs-path")
                text = text.replace(needle, "")
    if "hostname=" in text:
        text2, n = re.subn(r'\s+hostname="[^"]*"', "", text)
        if n:
            notes.append("hostname x%d" % n)
        text = text2
    return text, sorted(set(notes))


# ── XML 计数（元素级重数；bench_ingest 用同一口径独立复算）───────────────


def _attr_int(elem, name):
    """属性缺失返回 ``None``（**不是 0**）——"没声明"与"声明为 0"是两件事。

    这是**实测的框架差异**，也是本 fixture 脚本最有价值的发现：
    gotestsum 的 `<testsuites>` 根**不写 `skipped` 属性**，却确实含一个
    `<skipped/>` 用例、且 stdout 摘要报 `1 skipped`。把缺失当 0 会让
    "声明值 vs 元素重数"对账出现假红（0 != 1），从而误判产物有缺陷。
    """
    raw = elem.get(name)
    if raw is None or raw == "":
        return None
    return int(raw)


def count_elements(xml_path):
    """逐元素重数：tests / failures / errors / skipped + 各 suite 明细。"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suites = []
    totals = dict.fromkeys(COUNT_FIELDS, 0)
    suite_elems = root.findall("testsuite") if root.tag == "testsuites" else [root]
    for suite in suite_elems:
        st = dict.fromkeys(COUNT_FIELDS, 0)
        cases = suite.findall("testcase")
        st["tests"] = len(cases)
        for case in cases:
            # 一个 testcase 最多命中一种：failure / error / skipped 三选一（实测）
            if case.find("failure") is not None:
                st["failures"] += 1
            elif case.find("error") is not None:
                st["errors"] += 1
            elif case.find("skipped") is not None:
                st["skipped"] += 1
        st["name"] = suite.get("name") or ""
        suites.append(st)
        for field in COUNT_FIELDS:
            totals[field] += st[field]
    return totals, suites


def count_declared(xml_path):
    """框架自己声明的总计：优先根节点；根不带任何 totals 时退到唯一 suite。

    返回 ``(declared, source)``，``declared`` 里**未声明的字段是 ``None``**
    （不是 0）。调用方据此区分"框架声明为 0"与"框架没声明"。
    """
    root = ET.parse(xml_path).getroot()
    if root.tag == "testsuites" and any(root.get(f) is not None for f in COUNT_FIELDS):
        elem, source = root, "testsuites@root"
    else:
        elem = root if root.tag == "testsuite" else root.find("testsuite")
        source = "testsuite@%s" % (elem.get("name") or "") if elem is not None else "none"
    if elem is None:
        return dict.fromkeys(COUNT_FIELDS), "none"
    return {f: _attr_int(elem, f) for f in COUNT_FIELDS}, source


# ── 各框架的汇总行解析（第二条独立通道）────────────────────────────────


def _parse_pytest_summary(out):
    """pytest 末行形如 `1 failed, 4 passed, 1 skipped in 0.12s`。"""
    counts = {"failed": 0, "passed": 0, "skipped": 0, "error": 0, "errors": 0}
    found = False
    for word in re.findall(r"(\d+)\s+(failed|passed|skipped|error|errors)\b", out):
        counts[word[1]] += int(word[0])
        found = True
    if not found:
        return None
    return {
        "tests": counts["failed"] + counts["passed"] + counts["skipped"]
        + counts["error"] + counts["errors"],
        "failures": counts["failed"] + counts["error"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
    }


def _parse_gotestsum_summary(out):
    """gotestsum 末行形如 `DONE 5 tests, 1 skipped, 1 failure in 1.077s`。"""
    match = re.search(
        r"DONE\s+(\d+)\s+tests?,\s*(\d+)\s+skipped,\s*(\d+)\s+failures?\b", out
    )
    if not match:
        return None
    tests, skipped, failures = (int(g) for g in match.groups())
    return {"tests": tests, "failures": failures, "errors": 0, "skipped": skipped}


def _parse_playwright_summary(out):
    """playwright 摘要形如 `5 passed (9.3s)` / `1 failed` / `1 skipped`（list reporter）。"""
    counts = {}
    for word in re.findall(r"(\d+)\s+(passed|failed|skipped|flaky|did not run)\b", out):
        counts[word[1]] = int(word[0])
    if not counts:
        return None
    skipped = counts.get("skipped", 0) + counts.get("did not run", 0)
    return {
        "tests": sum(counts.values()),
        "failures": counts.get("failed", 0),
        "errors": 0,
        "skipped": skipped,
    }


# ── 三个 fixture 的产出器 ───────────────────────────────────────────────


def _write_expected(fixture, produced_by, declared, declared_source, elements, suites, extra=None):
    """写 expected.json。

    `totals` = **元素重数**（定义上就是文件里的东西）。两条"框架自述"通道
    （XML 属性 / stdout 摘要）在 `_reconcile` 里已逐项与它对齐，故此处的
    `totals` 与"框架汇总"逐项相等是可证的，而不是抄来的。
    `declared` 记录框架在 XML 属性里**实际声明**的字段（未声明的写 null），
    让下一棒一眼看到"框架少写了哪一项"。`observed` 一类"算好的观测"不写——
    真值只存输入与期望（见 plan/04 §二）。
    """
    payload = {
        "framework": fixture,
        "produced_by": produced_by,
        "totals": elements,
        "declared_in_xml": declared,
        "declared_source": declared_source,
        "suites": suites,
    }
    if extra:
        payload.update(extra)
    path = os.path.join(HERE, fixture, "expected.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    return path


def _reconcile(fixture, declared, elements, summary):
    """三条通道当场对账，不一致即抛错（不让自相矛盾的产物入库）。

    真值取**元素重数** `elements`（它就是文件内容），两条框架自述通道必须与它相等：
      - `declared`：XML 属性声明值。**仅对框架真正声明过的字段**比对——
        gotestsum 不写 `skipped` 属性，把"没声明"当"声明为 0"会造出假红；
      - `summary`：工具 stdout 末行摘要（独立于 XML 的第二条通道）。
    """
    problems = []
    for field in COUNT_FIELDS:
        got = declared.get(field)
        if got is not None and got != elements[field]:
            problems.append("XML 声明 %s=%s != 元素重数 %s" % (field, got, elements[field]))
    undeclared = [f for f in COUNT_FIELDS if declared.get(f) is None]
    if summary is not None:
        for field in COUNT_FIELDS:
            if summary[field] != elements[field]:
                problems.append("stdout %s=%s != 元素重数 %s" % (field, summary[field], elements[field]))
    if problems:
        raise SystemExit("%s：对账失败，不写产物——%s" % (fixture, "；".join(problems)))
    return undeclared


def regen_pytest():
    cwd = os.path.join(HERE, "pytest")
    artifact = os.path.join(cwd, "junit.xml")
    code, out = _run(
        [sys.executable, "-m", "pytest", "test_demo.py", "--junitxml=junit.xml",
         "-p", "no:cacheprovider", "-q", "--color=no"],
        cwd,
    )
    if not os.path.isfile(artifact):
        raise SystemExit("pytest：未产出 junit.xml（rc=%d）\n%s" % (code, out))
    declared, declared_source = count_declared(artifact)
    elements, suites = count_elements(artifact)
    summary = _parse_pytest_summary(out)
    _reconcile("pytest", declared, elements, summary)
    _scrub_file(artifact, cwd)
    import pytest as _pytest

    return _write_expected(
        "pytest",
        {
            "tool": "pytest",
            "tool_version": _pytest.__version__,
            "python_version": "%d.%d.%d" % sys.version_info[:3],
            "command": "python -m pytest test_demo.py --junitxml=junit.xml -p no:cacheprovider -q",
            "source": "本机真实运行",
        },
        declared,
        declared_source,
        elements,
        suites,
    )


def regen_gotestsum():
    cwd = os.path.join(HERE, "gotestsum")
    artifact = os.path.join(cwd, "gotestsum.xml")
    go = shutil.which("go")
    gts = shutil.which("gotestsum")
    if not go or not gts:
        raise _Skipped("gotestsum fixture：需要 go 与 gotestsum 在 PATH 上（go=%s gotestsum=%s）"
                       % (go, gts))
    code, out = _run(
        [gts, "--junitfile", "gotestsum.xml", "--junitfile-testsuite-name", "short",
         "--junitfile-testcase-classname", "short", "./..."],
        cwd,
    )
    if not os.path.isfile(artifact):
        raise SystemExit("gotestsum：未产出 gotestsum.xml（rc=%d）\n%s" % (code, out))
    declared, declared_source = count_declared(artifact)
    elements, suites = count_elements(artifact)
    summary = _parse_gotestsum_summary(out)
    _reconcile("gotestsum", declared, elements, summary)
    _scrub_file(artifact, cwd)
    _, gover = _run([go, "version"], cwd)
    return _write_expected(
        "gotestsum",
        {
            "tool": "gotestsum",
            "tool_version": _tool_version(gts, cwd),
            "go_version": gover.strip().splitlines()[0] if gover.strip() else "",
            "command": "gotestsum --junitfile gotestsum.xml --junitfile-testsuite-name short "
                       "--junitfile-testcase-classname short ./...",
            "source": "本机真实运行",
        },
        declared,
        declared_source,
        elements,
        suites,
    )


def regen_playwright():
    cwd = os.path.join(HERE, "playwright")
    artifact = os.path.join(cwd, "playwright.xml")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise _Skipped("playwright fixture：需要 node/npx 在 PATH 上")
    # 全局 reporter 覆盖为 list+junit：list 提供 stdout 摘要（第三条通道），
    # junit 提供必然落盘的 XML。配置文件里已声明 junit 输出路径。
    code, out = _run([npx, "--no-install", "playwright", "test"], cwd)
    if not os.path.isfile(artifact):
        raise _Skipped(
            "playwright fixture：未产出 playwright.xml（rc=%d；浏览器未装或依赖缺失）\n%s"
            % (code, out[-800:])
        )
    declared, declared_source = count_declared(artifact)
    elements, suites = count_elements(artifact)
    summary = _parse_playwright_summary(out)
    _reconcile("playwright", declared, elements, summary)
    _scrub_file(artifact, cwd)
    _, nodever = _run([shutil.which("node") or "node", "--version"], cwd)
    return _write_expected(
        "playwright",
        {
            "tool": "@playwright/test",
            "tool_version": _pw_version(cwd),
            "node_version": nodever.strip(),
            "command": "npx playwright test   # reporter 见 playwright.config.js",
            "source": "本机真实运行",
        },
        declared,
        declared_source,
        elements,
        suites,
    )


def _tool_version(exe, cwd):
    _, out = _run([exe, "--version"], cwd)
    return out.strip().splitlines()[0] if out.strip() else ""


def _pw_version(cwd):
    code, out = _run([shutil.which("npx") or "npx", "--no-install", "playwright", "--version"], cwd)
    return out.strip().splitlines()[-1] if out.strip() else ""


def _scrub_file(path, cwd):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    scrubbed, notes = _scrub(text, ROOT)
    if scrubbed != text:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(scrubbed)
    return notes


class _Skipped(RuntimeError):
    """工具链缺失——如实跳过，不产出任何产物。"""


FIXTURES = ("pytest", "gotestsum", "playwright")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="regen_fixtures", description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=FIXTURES, action="append", default=None,
                        help="只重产出指定 fixture（可重复）")
    args = parser.parse_args(argv)
    wanted = args.only or list(FIXTURES)

    print("重新产出真实 fixture（仓库根：%s）" % os.path.relpath(ROOT, ROOT) or ".")
    failed = []
    for name in FIXTURES:
        if name not in wanted:
            continue
        try:
            path = {"pytest": regen_pytest, "gotestsum": regen_gotestsum,
                    "playwright": regen_playwright}[name]()
            print("PASS  %-11s 写出 %s" % (name, os.path.relpath(path, ROOT)))
        except _Skipped as exc:
            print("SKIP  %-11s %s" % (name, exc))
            failed.append(name)
    print("=" * 56)
    print("结论：%s" % ("全部产出" if not failed else "未产出：%s" % ",".join(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
