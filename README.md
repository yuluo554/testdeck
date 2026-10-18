# TestDeck

> 测试结果终端工作台：一条命令把多次 run 的 JUnit XML 归一到本地 SQLite，用三栏 TUI 回答"谁在抖、谁在变慢、这次是不是新坏"。

CI 页面只回答"这一次 run 红不红"。跨 run 的问题——同一用例在多次 run 之间 pass/fail 交替、p50/p95 悄悄抬升、这次失败是不是上一轮没有的——需要**多次 run 的本地历史**。TestDeck 把 `**/junit*.xml`、`target/surefire-reports/*.xml`、`build/test-results/**` 以及 `gh run download` 下来的目录统一入库，然后在终端里用键盘逐条下钻。

- **纯本地**：无服务器、无账号、无网络调用、无遥测；数据只写本机 SQLite。
- **多框架**：pytest / gotestsum / Playwright / Maven Surefire 的 JUnit XML 用同一套解析。
- **确定性**：flaky 分数、p50/p95、回归比值都是算术，可被 CI 门禁复算。
- **终端唯一形态**：Textual 三栏（树 / 失败原文 / sparkline），`F` 矩阵、`S` 瀑布、`D` diff。

## 状态

**M0 骨架期**：CLI 参数面、键位表、退出码语义已定；`ingest` / `tui` / `export` 尚未实现（返回 `4`）。
后续里程碑见 `plan/00-README总览.md`。

```bash
pip install -e ".[dev]"
testdeck selftest
pytest -q
```

## 定位与边界（如实说明）

赛道有真实工具，但形态不同：

| 能力 | 现有工具（基准日 2026-10-17） | 本项目位置 |
|---|---|---|
| JUnit XML 报告 | allure2（5564★）等 Web/Java 报告体系 | 终端内即时下钻，不做报告站点 |
| 报告格式统一 | ctrf（100★）JSON 标准 | 首期只消费 JUnit XML |
| flaky 列表 | FlakeHarbor（2★）、kare（1★）纯 CLI | 增加四态矩阵、四类分型与三栏交互 |
| 跨 run 历史 | 多为 CI 平台内置、按 run 隔离 | **本地归档 + 键盘下钻**是本项目增量 |

本题**不是**"第一个 JUnit 查看器"，也不是"第一个 flaky 检测器"；检索计数只作软论据（检索式与基准日见 `data/README.md`）。

**不做**：不执行测试、不对接 CI API、不算覆盖率、不存云端、不做"AI 分析失败原因"、不做 Web/GUI 形态。

## 文档

- `plan/01-题目文档.md` — 题目定稿（需求原话、检索快照、模块与验收）
- `plan/00-README总览.md` — 索引、决策记录、承诺-证据台账、里程碑
- `data/README.md` — 查证记录、数据源可获取性、合成数据与**数值口径唯一真相源**
