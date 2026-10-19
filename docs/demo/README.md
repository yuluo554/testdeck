# docs/demo — TUI 演示录屏

`demo.gif` 是 `testdeck tui` 的演示动图（8 个状态位，**24.0s**，上限 30s）。
它由 `tools/make-demo-gif.py` 一条命令重新产出。

## 它是怎么做出来的（如实说明）

**这是 TUI 真实渲染输出的栅格化，不是"真终端里抓下来的字节流"。**

本机是 Windows：标准库没有 `pty` / `termios`，`winpty` 在非 tty 下直接断言失败（实测），
`asciinema` / `agg` / `pyte` 都不在，而本轮**不下载任何工具**。于是取的通路是
Textual 自己的 `App.export_screenshot()`——它渲染的正是 `App.run()` 会画到终端上的
同一份 `Screen._compositor.render_update()`，只是序列化成 SVG。脚本把那份 SVG
（`<rect>` 背景 + `<text>` 前景）用 Pillow 栅格化成 PNG 帧，再拼成 GIF。

字体用系统里的 **SimSun**（`simsun.ttc`）：实测 ASCII 与 CJK 恰好 **2:1**（10px / 20px @20px），
与终端等宽网格一致。粗体不用 `simsunb.ttf`（实测那是 SimSun-**ExtB**，只有罕见扩展区汉字，
常用汉字会渲染成豆腐块），改为对同一份字体加一圈描边模拟。

**因此它证明的是**：TUI 在 100×30 下真的渲染出这些内容（三栏 / `F` / `S` / `D` / 帮助层），
且内容与实现一致（同一份 `view.py` + `queries.py` 的输出）。

**它不证明**：真终端（Windows Terminal / ConPTY）下字体、尺寸、像素级的实际表现。
那一条仍是 `plan/05` §五 的**已知未验证项**与 `plan/06` 的 **G6**——本轮**未关闭**，
不得写成"真终端已验证"。

## 演示用的第二个 run 是脚手架

动图里的 `D`（新增失败 / 修复 / 仍失败）与 `S`（回归 `reg=y`）需要**两条 run**。
而三份真跑产物**都没有声明身份**（`branch` / `commit` / `ci_run_id` 全空），按 K26
会全部落进同一个"未标注 run"——只有一条 run 时 `D` 只能说"没有可 diff 的上一棒"。

所以 `tools/make-demo-gif.py` 另写了一份**演示脚手架**产物（同一组用例身份，一条从
pass 变 fail、一条从 fail 变 pass、耗时抬升），显式声明身份三元组让它自成一个 run。
它只写到 `bench/.tmp/`（**不入仓**，见 `.gitignore`），不入库、不进基准、不参与任何对账。
它的作用是"让动图演示得出这两条功能"，不是"造真值"。

## 重新产出

```bash
py -3.12 tools/make-demo-gif.py            # 写 docs/demo/demo.gif
py -3.12 tools/make-demo-gif.py --check    # 只校验存在且 ≤30s
```

`tests/test_demo_gif.py` 把"文件在、能打开、帧数 > 1、总时长 ≤ 30s"写成可跑红的断言。
