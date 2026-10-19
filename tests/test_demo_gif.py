"""演示录屏 `docs/demo/demo.gif`（`plan/00` §四 提交材料实物表的"TUI 录屏"一行）。

三条 DoD 判据落在这里：**文件存在** / **时长 ≤ 30s** / **内容非空（帧数 > 1）**。
另有两条把"绿不是装饰"钉住：

- **产出脚本在位**（`tools/make-demo-gif.py`）——录屏必须可复跑，不是一次性的手工作品；
- **脚本能解析 SVG 并栅格化**（拿一个手写的最小 SVG 走一遍解析 → 断言像素被画上）——
  否则"文件存在"可能只是一个坏掉的空壳。

**诚实边界**：这是 Textual 渲染输出的栅格化，不是真终端字节流录制（见
`docs/demo/README.md`）。真终端（字体/尺寸/ConPTY）表现仍是 `plan/05` §五 的未验证项，
本文件**不**声称验过它。
"""

import os
import struct

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIF_PATH = os.path.join(ROOT, "docs", "demo", "demo.gif")
MAKER = os.path.join(ROOT, "tools", "make-demo-gif.py")

#: 时长上限（`plan/01` 题面 / `plan/06` D10：≤ 30s）
MAX_SECONDS = 30.0


def _load_maker():
    import importlib.util

    spec = importlib.util.spec_from_file_location("td_make_demo_gif", MAKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_maker_script_exists():
    """录屏必须可复跑：产出脚本在位。"""
    assert os.path.isfile(MAKER), "缺 tools/make-demo-gif.py（录屏不可复跑）"


def test_demo_gif_is_committed():
    """`git ls-files docs/demo/demo.gif` 的等价判据：文件在仓内且非空。"""
    assert os.path.isfile(GIF_PATH), "缺 docs/demo/demo.gif"
    assert os.path.getsize(GIF_PATH) > 1024, "demo.gif 太小（可能是空壳）"


def test_demo_gif_header_is_gif89a():
    """字节头必须是 GIF（防"把别的文件改名成 .gif"）。"""
    with open(GIF_PATH, "rb") as fh:
        head = fh.read(6)
    assert head[:3] == b"GIF", head
    assert head[3:6] in (b"89a", b"87a"), head


def test_demo_gif_is_animated_and_under_30s():
    """帧数 > 1（真动图）且总时长 ≤ 30s（题面硬指标）。"""
    maker = _load_maker()
    seconds, frames = maker.gif_duration_seconds(GIF_PATH)
    assert frames > 1, "只有一帧（不是动图）"
    assert 0 < seconds <= MAX_SECONDS, "总时长 %.1fs 超出上限 %.0fs" % (seconds, MAX_SECONDS)


def test_maker_check_mode_passes():
    """`--check` 自己也得绿（否则 CI 与本地判据不一致）。"""
    maker = _load_maker()
    assert maker.main(["--check"]) == 0


# ── 栅格化管线本身（防"录屏脚本坏了但没人发现"）──────────────────────


def test_svg_rasterizer_draws_background_and_text():
    """手写一个最小 SVG 走一遍解析 → 栅格化：背景色与文字像素都要被画上。"""
    maker = _load_maker()
    svg = (
        '<svg class="rich-terminal" viewBox="0 0 200 40" xmlns="http://www.w3.org/2000/svg">'
        "<style>.terminal-1-r1 { fill: #ff0000 }</style>"
        "<defs><clipPath id='c'><rect x='0' y='0' width='1' height='1'/></clipPath></defs>"
        '<rect fill="#0000ff" x="0" y="0" width="200" height="40" shape-rendering="crispEdges"/>'
        '<text class="terminal-1-r1" x="0" y="30" textLength="80" '
        'clip-path="url(#c)">TEST</text>'
        "</svg>"
    )
    image = maker.rasterize(svg)
    assert image.size[0] >= 100 and image.size[1] >= 20, image.size
    colors = image.getcolors(maxcolors=1 << 24)
    palette = {color for _count, color in colors}
    assert (0, 0, 255) in palette, "背景没被画上"
    assert (255, 0, 0) in palette, "文字没被画上（前景色缺失）"


def test_svg_parser_skips_the_canvas_title():
    """Rich 的 SVG 画布标题会被跳过——它会和 App 自己的 Header 重叠（实测踩过）。"""
    maker = _load_maker()
    svg = (
        '<svg class="rich-terminal" viewBox="0 0 200 40" xmlns="http://www.w3.org/2000/svg">'
        "<style>.terminal-1-r1 { fill: #ff0000 }</style>"
        "<defs><clipPath id='c'><rect x='0' y='0' width='1' height='1'/></clipPath></defs>"
        '<text class="terminal-1-title" fill="#fff" x="100" y="27">CanvasTitle</text>'
        '<text class="terminal-1-r1" x="0" y="30" clip-path="url(#c)">BODY</text>'
        "</svg>"
    )
    _styles, _rects, texts = maker.parse_svg(svg)
    contents = [entry[4] for entry in texts]
    assert "BODY" in contents
    assert "CanvasTitle" not in contents, "画布标题没被跳过（会和 Header 重叠）"


def test_frame_plan_stays_under_the_time_budget():
    """帧计划 × 每帧时长必须 ≤ 30s——**改帧计划时这条会红**，不是靠人记。"""
    maker = _load_maker()
    total = len(maker.FRAMES) * maker.SETTLE_FRAMES * maker.FRAME_MS / 1000.0
    assert 0 < total <= MAX_SECONDS, "帧计划总时长 %.1fs 超上限" % total


def test_frame_plan_covers_three_views_and_help():
    """动图必须覆盖三栏 + `F` + `S` + `D` + 帮助层（`plan/00` §五 的死壳判据）。"""
    maker = _load_maker()
    keys = [key for key, _label in maker.FRAMES]
    for wanted in ("F", "S", "D", "question_mark"):
        assert wanted in keys, "帧计划缺 %s（死壳判据：视图没演示到）" % wanted
