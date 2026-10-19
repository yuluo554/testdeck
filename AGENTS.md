# AGENTS.md

本仓库遵循 **`ai-tool-project-sprint`** 方法论（装订日期：**2026-10-18**）。

## 任何新对话的第一件事

```bash
py -3.12 tools/check-sprint-layout.py     # Windows 本机
python tools/check-sprint-layout.py       # CI / Linux
```

- 布局门必须绿；红了**先修布局再干活**，不要把红当噪声。
- 续接对话：读 `plan/HANDOFF-M<k>.md`（第 k 棒的交接单），**先跑上面这条门**。
- 接手对话（无 HANDOFF）：先读 `plan/00`、`plan/05`、`plan/06` 与各 HANDOFF，重建
  "当前状态 + 既定口径（K 编号）清单"，先汇报再动手。
- **门不存在 = 本项目没装订** → 先补装订三件（本文件 + `tools/check-sprint-layout.py` +
  `plan/00` 顶部装订行），再做别的。

## 强制布局（布局门逐条断言，改动前先看这里）

| 项 | 位置 | 判据 |
| --- | --- | --- |
| 计划套件 | `plan/00`–`plan/06` + `data/README.md` | 存在，且各含必需小节（标题关键词） |
| 数据台账 | `data/README.md` | 含「依据查证记录」「数值口径」两节 |
| 交接单 | `plan/HANDOFF-M<k>.md` | 每个 ✅ 里程碑一份，六节齐（进度/待办/既定口径/环境坑/DoD/命令速查）；**M0 已声明豁免**（其收尾记录即计划套件本身），但 **M0 收尾必须已写 `HANDOFF-M1`** |
| 里程碑状态副本 | `plan/00` 里程碑表 + `plan/05` 状态表 + `plan/06` 缺口表 + `README.md` 状态表 | **四处逐里程碑一致**；判据只认"表格行且首格是 M\<k\>"，不扫自由文本 |
| 发布留档 | `plan/RELEASE-M6.md` | M6 完成后必须存在：两栏（tag 前 / tag 后）+ 阶段 7 覆盖对账表（实现 / 不适用+理由 / 待首推） |
| 装订行 | `plan/00` 顶部 | 同一行同现：`ai-tool-project-sprint` + `check-sprint-layout` + 装订日期 |

**强制布局只放结构性质的项**（存在性 / 节齐 / N 处一致），不放会随实现漂移的数字
（测试数 / 用例数 / 提交数 / run 数）——那些写进 tag 树那一刻就过期。

## 本机环境事实（实测日期见括号）

- Windows + Git Bash；`python` 是商店占位符，**用 `py`**；中文输出用 `py -X utf8`（2026-10-18）。
- `py -0p`：**3.8.8-64 与 3.12-64 两条通道**；本项目 `requires-python >=3.9`，
  本机跑测试/构建一律用 **`py -3.12`**（2026-10-18）。
- `node v24.15.0`、`npm 11.12.1` 在；**`go` 不在 PATH 上**（2026-10-19 复测）。
  但 Go 工具链**可下载**（`https://dl.google.com/go/` 实测可达）——M1 就是这样拿到
  `go1.23.4` 真跑 gotestsum fixture 的（见 `bench/fixtures/gotestsum/README.md`）。
  → **不要**再把 D2/D3 说成"只能预置产物"：M1 已改为真跑产出。
- Playwright 同理：npm 官方源不通，但 `registry.npmmirror.com` 与
  `cdn.npmmirror.com/binaries/playwright` 可达（2026-10-19 实测）——M1 用它们装了
  `@playwright/test` 1.48.2 + Chromium 130 并真跑产出 fixture。
- 依赖镜像（2026-10-19 实测可达）：`pypi.tuna.tsinghua.edu.cn`、`goproxy.cn`、
  `registry.npmmirror.com`。**官方源**（`proxy.golang.org`、`registry.npmjs.org`）
  当时不通——装包失败先换镜像，再定性。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**（`git remote -v` 为空）。
- `github.com` git 通道间歇 `Failed to connect`；判据是"远端 sha == 本地 sha"，不是 push 退出码。
- 本机注册表代理会污染 pip；装包失败先加 `NO_PROXY="*" no_proxy="*"` 与清华镜像。
- pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` 再重试。
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用 `py -3.12` 以
  `encoding="utf-8"` 回读，或直接读文件。
- **`/tmp` 在 Git Bash 与 Windows Python 眼里不是同一个目录**（实测坑）：Git Bash 的 `/tmp`
  是 `C:\Users\<用户>\AppData\Local\Temp`，而 `py -3.12` 收到的 `/tmp/x` 会解析成 `D:\tmp\x`。
  跨工具传路径时用仓库内相对路径，或写全 `C:/...`。
- **`os.path.relpath` 跨盘符会抛 `ValueError`**（实测：仓库在 `D:\`、临时目录在 `C:\`）：
  凡"展示用相对路径"的地方都要 try/except 回落原路径。
- 任何"本机没有 X"的结论都带实测日期，下一棒先复测再引用。

## 禁止

- 把"未执行"写成已完成；"CI 绿"在无远端时只能写"本地等价校验（CI 待首推验证）"。
- 在 tag 之后改代码面；为让 WARN 消失而重打 tag。
- 把本机绝对路径写进入库文件（HANDOFF / 计划 / 留档一律相对路径）。
- 在 `src/` 里引入网络客户端（本项目零网络调用，由 `tests/test_no_network.py` 守门）。
