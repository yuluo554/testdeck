#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""布局门（方法论装订的第②件）：把"项目还长在方法论上"变成可跑红的断言。

用法：
    py -3.12 tools/check-sprint-layout.py          # Windows 本机
    python tools/check-sprint-layout.py            # CI / Linux

退出码：0 全绿 / 1 有 FAIL / 2 用法错误。

判据一律落**仓库内文件**，不读 git 元数据（tag / 历史深度 / remote 在 CI 浅克隆下会翻转）。
每条判据都遵守三条纪律：
  ① 非空跑自证——本轮扫到几份文档 / 几份交接单 / 几处状态副本，必须打出来；
  ② 永不崩——被检查对象不存在时报 FAIL 并继续，不是异常逃逸（否则 rc=1 但一条结论都没跑）；
  ③ 枚举式——状态副本逐个采集后交叉比对，**真值不取自任何一个副本**（自我参照 = 恒真）。
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKS = []
SCANNED = {"docs": 0, "handoffs": 0, "copies": 0, "milestones": 0}


def add(check_id, ok, detail):
    CHECKS.append({"id": check_id, "ok": bool(ok), "detail": detail})


def read(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ── 配置：改布局只改这里 ────────────────────────────────────────────────
REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "data/README.md",
    "plan/00-README总览.md",
    "plan/01-题目文档.md",
    "plan/02-架构与技术选型.md",
    "plan/03-模块详设.md",
    "plan/04-数据计划.md",
    "plan/05-里程碑与发布.md",
    "plan/06-交付对标与决策.md",
]

REQUIRED_SECTIONS = {
    "plan/00-README总览.md": ["文档索引", "决策记录", "承诺-证据台账", "里程碑"],
    "plan/01-题目文档.md": ["任务要求", "评分标准", "边界与非目标"],
    "plan/02-架构与技术选型.md": ["分层", "CLI 契约", "数据库", "构建"],
    "plan/03-模块详设.md": ["模块①", "模块⑤", "降级"],
    "plan/04-数据计划.md": ["数据清单", "真值纪律", "数值口径"],
    "plan/05-里程碑与发布.md": ["DoD", "退出码", "已知未验证项"],
    "plan/06-交付对标与决策.md": ["评分对标", "待定决策", "风险登记"],
    "data/README.md": ["依据查证记录", "数值口径"],
}

# 装订行：三个锚点必须**同现于一行**（前瞻，顺序无关）。写成"或"关系会让残句也判绿。
BINDING_LINE = re.compile(
    r"^>(?=.*ai-tool-project-sprint)(?=.*check-sprint-layout)(?=.*20\d{2}-\d{2}-\d{2}).*$",
    re.M,
)

# 交接单六节（语义关键词；项目自定更细格式是合法超集，不断言节数恰好为 6）
HANDOFF_SECTIONS = ["当前进度", "待办", "既定口径", "环境坑", "DoD", "命令速查"]

# 状态副本：同一里程碑在这几处的状态必须互相一致。下界 = 本清单长度（防漏扫）。
STATUS_COPIES = [
    "plan/00-README总览.md",
    "plan/05-里程碑与发布.md",
    "plan/06-交付对标与决策.md",
    "README.md",
]

MILESTONES = list(range(0, 7))
RELEASE_MILESTONE = 6

# 只认"状态行"：表格行且首格就是里程碑号。扫自由文本会把
# "M0–M6 完成……未验证项保持 ⬜" 读成"M0/M6 仍挂 ⬜"（张冠李戴）。
STATUS_LINE = re.compile(r"^\|\s*\*{0,2}M(\d+)\b")
PENDING_MARKERS = ["⬜", "🟡", "未开始", "未执行", "待执行", "待确认"]


def check_required_files():
    missing = [rel for rel in REQUIRED_FILES if not os.path.isfile(os.path.join(ROOT, rel))]
    SCANNED["docs"] = len(REQUIRED_FILES) - len(missing)
    add(
        "LAYOUT.FILES",
        not missing,
        "缺: " + ",".join(missing) if missing else "%d 份必备文件齐备" % SCANNED["docs"],
    )


def check_binding_head():
    text = read("plan/00-README总览.md") or ""
    ok = bool(BINDING_LINE.search(text))
    add(
        "LAYOUT.BINDING_HEAD",
        ok,
        "plan/00 顶部有装订行（方法论名 + 布局门命令 + 日期同现）"
        if ok
        else "plan/00 顶部缺装订行：需同一行同现 ai-tool-project-sprint / check-sprint-layout / 日期",
    )


def check_sections():
    bad = []
    seen = 0
    for rel, needles in REQUIRED_SECTIONS.items():
        text = read(rel)
        if text is None:
            continue
        seen += 1
        missing = [n for n in needles if n not in text]
        if missing:
            bad.append("%s: 缺 %s" % (rel, "/".join(missing)))
    add(
        "LAYOUT.SECTIONS",
        not bad,
        "；".join(bad) if bad else "%d 份文档的小节齐备" % seen,
    )


def collect_states():
    """逐副本采集状态：{里程碑: {done/pending}}。真值不取自任何一个副本。"""
    states = {}
    missing_in = []
    for rel in STATUS_COPIES:
        text = read(rel)
        if text is None:
            missing_in.append(rel)
            continue
        SCANNED["copies"] += 1
        found = set()
        for line in text.splitlines():
            m = STATUS_LINE.match(line)
            if not m:
                continue
            k = int(m.group(1))
            if k not in MILESTONES:
                continue
            found.add(k)
            state = "pending" if any(mark in line for mark in PENDING_MARKERS) else "done"
            states.setdefault(k, set()).add(state)
        for k in MILESTONES:
            if k not in found:
                missing_in.append("%s 未列出 M%d" % (rel, k))
    SCANNED["milestones"] = len(states)
    return states, missing_in


def check_status_agreement(states, missing_in):
    problems = []
    for k in MILESTONES:
        if k not in states:
            problems.append("M%d 在所有副本里都没出现" % k)
            continue
        if len(states[k]) > 1:
            problems.append("M%d 在副本间状态不一致（%s）" % (k, " vs ".join(sorted(states[k]))))
    if missing_in:
        problems.append("副本覆盖不全: " + "；".join(missing_in[:6]))
    if SCANNED["copies"] < len(STATUS_COPIES):
        problems.append("只扫到 %d 处副本（下界 %d）" % (SCANNED["copies"], len(STATUS_COPIES)))
    add(
        "LAYOUT.STATUS",
        not problems,
        "；".join(problems)
        if problems
        else "%d 处副本 × %d 个里程碑 状态全一致" % (SCANNED["copies"], len(states)),
    )


def done_milestones(states):
    return [k for k in MILESTONES if "done" in states.get(k, set())]


def check_handoffs(done):
    """每个 ✅ 里程碑一份交接单；**且当前棒的下一棒交接单必须已落盘**。

    后半条是硬约束①的机器化：里程碑收尾 = 本对话内写完下一棒 HANDOFF。
    M0 没有上一棒，其收尾记录即计划套件本身，故 M0 本身豁免；但 M0 收尾必须已写
    `HANDOFF-M1`。这条让门在"只有 M0 完成"的现在也是**非空跑**的。
    """
    problems = []
    required = set()
    for k in done:
        if k == 0:
            continue
        required.add(k)
    if done:
        nxt = max(done) + 1
        if nxt <= RELEASE_MILESTONE:
            required.add(nxt)
    for k in sorted(required):
        rel = "plan/HANDOFF-M%d.md" % k
        text = read(rel)
        if text is None:
            problems.append("%s(缺)" % rel)
            continue
        SCANNED["handoffs"] += 1
        missing = [s for s in HANDOFF_SECTIONS if s not in text]
        if missing:
            problems.append("%s(缺节: %s)" % (rel, "/".join(missing)))
    if not required:
        problems.append("没有任何里程碑完成、也无下一棒交接单——判据空转")
    add(
        "LAYOUT.HANDOFFS",
        not problems,
        "；".join(problems)
        if problems
        else "%d 份交接单齐（需 %s）"
        % (SCANNED["handoffs"], ",".join("M%d" % k for k in sorted(required))),
    )


def _gap_column_index(header_line):
    cells = header_line.strip().strip("|").split("|")
    for idx, cell in enumerate(cells):
        if "缺口" in cell:
            return idx
    return None


def check_stale_gaps(done):
    text = read("plan/06-交付对标与决策.md") or ""
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "缺口" in line:
            header_idx = i
            break
    if header_idx is None:
        add("LAYOUT.GAPS", False, "plan/06 找不到含『缺口』表头的表（判据表搬走了？）")
        return
    col = _gap_column_index(lines[header_idx])
    if col is None:
        add("LAYOUT.GAPS", False, "plan/06 的缺口表头无法定位列号")
        return
    stale = []
    rows = 0
    for line in lines[header_idx + 2:]:
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        if re.fullmatch(r"[\|\s:\-]+", line.strip()):
            continue
        cells = line.strip().strip("|").split("|")
        if col >= len(cells):
            continue
        rows += 1
        cell = cells[col]
        for k in done:
            if re.search(r"(^|[^0-9A-Za-z])M%d([^0-9]|$)" % k, cell):
                stale.append("缺口列仍提已完成的 M%d：%s" % (k, cell.strip()[:60]))
    if rows == 0:
        add("LAYOUT.GAPS", False, "plan/06 缺口表没有数据行（非空跑自证失败）")
        return
    add(
        "LAYOUT.GAPS",
        not stale,
        "；".join(stale) if stale else "%d 行缺口登记中无已 ✅ 里程碑" % rows,
    )


def check_release_doc(done):
    if RELEASE_MILESTONE not in done:
        add(
            "LAYOUT.RELEASE",
            True,
            "M%d 未完成：发布留档此刻不要求（发布门在 M%d 生效）"
            % (RELEASE_MILESTONE, RELEASE_MILESTONE),
        )
        return
    rel = "plan/RELEASE-M%d.md" % RELEASE_MILESTONE
    text = read(rel)
    if text is None:
        add("LAYOUT.RELEASE", False, "缺 %s" % rel)
        return
    two_cols = bool(re.search(r"^##\s*一、.*tag\s*前", text, re.M)) and bool(
        re.search(r"^##\s*二、.*tag\s*后", text, re.M)
    )
    coverage = bool(re.search(r"^#{2,3}.*覆盖对账", text, re.M))
    rows = len(re.findall(r"^\|.*(?:实现|不适用|待首推).*\|$", text, re.M))
    add(
        "LAYOUT.RELEASE",
        two_cols and coverage and rows >= 3,
        "两栏:%s 覆盖对账小节:%s 三态行数:%d" % (two_cols, coverage, rows),
    )


def run_guarded(fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 - 门永不崩，异常本身算 FAIL
        add(fn.__name__.upper(), False, "检查项异常: %s: %s" % (type(exc).__name__, exc))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    run_guarded(check_required_files)
    run_guarded(check_binding_head)
    run_guarded(check_sections)
    states, missing_in = ({}, [])
    try:
        states, missing_in = collect_states()
    except Exception as exc:  # noqa: BLE001
        add("COLLECT_STATES", False, "状态采集异常: %s" % exc)
    done = done_milestones(states)
    run_guarded(check_status_agreement, states, missing_in)
    run_guarded(check_handoffs, done)
    run_guarded(check_stale_gaps, done)
    run_guarded(check_release_doc, done)

    failed = [c for c in CHECKS if not c["ok"]]
    print("布局门（方法论装订） · 判据只落仓库内文件")
    print("=" * 60)
    for c in CHECKS:
        print("%s  %-22s %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["detail"]))
    print("=" * 60)
    print(
        "这轮扫到：文档 %d / 交接单 %d / 状态副本 %d / 里程碑 %d"
        % (
            SCANNED["docs"],
            SCANNED["handoffs"],
            SCANNED["copies"],
            SCANNED["milestones"],
        )
    )
    print("结论: %s" % ("全绿" if not failed else "%d 项 FAIL" % len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
