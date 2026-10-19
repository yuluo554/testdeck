#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 TUI 的**真实渲染输出**（Textual 的 SVG 截图）栅格化成 PNG 帧，并拼成 GIF。

为什么走这条路（而不是抓 ConPTY 的字节流）：本机是 Windows，标准库没有 `pty` /
`termios`，`winpty` 在非 tty 下会直接断言失败（实测），`asciinema` / `agg` 都不在。
**不装新工具**（本轮不下载）的前提下，唯一能拿到"TUI 真实渲染输出"的通路是
Textual 自己的 `App.export_screenshot()`——它渲染的正是 `App.run()` 会画到终端上的
同一份 `Screen._compositor.render_update()`，只是序列化成 SVG。

于是本脚本做三件事：

1. 用 `tests` 同样的方式（无头 Pilot）驱动 App，逐帧 `export_screenshot()`；
2. 解析 SVG（`<rect>` 背景 + `<text>` 前景），用 Pillow 栅格化——字体用系统里的
   **SimSun**（`simsun.ttc`）：实测 ASCII 与 CJK 都是**恰好 2:1**（10px / 20px @20px），
   与终端等宽网格一致，不需要 `wcwidth`（未安装）；
3. 用 Pillow 把帧序列写成 `docs/demo/demo.gif`（**只改时长，不改内容**）。

**诚实边界（写进 `docs/demo/README.md`）**：这是 Textual 渲染输出的栅格化，
不是"真终端里录下来的字节流"。它证明的是"TUI 在 100×30 下真的渲染出这些内容"，
**不**证明 ConPTY/字体下的像素级表现——后者仍是 `plan/05` §五 的未验证项（G6）。

用法（在仓库根跑）：

    py -3.12 tools/make-demo-gif.py            # 写出 docs/demo/demo.gif
    py -3.12 tools/make-demo-gif.py --check    # 只校验 GIF 存在且 ≤30s，不写盘
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

DEMO_DIR = os.path.join(ROOT, "docs", "demo")
GIF_PATH = os.path.join(DEMO_DIR, "demo.gif")

#: 录制尺寸（固定：`plan/05` §五 要求录屏固定终端尺寸）
TERMINAL_SIZE = (100, 30)
#: 每帧停留时长（毫秒）——**只影响播放节奏，不改内容**
FRAME_MS = 1000
#: 帧序列（按键 → 说明）；`start` 表示"按当前状态拍一帧"
FRAMES = (
    ("start", "三栏：失败优先树 + summary + failure 原文/sparkline"),
    ("F", "F：flaky 矩阵（test × run 四态 + 分型标签）"),
    ("escape", "Esc 回到三栏"),
    ("S", "S：慢测试（p50/p95 + 回归标记 + 瀑布条）"),
    ("escape", "Esc 回到三栏"),
    ("D", "D：两次 run 的用例级 diff（三类分组）"),
    ("escape", "Esc 回到三栏"),
    ("question_mark", "?：帮助层（键位来自 keys.py）"),
)
#: 每个状态位额外停留的"入场帧"数（让动图有"动"的感觉，但内容不变）。
#: 总时长 = len(FRAMES) × SETTLE_FRAMES × FRAME_MS，必须 ≤ 30s（`plan/05` §五）。
SETTLE_FRAMES = 3
#: 字体（SimSun：ASCII 与 CJK 恰 2:1，与终端网格一致）。
#: **粗体不用 `simsunb.ttf`**——实测那是 SimSun-ExtB（只有罕见扩展区汉字），
#: 常用汉字会渲染成豆腐块。改为对同一份 SimSun 加一圈 `stroke_width` 描边来模拟粗体，
#: 既保住字形，又不引入第二种字体度量。
FONT_REGULAR = "C:/Windows/Fonts/simsun.ttc"
FONT_SIZE = 20
#: 模拟粗体的描边宽度（像素；0 = 不描边）
BOLD_STROKE = 1


# ── SVG 解析（只认 Rich 的 `rich-terminal` 形态）────────────────────────


_STYLE_RE = re.compile(r"\.(terminal-\d+-r\d+)\s*\{([^}]*)\}")
_CLASS_RE = re.compile(r"class=\"([^\"]+)\"")
_TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_RECT_RE = re.compile(r"<rect\b([^>]*)/>")
_ATTR_RE = re.compile(r"([\w-]+)=\"([^\"]*)\"")
_FILL_RE = re.compile(r"fill:\s*([^;}\s]+)")
_WEIGHT_RE = re.compile(r"font-weight:\s*bold")


def _attrs(text):
    return {key: value for key, value in _ATTR_RE.findall(text)}


def _unescape(text):
    return (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
                .replace("&#160;", " ").replace("&#xa0;", " "))


def parse_svg(svg_text):
    """SVG → ``(styles, rects, texts)``。

    - ``styles``：类名 → ``(fill, bold)``；
    - ``rects``：``(x, y, w, h, fill)``（按文档顺序，先画的在下层）；
    - ``texts``：``(x, y, fill, bold, content)``（按文档顺序）。
    """
    styles = {}
    for name, body in _STYLE_RE.findall(svg_text):
        fill = _FILL_RE.search(body)
        styles[name] = (fill.group(1) if fill else "#ffffff",
                        bool(_WEIGHT_RE.search(body)))

    body = svg_text.split("</defs>", 1)[-1]
    rects = []
    for raw in _RECT_RE.findall(body):
        attrs = _attrs(raw)
        fill = attrs.get("fill")
        if not fill or fill.startswith("url(") or fill in ("none", "transparent"):
            continue
        rects.append((float(attrs.get("x", 0)), float(attrs.get("y", 0)),
                      float(attrs.get("width", 0)), float(attrs.get("height", 0)), fill))

    texts = []
    for raw_attrs, raw_text in _TEXT_RE.findall(body):
        attrs = _attrs(raw_attrs)
        content = _unescape(raw_text)
        if content.strip() == "":
            continue  # 换行占位，不画
        cls = _CLASS_RE.search(raw_attrs)
        class_name = cls.group(1) if cls else ""
        if class_name.endswith("-title"):
            # Rich 的 SVG **画布标题**（不是终端屏幕的一部分）：它按 y=27 画在
            # 内容第一行上，会和 App 自己的 Header 重叠。真终端里没有这一行，
            # 所以这里跳过——只栅格化"终端屏幕上真实存在的东西"。
            continue
        fill, bold = styles.get(class_name, ("#ffffff", False))
        texts.append((float(attrs.get("x", 0)), float(attrs.get("y", 0)), fill, bold, content))
    return styles, rects, texts


# ── 栅格化 ────────────────────────────────────────────────────────────


def _rgb(value):
    value = value.strip()
    if value.startswith("#"):
        if len(value) == 4:  # #abc
            value = "#" + "".join(c * 2 for c in value[1:])
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    if value.startswith("rgba"):
        parts = value[value.find("(") + 1:value.find(")")].split(",")
        return tuple(int(float(p)) for p in parts[:3])
    raise ValueError("unsupported color: %r" % value)


def rasterize(svg_text, scale=1):
    """SVG → PIL 图像（真实渲染输出的栅格化）。"""
    _styles, rects, texts = parse_svg(svg_text)
    width = int(max([r[0] + r[2] for r in rects] + [t[0] for t in texts] + [0])) + 2
    height = int(max([r[1] + r[3] for r in rects] + [t[1] for t in texts] + [0])) + 2
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    for x, y, w, h, fill in rects:
        try:
            color = _rgb(fill)
        except ValueError:
            continue
        if w <= 0 or h <= 0:
            continue
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)

    regular = ImageFont.truetype(FONT_REGULAR, FONT_SIZE)
    for x, y, fill, is_bold, content in texts:
        try:
            color = _rgb(fill)
        except ValueError:
            color = (255, 255, 255)
        # SVG 的 y 是基线；PIL 的 anchor="ls" 就是 baseline-left
        draw.text((x, y), content, font=regular, fill=color, anchor="ls",
                  stroke_width=BOLD_STROKE if is_bold else 0, stroke_fill=color)
    if scale != 1:
        image = image.resize((width * scale, height * scale), Image.LANCZOS)
    return image


# ── 驱动 App 拍帧 ─────────────────────────────────────────────────────


def _build_demo_db(repo_root, db_path):
    """建一个**两 run** 的演示库：三份真跑产物（run A）+ 一份合成"下一棒"（run B）。

    为什么要第二个 run：三份真跑产物**都没有声明身份**（`branch` / `commit` /
    `ci_run_id` 全空），按 K26 会全部落进同一个"未标注 run"。只有一条 run 时
    `S` 视图的回归判定落 `missing_window`、`D` 视图只能说"没有可 diff 的上一棒"——
    动图就演示不出这两条功能。

    run B 是**演示脚手架**：同样的一组用例，其中一条从 pass 变 fail（`D` 的"新增失败"）、
    一条从 fail 变 pass（"修复"）、整体耗时抬升（`S` 的回归）。它只写到
    `bench/.tmp/`（**不入仓**，见 .gitignore），并在 `docs/demo/README.md` 里如实标注。
    """
    from testdeck import cli, exit_codes

    def _fixture_paths():
        return [os.path.join(repo_root, "bench", "fixtures", name)
                for name in ("pytest/junit.xml", "gotestsum/gotestsum.xml",
                             "playwright/playwright.xml")]

    code = cli.main(["ingest", *_fixture_paths(), "--db", db_path])
    if code != exit_codes.OK:
        raise SystemExit("演示库构建失败：ingest 返回 %d" % code)

    scaffold = os.path.join(os.path.dirname(db_path), "demo_next_run.xml")
    with io.open(scaffold, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_scaffold_xml())
    code = cli.main(["ingest", scaffold, "--db", db_path])
    if code != exit_codes.OK:
        raise SystemExit("演示库构建失败（第二个 run）：ingest 返回 %d" % code)


def _scaffold_xml():
    """演示用"下一棒"产物：**同一组用例身份**（取自三份真跑产物），状态与耗时按剧本变。

    剧本（都是为了演示三条功能，不是"造真值"）：

    - `test_add_returns_sum`（pytest）：pass → **fail**（`D` 的新增失败）
    - `test_deliberate_failure_fixture`（pytest）：fail → **pass**（`D` 的修复）
    - `deliberate failure fixture: counter text`（playwright）：fail → fail（`D` 的仍失败）
    - 耗时整体抬升：`renders the page title` 281ms → **1400ms**（`S` 的回归：
      ratio 4.98 ≥ 1.2 且 delta 1119ms ≥ 200ms）

    身份三元组在根与 `testsuite` 上显式声明，所以它自成一个 run——这正是 K26
    的**正确用法**（CI 在 XML 里写身份属性，多份产物才会分成多个 run）。
    """
    branch, commit, ci_run = "main", "0" * 39 + "9", "1000000009"
    # (suite, classname, name, 本棒耗时 ms, 本棒状态)
    plan = [
        ("pytest", "bench.fixtures.pytest.test_demo", "test_add_returns_sum", 0, "fail"),
        ("pytest", "bench.fixtures.pytest.test_demo", "test_add_is_commutative", 0, "pass"),
        ("pytest", "bench.fixtures.pytest.test_demo", "test_div_returns_quotient", 0, "pass"),
        ("pytest", "bench.fixtures.pytest.test_demo", "test_div_guards_zero", 0, "pass"),
        ("pytest", "bench.fixtures.pytest.test_demo", "test_deliberate_failure_fixture", 0, "pass"),
        ("pytest", "bench.fixtures.pytest.test_demo", "test_not_implemented_yet_subtract", 0, "skip"),
        ("demo-lib", "demo-lib", "TestAdd", 0, "pass"),
        ("demo-lib", "demo-lib", "TestIsEven", 0, "pass"),
        ("demo-lib", "demo-lib", "TestDivByZero", 0, "pass"),
        ("demo-lib", "demo-lib", "TestDeliberateFailureFixture", 0, "fail"),
        ("demo-lib", "demo-lib", "TestNotImplementedYetSubtract", 0, "skip"),
        ("todo.spec.js", "todo.spec.js", "renders the page title", 1400, "pass"),
        ("todo.spec.js", "todo.spec.js", "adds an item to the list", 600, "pass"),
        ("todo.spec.js", "todo.spec.js", "removes an item when its button is clicked", 700, "pass"),
        ("todo.spec.js", "todo.spec.js", "updates the remaining counter", 800, "pass"),
        ("todo.spec.js", "todo.spec.js", "ignores blank submissions", 500, "pass"),
        ("todo.spec.js", "todo.spec.js", "deliberate failure fixture: counter text", 5200, "fail"),
        ("todo.spec.js", "todo.spec.js", "not implemented yet: persisted storage", 242, "skip"),
    ]
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             '<testsuites name="demo next run" branch="%s" commit="%s" ci_run_id="%s">'
             % (branch, commit, ci_run)]
    by_suite = {}
    for suite, classname, name, ms, status in plan:
        by_suite.setdefault(suite, []).append((classname, name, ms, status))
    for suite, entries in by_suite.items():
        failures = sum(1 for _c, _n, _ms, s in entries if s == "fail")
        skips = sum(1 for _c, _n, _ms, s in entries if s == "skip")
        lines.append('  <testsuite name="%s" branch="%s" commit="%s" ci_run_id="%s"'
                     % (suite, branch, commit, ci_run))
        lines.append('             tests="%d" failures="%d" skipped="%d" time="0.100">'
                     % (len(entries), failures, skips))
        for classname, name, ms, status in entries:
            child = ""
            if status == "fail":
                child = ('<failure message="Failed" type="AssertionError">'
                         'demo scaffold failure</failure>')
            elif status == "skip":
                child = "<skipped/>"
            lines.append('    <testcase classname="%s" name="%s" time="%.3f">%s</testcase>'
                         % (classname, name, ms / 1000.0, child))
        lines.append("  </testsuite>")
    lines.append("</testsuites>")
    return "\n".join(lines) + "\n"


async def capture_frames(db_path):
    """按 `FRAMES` 驱动 App，逐状态拍帧（每状态另加 `SETTLE_FRAMES` 张同内容帧）。"""
    from testdeck.tui.app import TestDeckApp

    frames = []
    app = TestDeckApp(db_path, env={"COLORTERM": "truecolor", "TERM": "xterm"}, isatty=True)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        for _ in range(400):
            if app.report is not None:
                break
            await pilot.pause()
        for key, _label in FRAMES:
            if key != "start":
                await pilot.press(key)
                for _ in range(60):
                    await pilot.pause(0.02)
            # `title=""`：去掉 Textual 自动画的标题（它会和 App 的 Header 重叠，
            # 实测：默认标题 "TestDeckApp" 会叠在 `run #1` 那一行上）
            svg = app.export_screenshot(title="")
            for _ in range(SETTLE_FRAMES):
                frames.append(svg)
    return frames


def build_gif(db_path, gif_path):
    frames_svg = asyncio.run(capture_frames(db_path))
    images = [rasterize(svg) for svg in frames_svg]
    os.makedirs(os.path.dirname(gif_path), exist_ok=True)
    images[0].save(gif_path, save_all=True, append_images=images[1:],
                   duration=FRAME_MS, loop=0, optimize=True, disposal=2)
    return len(images)


# ── CLI ───────────────────────────────────────────────────────────────


def gif_duration_seconds(path):
    """GIF 总时长（秒）——用帧数与每帧 duration 算，不猜。"""
    with Image.open(path) as image:
        count = getattr(image, "n_frames", 1)
        duration = 0
        for index in range(count):
            image.seek(index)
            duration += image.info.get("duration", 0)
    return duration / 1000.0, count


def main(argv=None):
    parser = argparse.ArgumentParser(prog="make-demo-gif", description="TUI 渲染输出 → demo.gif")
    parser.add_argument("--db", default=None, help="演示库路径（默认 bench/.tmp/demo.db）")
    parser.add_argument("--check", action="store_true", help="只校验，不写盘")
    parser.add_argument("--scale", type=int, default=1, help="栅格化放大倍数（默认 1）")
    args = parser.parse_args(argv)

    if args.check:
        if not os.path.isfile(GIF_PATH):
            print("FAIL  缺 %s" % os.path.relpath(GIF_PATH, ROOT))
            return 1
        seconds, count = gif_duration_seconds(GIF_PATH)
        ok = seconds <= 30.0 and count > 1
        print("%s  %s：%d 帧 / %.1fs（上限 30s）"
              % ("PASS" if ok else "FAIL", os.path.relpath(GIF_PATH, ROOT), count, seconds))
        return 0 if ok else 1

    db_path = args.db or os.path.join(ROOT, "bench", ".tmp", "demo.db")
    if not os.path.isfile(db_path):
        _build_demo_db(ROOT, db_path)
    count = build_gif(db_path, GIF_PATH)
    seconds, frames = gif_duration_seconds(GIF_PATH)
    print("PASS  写出 %s：%d 帧（%d 张截图）/ %.1fs / %d 字节"
          % (os.path.relpath(GIF_PATH, ROOT), frames, count, seconds,
             os.path.getsize(GIF_PATH)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
