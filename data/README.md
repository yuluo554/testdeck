# data/README — 依据查证、数据源可获取性与合成数据纪律

> 基准日：**2026-10-17**（题面定稿）。GitHub 检索实测窗口：**2026-10-18 10:33–10:50 UTC**（检索计数为当时快照，之后会漂移；本文所有星数与 total_count 均按该窗口记录）。
> 三态口径：✅ 已核对（可直连/可复现）/ ⬜ 待核对或软论据（检索式与基准日可回溯，但不作硬锚点）/ ❌ 不可获取（不作底座）。

## 一、依据查证记录

### 1.1 需求侧原话（✅ 原话直连）

| # | 原话 | 作者/日期 | 链接 | 用途 |
|---|---|---|---|---|
| 1 | "I maintain an OSS project with a very involved CI setup… worth having observability into which tests are flaky… takes junit.xml exports from **cargo nextest, vitest, playwright, pytest, and go test**. What do you all recommend?" | vrm，2025-09-12（Ask HN） | `https://news.ycombinator.com/item?id=45222181` | 多框架 JUnit XML 是事实标准输入；需求是跨 run 可观测性 |
| 2 | "There is really **no proper way to expose the results if you are not using Jenkins** as your main CI." | rasjani，2022-10-26 | `https://news.ycombinator.com/item?id=33341434` | 结果展示被 CI 平台绑定，缺少本地归档层 |
| 3 | "people often take flaky test way less serious then they should… written off as flaky tests" | dathinab，2026-04-20 | `https://news.ycombinator.com/item?id=47837206` | flaky 被当成噪声写掉，需要可复查的量化记录 |
| 4 | "Flaky tests are a very strong signal of a bug, somewhere. Problem is it's not always easy to tell if the bug's in the test or in the code under test." | tomjakubowski，2026-04-20 | `https://news.ycombinator.com/item?id=47839948` | 抖动与恒失败必须分开看（对应本题 broken / flaky 分型） |

> 原话按页面文本照录；省略号处为原帖行文省略，未改写语义。

### 1.2 开源检索快照（✅ 计数 / ⬜ 空白判定）

检索方式：GitHub 仓库搜索（`gh api search/repositories`），`total_count` 与头部结果按上述实测窗口记录。

| 检索式 | total_count | 头部结果 | 状态 |
|---|---|---|---|
| `junit tui` | **9** | 4★ 无关课程项目；相关仅 testlens-app/cli 2★ | ✅ 计数 |
| `junit xml viewer` | 6 | amalfra/junit-cli-report-viewer 8★ | ✅ 计数 |
| `junit xml tui` | **0** | — | ✅ 计数 / ⬜ 空白判定 |
| `test report browser tui` | **0** | — | ✅ 计数 / ⬜ 空白判定 |
| `surefire report viewer` | **0** | — | ✅ 计数 / ⬜ 空白判定 |
| `flaky test tui` | 1 | 1★ WIP | ✅ 计数 |
| `pytest report tui` | 1 | 0★ | ✅ 计数 |
| `test flakiness dashboard` | 63 | 6★ | ✅ 计数 |
| `junit history` | 80 | 头部 152★ 无关；相关 FlakeHarbor 2★、kare 1★ | ✅ 计数 |

**软论据边界（必须如实）**：检索计数只能说明"终端形态的 JUnit 工具在 GitHub 上稀少"，**不能**证明"世界上没有"。GitHub 之外的私有工具、CI 厂商内置功能（如 GitLab 的 test report 视图、Buildkite 的 test analytics）都覆盖了部分场景。本题的增量主张因此限定为：**本地 + 多 run + 键盘下钻**这一组合，不主张品类首创。

### 1.3 相邻工具（✅ 仓库页，基准日 2026-10-17）

| 项目 | 规模 | 形态 | 与本题的关系 |
|---|---|---|---|
| allure2 | **5564★** | Java/Web 报告体系，需报告服务或静态站点生成 | 形态与重量不同；本题是终端内即时下钻 |
| ctrf | **100★** | JSON 报告标准 | 解决格式统一，不含 TUI 与跨 run 库 |
| FlakeHarbor | 2★ | 纯 CLI，输出 flaky 列表 | 无交互下钻、无三栏、无慢测试瀑布 |
| kare | 1★ | 纯 CLI | 同上 |

### 1.4 技术可行性（✅）

- Playwright、pytest、Go（gotestsum）、Maven Surefire 默认都能产出 JUnit XML —— 用户零改造成本。
- 纯本地文件读取，无 root、无网络、无账号；`gh run download` 只是可选的 artifact 拉取方式。
- Textual 提供 `Tree` / `DataTable` / `Sparkline` / `Footer` 与 `Pilot` 无头测试；`textual run --dev` 可录屏。
- 风险：超大 XML（> 50MB）必须 `iterparse` 流式读取，不得整树 `parse`。

## 二、数据源可获取性记录

| 数据源 | 状态 | 获取路径 | 阻断/说明 |
|---|---|---|---|
| pytest JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/pytest/`） | `pytest --junitxml=...` | 无阻断；首期用仓库内最小测试集产出，版本与命令写入 fixture 说明 |
| Go gotestsum JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/gotestsum/`） | `gotestsum --junitfile=...` | 无阻断；需本地 Go 工具链，产物入库后不再依赖工具链 |
| Playwright JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/playwright/`） | Playwright `reporter: [['junit', {...}]]` | 无阻断；需 Node + 浏览器，产物入库后不再依赖 |
| Maven Surefire XML | ⬜ 待获取（扩展） | `target/surefire-reports/*.xml` | 需 JDK + Maven；首期只做路径识别，不做验收对账 |
| `gh run download` 目录 | ⬜ 可选 | `gh run download <id> -D <dir>` | 需 gh 登录；**非必需**。缺失时 `ingest --from-gh` 必须 exit 3，不得当成"零结果" |
| 外部数据集 | ❌ 不使用 | — | 本题不依赖任何外部数据服务；所有验收语料随仓或由生成器产出 |

**结论**：无外部数据依赖。三份真实产物在 M1 一次性产出并入库；合成语料由 `data/synth/gen_runs.py` 程序化生成，不入仓（体积原因），但生成器与真值 `expect.json` 入库。

## 三、合成数据纪律

1. **假仓库名与假分支白名单**：合成 run 的 `branch` 只允许 `main`、`feature/synth-*`、`fix/synth-*`；仓库名只允许 `demo-app`、`demo-lib`、`demo-web`。不得出现任何真实组织名、真实用户名、真实域名。
2. **假 commit 与假 run id**：commit 用 `0000000` 起的递增十六进制占位（如 `5ynth0001` 不合法，统一用 `0000000000000000000000000000000000000001` 起的 40 位全数字占位串）；`ci_run_id` 用 `1000000000` 起的递增整数。**不得**照抄任何真实 CI 的 run id 或 commit。
3. **植入真值**：生成器在写语料的同时写 `expect.json`，包含每个用例的预期分型（stable / flaky / broken / watch）、预期 flaky 分数、预期 p50/p95、预期回归标记。基准脚本只读 `expect.json` 对账，不从生成逻辑反推。
4. **模式覆盖下限**（覆盖度口径，不写具体条数）：每个分型至少覆盖一个样本；`missing` 至少覆盖一个用例；`skip` 至少覆盖一个用例；回归判定覆盖"恰好 1.2x / 略低 / 略高"与"恰好 +200ms / 略低 / 略高"六种边界；flaky 样本必须包含 transitions 从 1 到 5 的梯度。
5. **可重放**：生成器接受 `--seed`，同 seed 输出逐字节一致；`--check` 只校验不写盘。
6. **规模**：合成主语料为 200 run × 5000 用例（生成器参数可调），大文件基准另生成单文件 5 万用例；两者都不入仓。

## 四、数值口径（唯一真相源）

> 代码、测试、文档、导出必须引用同一处定义；本节是唯一真相源。任何地方出现第二套阈值即为缺陷。

| 口径 | 定义 | 落地位置（M0 起） |
|---|---|---|
| run 身份 | `(branch, commit, ci_run_id)` 三元组 | `src/testdeck/identity.py` |
| 用例身份 | `(suite_name, classname, name)`；参数化用例保留完整参数串 | 同上 |
| 状态枚举 | `pass` / `fail` / `skip` / `missing`（四态） | `src/testdeck/model.py` |
| 耗时单位 | 整数毫秒；XML 十进制秒 → 毫秒，ROUND_HALF_UP | `src/testdeck/model.py` |
| `fail_rate` | `fails / (passes + fails)`；skip 与 missing 不进分母 | `src/testdeck/flaky.py` |
| `transitions` | 相邻两次 run 的状态均为 pass/fail 且不同，计 1；skip/missing 不制造 transition | 同上 |
| `flaky_score` | `transitions / (n - 1)`，`n` = 参与计算的 pass/fail 次数 | 同上 |
| 分型 | `fail_rate == 1` → broken；`== 0` → stable；`0.05 ≤ fail_rate ≤ 0.95` 且 `transitions ≥ 3` → flaky；其余 → watch | `data/rules/flaky.json` + `src/testdeck/flaky.py` |
| 分位数 | 线性插值：索引 `(n-1) * p`，取 floor/ceil 两点按小数部分插值 | `src/testdeck/slow.py` |
| 回归判定 | `curr_p50 / base_p50 ≥ 1.2` **且** `curr_p50 - base_p50 ≥ 200ms`（边界计入） | `data/rules/slow.json` + `src/testdeck/slow.py` |
| 慢测试阈值 | `slow_ms` 默认值写 `data/rules/slow.json`，不在代码里另写 | 同上 |
| sparkline 窗口 | 最近 20 次 run（可配） | `data/rules/view.json` |
| 键位表 | `j/k/g/G/Enter/F/S/D//e/?`，唯一来源 | `src/testdeck/keys.py` |
| 导出字段序 | 由 `report_model.py` 的字段声明顺序决定，md 列与 JSON 键共用 | `src/testdeck/report_model.py` |
| 退出码 | `0` 达标 / `1` 门禁触发 / `2` 用法错误 / `3` 依赖缺失或库不可读；`4` 仅骨架期表示"尚未实现"，M2 起退役 | `src/testdeck/exit_codes.py` |
| 数据库路径 | `$XDG_DATA_HOME/testdeck/testdeck.db`，未设置时 `~/.local/share/testdeck/testdeck.db` | `src/testdeck/db.py` |

**跨平台口径**：Windows 上 `XDG_DATA_HOME` 通常未设置，回落到 `%USERPROFILE%\.local\share\testdeck\`；数据库路径可由 `--db` 覆盖，覆盖值必须在 `ingest` 摘要与 `export` 输出中回显，避免"写到了别处却不知道"。

## 五、诚实性声明

- 本文所有星数、total_count、HN 原话均按基准日与实测窗口记录；**未做**长期监控，数值会漂移。
- 本题**不是**"第一个 JUnit 查看器"，也**不是**"第一个 flaky 检测器"；增量主张限定在 §1.2 末段的组合缝隙。
- 合成语料全部为程序生成的假数据，不含任何真实项目的测试输出。
