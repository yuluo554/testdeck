# TestDeck

> 测试结果终端工作台：一条命令把多次 run 的 JUnit XML 归一到本地 SQLite，用三栏 TUI 回答"谁在抖、谁在变慢、这次是不是新坏"。

CI 页面只回答"这一次 run 红不红"。跨 run 的问题——同一用例在多次 run 之间 pass/fail 交替、p50/p95 悄悄抬升、这次失败是不是上一轮没有的——需要**多次 run 的本地历史**。TestDeck 把 `**/junit*.xml`、`target/surefire-reports/*.xml`、`build/test-results/**` 以及 `gh run download` 下来的目录统一入库，然后在终端里用键盘逐条下钻。

- **纯本地**：无服务器、无账号、无网络调用、无遥测；数据只写本机 SQLite。
- **多框架**：pytest / gotestsum / Playwright / Maven Surefire 的 JUnit XML 用同一套解析。
- **确定性**：flaky 分数、p50/p95、回归比值都是算术，可被 CI 门禁复算。
- **终端唯一形态**：Textual 三栏（树 / 失败原文 / sparkline），`F` 矩阵、`S` 瀑布、`D` diff。

## 状态

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 方法论装订 + plan/00–06 + 可运行骨架 | ✅ 已完成（2026-10-18） |
| M1 | 三框架真实产物（真跑）+ 合成语料 + 真值台账 + 大文件基准 | ✅ 已完成（2026-10-19） |
| M2 | 解析落库（`iterparse` + 四表 + upsert + ingest 摘要） | ✅ 已完成（2026-10-19） |
| M3 | 三栏视图（失败优先树 / summary / failure 原文 / sparkline） | ✅ 已完成（2026-10-19） |
| M4 | flaky 矩阵与分型 + 两次 run diff | ✅ 已完成（2026-10-19） |
| M5 | 慢测试与回归 + 导出与门禁 + 录屏 | ✅ 已完成（2026-10-19） |
| M6 | 脱敏发布（tag + Release + 发布留档） | ⬜ 待 M6 |

**M5 现状（最新）**：`S` 视图每条用例带 `slow.py` 的 **p50 / p95 / 回归三态标记**
（`reg=yes/no/?`）与瀑布条；summary 六个字段全部有值（`slow` = 本 run 达到 `slow_ms` 的用例数）。
`testdeck export --format md|json` 已实装，`--fail-on flaky|new-failures|regressions` 供 CI 门禁；
**两次导出逐字节一致**（不写生成时刻、不含 `ingested_at` / 绝对路径）：

```bash
py -3.12 bench/bench_slow.py                 # p50/p95 + 回归边界对账（22 锚点 + 50 样本 + 全语料）
py -3.12 bench/bench_export.py               # 导出字段一致 + 逐字节一致 + 门禁退出码
py -3.12 bench/run_all.py                    # 四套件 43 项检查全绿，exit 0
py -3.12 bench/run_all.py --probe            # 探活：逐套件注入全被报出（exit 0）
py -3.12 -m testdeck export --db /tmp/demo.db --format md             # 导出 md 到 stdout
py -3.12 -m testdeck export --db /tmp/demo.db --fail-on regressions   # 命中回归 → exit 1
```

`docs/demo/demo.gif` 是 TUI 的实际渲染录屏（8 帧 / 24.0s），由
`py -3.12 tools/make-demo-gif.py` 一条命令可复跑；口径见 `docs/demo/README.md`。

**M4**：`F` 矩阵每行带四类分型（`stable`/`flaky`/`broken`/`watch`）与 `flaky_score`，
行序按 `flaky_score` 降序；`D` 视图把两次 run 的用例级 diff 分成**新增失败 / 修复 / 仍失败**
三类（`diff.py`）。恒失败不进 flaky 是独立断言：

```bash
py -3.12 bench/bench_flaky.py                # 分型逐值对账（22 锚点 + 50 样本 + 全语料）
```

**M3**：`testdeck tui` 已实装——Textual 三栏（失败优先树 / summary / failure 原文 /
sparkline），`F`/`S`/`D` 三个视图**接真实查询**。窄终端自动单栏、`NO_COLOR` 颜色退化：

```bash
py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db /tmp/demo.db
py -3.12 -m testdeck tui --db /tmp/demo.db      # 需真终端；纯键盘操作
py -3.12 -m pytest tests/test_tui_pilot.py -q   # 无头键盘全流程（CI 可跑）
```

**M2**：`testdeck ingest` 已实装——流式 `iterparse` 解析、框架识别、四表
`upsert`、摘要（机读行 + 人读行）都在跑，重复 ingest 四表行数不变：

```bash
py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db /tmp/demo.db
# ingest: files=3 runs=1 cases=18 occurrences=18 skipped=0 framework=gotestsum,playwright,pytest
```

```bash
py -3.12 data/synth/gen_runs.py --check       # 真值台账位级一致（exit 0）
```

`bench/run_all.py` 不带参数时会跑全部**登记**套件（M5 起四套件全就绪，exit 0）。
**退出码 4 已全面退役**：`ingest` 于 M2、`tui` 于 M3、`export` 于 M5——
`cli.py` 里不再有返回 4 的分支（常量保留在 `exit_codes.py`，历史留档要能读）。

## 快速开始

```bash
pip install -e ".[dev]"
testdeck selftest
pytest -q
```

本机（Windows，`python` 是商店占位符）用：

```bash
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m testdeck selftest
py -3.12 -m pytest -q
```

两条通路（裸 `testdeck` 与 `python -m testdeck`）都必须在干净环境里可用——
只验其中一条会漏掉安装面缺陷。

## 命令（M0 已定参数面）

| 命令 | 说明 | 退出码 |
| --- | --- | --- |
| `testdeck selftest` | 自检键位 / 退出码 / 规则包 / 零网络 / 分层 | 0 / 1 |
| `testdeck ingest <paths...>` | 扫描并归一 JUnit XML（`--glob` 可重复、`--dry-run` 零副作用、`--db` 覆盖并回显） | 0 / 2 / 3 |
| `testdeck tui` | 三栏工作台；`j/k/g/G` 移动、`Enter` 展开/详情、`F`/`S`/`D` 切视图、`/` 搜索、`?` 帮助、`Esc`/`q` 返回/退出 | 0 / 2 / 3 |
| `testdeck export --format md\|json` | 导出报告到 stdout；`--fail-on flaky\|new-failures\|regressions` 供 CI 门禁（命中 → 1） | 0 / 1 / 2 / 3 |

退出码语义：`0` 达标 / `1` 门禁触发 / `2` 用法错误 / `3` 依赖缺失或库不可读。
骨架期的 `4`（尚未实现）**逐命令退役**：`ingest` 于 M2、`tui` 于 M3、`export` 于 M5
全部退役——`cli.py` 里已无返回 4 的分支（常量保留，见 `plan/05` §二）。

`tui` 的降级：终端宽度 < 80 列自动单栏（右栏改为按 `Enter` 进入的详情页）；
`NO_COLOR` / `TERM=dumb` / 无真彩色 → 保留结构、颜色退化。库不存在 / 没有 run →
退出码 3 并提示先跑 `testdeck ingest`。

## 方法论装订

本仓库遵循 `ai-tool-project-sprint` 方法论。**任何新对话的第一件事**：

```bash
py -3.12 tools/check-sprint-layout.py     # 布局门（CI 里也有一条）
```

## 定位与边界（如实说明）

赛道有真实工具，但形态不同：

| 能力 | 现有工具（基准日 2026-10-17） | 本项目位置 |
| --- | --- | --- |
| JUnit XML 报告 | allure2（5564★）等 Web/Java 报告体系 | 终端内即时下钻，不做报告站点 |
| 报告格式统一 | ctrf（100★）JSON 标准 | 首期只消费 JUnit XML |
| flaky 列表 | FlakeHarbor（2★）、kare（1★）纯 CLI | 增加四态矩阵、四类分型与三栏交互 |
| 跨 run 历史 | 多为 CI 平台内置、按 run 隔离 | **本地归档 + 键盘下钻**是本项目增量 |

本题**不是**"第一个 JUnit 查看器"，也不是"第一个 flaky 检测器"；检索计数只作软论据（检索式与基准日见 `data/README.md`）。

**不做**：不执行测试、不对接 CI API、不算覆盖率、不存云端、不做"AI 分析失败原因"、不做 Web/GUI 形态。

## 文档

- `plan/01-题目文档.md` — 题目定稿（需求原话、检索快照、模块与验收）
- `plan/00-README总览.md` — 索引、决策记录、承诺-证据台账、里程碑
- `plan/02`–`plan/06` — 架构 / 模块详设 / 数据计划 / 里程碑与发布 / 交付对标
- `data/README.md` — 查证记录、数据源可获取性、合成数据与**数值口径唯一真相源**
- `AGENTS.md` — 方法论锚点与布局门命令

## License

MIT
