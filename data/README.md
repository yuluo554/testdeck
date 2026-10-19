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
| --- | --- | --- | --- |
| pytest JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/pytest/`） | `pytest --junitxml=...` | 无阻断；用仓库内最小测试集产出，版本与命令写入 fixture `README.md` |
| Go gotestsum JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/gotestsum/`） | `gotestsum --junitfile=...` | 无阻断；**2026-10-19 复测后改为真跑产出**（Go 1.23.4 经 `dl.google.com`、gotestsum v1.12.0 经 `goproxy.cn`）。产物入库后不再依赖工具链 |
| Playwright JUnit XML | ✅ 已获取（M1 落 `bench/fixtures/playwright/`） | Playwright `reporter: [['junit', {...}]]` | 无阻断；**2026-10-19 复测后改为真跑产出**（`@playwright/test` 1.48.2 经 `registry.npmmirror.com`、Chromium 130 经 `cdn.npmmirror.com`）。产物入库后不再依赖 |
| Maven Surefire XML | ⬜ 待获取（扩展） | `target/surefire-reports/*.xml` | 需 JDK + Maven；首期只做路径识别，不做验收对账 |
| `gh run download` 目录 | ⬜ 可选 | `gh run download <id> -D <dir>` | 需 gh 登录；**非必需**。缺失时 `ingest --from-gh` 必须 exit 3，不得当成"零结果" |
| 外部数据集 | ❌ 不使用 | — | 本题不依赖任何外部数据服务；所有验收语料随仓或由生成器产出 |

> **口径更新（2026-10-18 → 2026-10-19）**：2026-10-18 实测"本机无 Go、Playwright 未安装"，
> 当时计划 D2/D3 用**预置产物**。2026-10-19 复测发现三个工具链都能经可达镜像取得，
> 于是**改为真跑产出**——三份产物的 `produced_by.source` 均写"本机真实运行"。
> 依据 AGENTS.md 的复测纪律，旧结论不再引用。

**结论**：无外部数据依赖。三份真实产物在 M1 一次性产出并入库，且由
`bench/fixtures/regen_fixtures.py` 一条命令可重跑、可复核；合成语料由
`data/synth/gen_runs.py` 程序化生成，不入仓（体积原因），但生成器与真值
`expect.json` 入库。

## 三、合成数据纪律

1. **假仓库名与假分支白名单**：合成 run 的 `branch` 只允许 `main`、`feature/synth-*`、`fix/synth-*`；仓库名只允许 `demo-app`、`demo-lib`、`demo-web`。不得出现任何真实组织名、真实用户名、真实域名。
2. **假 commit 与假 run id**：commit 用 `0000000` 起的递增十六进制占位（如 `5ynth0001` 不合法，统一用 `0000000000000000000000000000000000000001` 起的 40 位全数字占位串）；`ci_run_id` 用 `1000000000` 起的递增整数。**不得**照抄任何真实 CI 的 run id 或 commit。
3. **植入真值**：生成器在写语料的同时写 `expect.json`，包含每个用例的预期分型（stable / flaky / broken / watch）、预期 flaky 分数、预期 p50/p95、预期回归标记。基准脚本只读 `expect.json` 对账，不从生成逻辑反推。
4. **模式覆盖下限**（覆盖度口径，不写具体条数）：每个分型至少覆盖一个样本；`missing` 至少覆盖一个用例；`skip` 至少覆盖一个用例；回归判定覆盖"恰好 1.2x / 略低 / 略高"与"恰好 +200ms / 略低 / 略高"六种边界；flaky 样本必须包含 transitions 从 1 到 5 的梯度。
5. **可重放**：生成器接受 `--seed`，同 seed 输出逐字节一致；`--check` 只校验不写盘。
6. **规模**：合成主语料为 200 run × 5000 用例（生成器参数可调），大文件基准另生成单文件 5 万用例；两者都不入仓。

### 3.1 实际落地形态（M1 定，参数可调）

| 项 | 落地值 | 说明 |
| --- | --- | --- |
| 生成命令 | `py -3.12 data/synth/gen_runs.py --seed 42 --runs 200 --cases 5000 --sample-size 50` | 一条命令同时写语料与真值 |
| 语料（D5，不入仓） | 200 run × 5000 用例，按种子确定生成 | 体积原因不入仓；同 seed 可位级重放 |
| 真值（D7，入仓） | `data/synth/expect.json`（约 0.43 MB） | 22 条锚点 + 50 条确定性样本（各带完整输入侧与期望侧）+ 全语料汇总 |
| 大文件（D6，不入仓） | `--big 50000` → `data/synth/big.xml`（约 3.6 MB） | 单文件 5 万用例，供 ingest 性能门 |
| 样本条数 | `--sample-size 50` | 入仓台账只存切片：完整输入侧（每条 200 长）体积敏感，5000 条会把台账推到 MB 级 |

**为什么"真值入仓"不等于"整份语料入仓"**：`expect.json` 存的是
**锚点 + 确定性样本 + 汇总**；锚点是逐一覆盖 DoD 要求的手工样本（四类分型 /
missing / skip / transitions 1..5 / 回归边界），样本是从语料里确定性抽取的切片。
全语料本身由同一条命令按种子重建，并由 `--check` 位级比对。

## 四、数值口径（唯一真相源）

> 代码、测试、文档、导出必须引用同一处定义；本节是唯一真相源。任何地方出现第二套阈值即为缺陷。

| 口径 | 定义 | 落地位置（M0 起） |
|---|---|---|
| run 身份 | `(branch, commit, ci_run_id)` 三元组 | `src/testdeck/identity.py` |
| run 身份**来源** | 只从 XML 声明的元数据读（根/`testsuite` 的 `branch` / `commit[_sha]` / `ci_run_id` / `timestamp`）；读不到写**空串**，并计入摘要 `degraded` | `src/testdeck/junit.py` |
| run 分组 | 三元组相同的产物归同一个 run；**没声明身份的产物因此全部落进同一个"未标注 run"**（K26）。`runs.framework` = 该 run 覆盖到的框架集合（字典序逗号连接），`runs.source_path` = 该 run 按展示路径字典序的首个产物 | `src/testdeck/ingest.py` |
| 用例身份 | `(suite_name, classname, name)`；参数化用例保留完整参数串 | 同上 |
| 框架识别 | `<testsuite>`/根 `name` → `<properties>` 键名（`go.version`）→ 文件名；判不出写 `unknown` | `src/testdeck/framework.py` |
| 坏文件原因码 | `bad_xml` / `bad_encoding` / `no_testsuite` / `unreadable`（逐文件记录，不中断整批） | `src/testdeck/junit.py` |
| 单项降级码 | `bad_time` / `missing_name` / `started_at_missing` / `bad_commit`（文件照常入库，该项按缺失处理） | 同上 |
| 状态枚举 | `pass` / `fail` / `skip` / `missing`（四态）；`failure` 与 `error` 都归 `fail` 态，但**元素重数分桶** | `src/testdeck/model.py` / `junit.py` |
| 耗时单位 | 整数毫秒；XML 十进制秒 → 毫秒，ROUND_HALF_UP；**缺失写 NULL 不是 0** | `src/testdeck/model.py` |
| `fail_rate` | `fails / (passes + fails)`；skip 与 missing 不进分母；`n == 0`（全 skip/missing）时**无定义**（记 `None`，不是 `0`） | `src/testdeck/flaky.py` |
| `transitions` | 相邻两次 run 的状态均为 pass/fail 且不同，计 1；skip/missing 不制造 transition | 同上 |
| `flaky_score` | `transitions / (n - 1)`，`n` = 参与计算的 pass/fail 次数；`n < 2` → 0 | 同上 |
| 分型 | `fail_rate == 1` → broken；`== 0` → stable；`0.05 ≤ fail_rate ≤ 0.95` 且 `transitions ≥ 3` → flaky；其余 → watch | `src/testdeck/rules/flaky.json` + `src/testdeck/flaky.py` |
| 分型降级①（窗口样本不足） | 窗口 run 数 `< min_runs_for_flaky`（=2） → 一律 `watch`，**不得输出 flaky** | `rules/flaky.json` + `flaky.py` |
| 分型降级②（零计数样本） | `n == 0`（该用例在所有 run 都是 skip/missing）时 `fail_rate` 是 0/0、**无定义**（记为"无定义"而非数值 `0`） → 一律 `watch`。**不得判成 stable**——"一次都没真正跑过"不构成"稳定"证据 | 同上 |
| 分位数 | 线性插值：索引 `(n-1) * p`，取 floor/ceil 两点按小数部分插值；缺失耗时（`None`）不进样本、不补 0 | `src/testdeck/slow.py`（**M5 已落地**） |
| 百分比值渲染 | `fail_rate` / `flaky_score` / p50 / p95 一律以**精确有理数**运算（`Fraction`），渲染为**终止十进制串**；不终止时用 `p/q`（如 `"1/3"`）。禁用 `float`——浮点会让"恰好等于阈值"的样本随机落侧 | `flaky.py` / `slow.py` / `bench/refimpl.py` |
| 回归判定 | `curr_p50 / base_p50 ≥ 1.2` **且** `curr_p50 - base_p50 ≥ 200ms`（两处边界均计入，`>=`） | `src/testdeck/rules/slow.json` + `src/testdeck/slow.py`（**M5 已落地**） |
| 回归窗口 | `base` = 窗口前段样本的 p50、`curr` = 窗口后段样本的 p50；切分点 `split` 由**输入侧**给出（合成台账里显式存 `regression_split`），引擎不得自行发明切分 | `slow.py` |
| 回归不可判 | `base_p50 == 0` → `undefined_base`；任一侧无样本 → `missing_window`。两者都**不判回归、也不谎报"无回归"**（返回 `None`，不是 `False`） | 同上 |
| 慢测试降级 | 总样本 0 或回归窗口任一侧无样本 → `insufficient_history`；总样本恰 1 → `single_sample`（p50 == p95） | `src/testdeck/slow.py` |
| 瀑布条宽度 | `round(time_ms / max_time_ms * width)`，**整数运算**（余数加倍与除数比较）；`max_time_ms == 0` → 全宽 0 | 同上 |
| summary 的 `slow` | 本 run 里**有耗时声明且 ≥ `slow_ms`** 的用例数；`None`（没声明耗时）不算慢 | `src/testdeck/slow.py:is_slow` + `queries.slow_summary_count` |
| 导出格式与门禁取值 | `formats` / `fail_on` / `json_indent` / `json_ensure_ascii` / `write_generated_at` 全部取自规则包 | `src/testdeck/rules/view.json` + `report_model.py` |
| `--fail-on` 命中条件 | `flaky`：分型 flaky 数 >0；`new-failures`：相对 base run 新增失败数 >0；`regressions`：回归清单非空。**判定只读模型**，不重新查库 | `report_model.gate_hits` + `export.py` |
| 慢测试阈值 | `slow_ms` 默认值写 `src/testdeck/rules/slow.json`，不在代码里另写 | 同上 |
| sparkline 窗口 | 最近 20 次 run（可配） | `src/testdeck/rules/view.json` |
| 真值台账 | `expect.json` 只存**输入侧**（`history` / `timings_ms` / `regression_split` / `runs`）与**期望侧**（分型 / `flaky_score` / p50 / p95 / 回归标记）；**禁存 `observed`** | `data/synth/gen_runs.py` + `bench/refimpl.py` |
| 键位表 | `j/k/g/G/Enter/F/S/D//e/?` + `Esc`/`q`（`Esc`=back、`q`=quit 也是表成员），唯一来源 | `src/testdeck/keys.py` |
| 导出字段序 | 由 `report_model.py` 的字段声明顺序决定，md 列与 JSON 键共用（`case_id` 与 `ingested_at` 都不进报表） | `src/testdeck/report_model.py` |
| 失败优先排序 | 同父节点下 `fail_count > 0` 的子树在前；同组内 suite 按 `suite_id`（XML 出现序）升序，class/name 按字典序。**单点在 `queries.fail_first_key`**，树/矩阵/瀑布共用（K35） | `src/testdeck/queries.py` |
| summary 字段序 | `total / fail / skip / flaky / broken / slow`，键序取规则包；`flaky`/`broken`/`slow` 在各自里程碑前恒为 `None`（不猜，K37） | `src/testdeck/rules/view.json` + `queries.py` |
| 单栏门槛 | 终端宽度 `< min_width_single_column`（=80，判据是 `<`）→ 单栏 | `src/testdeck/rules/view.json` + `tui/view.py` |
| 颜色退化条件 | `NO_COLOR`（**按有没有设置判**，`NO_COLOR=""` 也算）/ `TERM=dumb` / 非 tty / `COLORTERM` 非 truecolor\|24bit → 保留结构、只去色（K39/K40） | `src/testdeck/tui/view.py` |
| sparkline 口径 | pass=1 / fail=0；`skip`/`missing` **不绘制**（与 flaky 分母同源） | `model.COUNTED_STATUSES` + `tui/view.py` |
| 退出码 | `0` 达标 / `1` 门禁触发 / `2` 用法错误 / `3` 依赖缺失或库不可读；`4` 仅骨架期表示"尚未实现"，**逐命令退役**（`ingest` 于 M2、`tui` 于 M3、**`export` 于 M5** 全部退役；常量保留） | `src/testdeck/exit_codes.py` |
| `tui` 的库不可用 | 库不存在 / 无 run / `--run` 不存在 → 一律 exit 3（空库 ≠ "没有失败"，K45） | `src/testdeck/tui/app.py` |
| 数据库路径 | `$XDG_DATA_HOME/testdeck/testdeck.db`，未设置时 `~/.local/share/testdeck/testdeck.db` | `src/testdeck/db.py` |
| 库打开方式 | 写侧 `db.connect`（确保 schema）/ 读侧 `db.open_existing`（不建目录不建表；不存在即报错）——**读侧不得用 `connect`** | `src/testdeck/db.py` |
| 库 schema 版本 | `db.SCHEMA_VERSION`（M2 = 2；版本不符时报错并提示删库重建，不静默复用） | `src/testdeck/db.py` |

**跨平台口径**：Windows 上 `XDG_DATA_HOME` 通常未设置，回落到 `%USERPROFILE%\.local\share\testdeck\`；数据库路径可由 `--db` 覆盖，覆盖值必须在 `ingest` 摘要与 `export` 输出中回显，避免"写到了别处却不知道"。

## 五、诚实性声明

- 本文所有星数、total_count、HN 原话均按基准日与实测窗口记录；**未做**长期监控，数值会漂移。
- 本题**不是**"第一个 JUnit 查看器"，也**不是**"第一个 flaky 检测器"；增量主张限定在 §1.2 末段的组合缝隙。
- 合成语料全部为程序生成的假数据，不含任何真实项目的测试输出。
- 三份 fixture 是**真跑工具产出的真实产物**（2026-10-19），入库前只做过一道确定性脱敏
  （删 `hostname` 属性 + 绝对路径改仓库内相对路径），规则与复核命令写在
  `bench/fixtures/*/README.md`；`bench/fixtures/scan_leaks.py` 是可跑的守门。
- 本文提到的工具链可达性都是**当日实测**结论（镜像会失效）；
  下一棒引用前先复测（AGENTS.md 的复测纪律）。
- M2 的解析/落库结论来自**实跑**：`bench/run_all.py --suites ingest` 用生产解析器
  （`src/testdeck/junit.py`）对三份真跑产物逐项对账，并与基准侧独立重数实现互校；
  入库幂等、坏文件原因码、dry-run 零副作用都由 `tests/` 里的临时库/临时目录实测。
- M3 的三栏视图结论来自**实跑的无头 Pilot**（`tests/test_tui_pilot.py`，13 例）：
  键盘全流程、`F/S/D` 三视图取真实查询、两条降级（窄终端/`NO_COLOR`）都在其中；
  summary 的每个数字另有"与直出 SQL 逐项相等"的独立断言（`tests/test_queries.py`）。
  **真终端（字体/尺寸/ConPTY）的表现本轮未验**，登记为 `plan/05` §五 的未验证项与
  `plan/06` 的 G6。
- 本节新增的 M3 口径（失败优先单点、summary 键序、单栏门槛、颜色退化条件、sparkline
  口径、读侧 `open_existing`）都有对应测试；**改动前先看 `plan/HANDOFF-M4.md` §3 的 K 表**。
- M4 的分型与 diff 结论来自**实跑**：`bench/bench_flaky.py` 用生产 `flaky.py` 对台账
  22 锚点 + 50 样本的 7 个字段逐值对账，并与参照实现（阈值取自台账 `rules_snapshot`）
  互校，再重建全语料 5000 条核对分型计数；`broken ∩ flaky == ∅` 是**独立断言**
  （两份集合求交，不靠分类函数内部顺序自证）。diff 的三类由 `tests/test_diff.py`
  逐类对账（含 `fail→skip`/`fail→缺` 不判"修复"的边界）。
- M5 的分位数/回归/导出结论来自**实跑**：`bench/bench_slow.py` 用生产 `slow.py` 对台账
  22 锚点 + 50 样本的 5 个字段（p50/p95/base/curr/regression）逐值对账，并与参照实现
  （阈值取自台账 `rules_snapshot`）互校，再重建全语料 5000 条核对回归三态计数；
  回归边界六种（ratio/delta 恰好/略低/略高）**True/False/None 三态齐全**，
  缺失耗时"不补 0"与"不可判返回 `None`"两条口径各有可证伪的基准检查项。
- M5 的导出结论来自**实跑**：`bench/bench_export.py` 用确定性合成模型对账
  （导出面全是纯函数，不碰库），`tests/test_export_determinism.py` 双跑 `cmp` 断言
  两次导出逐字节一致；`--fail-on` 三种值的退出码（命中 1 / 未命中 0 / 未知值 2 /
  库不可用 3）由 `tests/test_export.py` 与基准两侧钉住，且**门禁只读模型**——
  篡改模型结论随之变（`export/gate_reads_model_only`），这条防的是"门禁另查一遍库"。
- **M5 的录屏口径（如实写）**：`docs/demo/demo.gif` 是 **Textual 渲染输出**
  （`App.export_screenshot()` 的 SVG）经 Pillow 栅格化拼成，**不是真终端字节流录制**——
  本机 Windows 无 `pty`/`termios`，`winpty` 在非 tty 下断言失败，`asciinema`/`agg`/`pyte`
  都不在且本轮不下载任何工具。它证明的是"TUI 在 100×30 下真的渲染出这些内容"，
  **不**证明真终端（字体/像素级/ConPTY）表现——后者仍是 `plan/05` §五 的未验证项与
  `plan/06` 的 G6（**未关闭**）。演示动图里的第二个 run 是**演示脚手架**（只写
  `bench/.tmp/`，不入仓），用来让 `D`/`S` 演示得出"新增失败/修复/回归"。
- 本节新增的 M5 口径（分位数插值、回归三态、慢测试两条降级、瀑布条整数运算、
  summary 的 `slow`、导出字段序与门禁取值）都有对应测试；**改动前先看
  `plan/HANDOFF-M6.md` §3 的 K 表**。
- **M4 修正的一处口径（引擎与真值同源修正）**：参照实现原先把零计数样本的 `fail_rate`
  渲染成 `"0"`，与本节 §四「零计数样本 `fail_rate` 无定义」冲突（`"0"` 与 stable 撞车）。
  已改参照实现（记 `None`）并重生成 `expect.json`；生产 `flaky.py` 本就按口径记无定义。
