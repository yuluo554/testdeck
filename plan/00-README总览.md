# 00 · README 总览 — 10-19-testdeck（测试结果终端工作台）

> 方法论：`ai-tool-project-sprint`（装订 2026-10-18）｜布局门：`py -3.12 tools/check-sprint-layout.py`｜续接对话第一件事 = 跑它

- 性质：不参赛项目题 · 发布 GitHub **公开仓库** · 署名 yuluo554
- 交付形态：**唯一形态 = 纯本地终端 TUI（Python + Textual）**；无服务器、无 GPU、无网络调用、无账号。
- 定位宣言："一条命令扫本地 `**/junit*.xml`、`target/surefire-reports/`、`gh run download` 目录，把上千次 run 归一到本地 SQLite；三栏 TUI：左侧 suite→class→test 树、右侧 failure 原文与历史 sparkline，`F` 切 flaky 矩阵、`S` 切慢测试瀑布、`D` 做两次 run 的用例级 diff。CI 只给一次 run 的红绿，跨 run 的'谁在抖、谁在变慢、这次是不是新坏'无人本地归档。"
- 版本史：v1 2026-10-17（题面定稿，查证基准日 2026-10-17；GitHub 检索实测窗口 2026-10-18 10:33–10:50 UTC）。
- 下一棒：**sprint M1（数据先行）**——先造三框架真实产物与合成语料，再写解析与落库。

## 一、文档索引表

| 文档 | 内容 | 状态 |
|---|---|---|
| plan/00-README总览.md | 本文档：索引 / 决策记录 / 承诺-证据台账 / 里程碑 | ✅ v1 |
| plan/01-题目文档.md | 十段式题目定稿（含需求原话、检索快照、招牌动词表、风险与边界） | ✅ v1 |
| plan/02-架构与技术选型.md | 分层架构、CLI 契约、退出码、数据库 schema、渲染与查询分离 | ✅ v1（M0） |
| plan/03-模块详设.md | 五个模块的输入/输出/实现/降级/验收，编排与数据流 | ✅ v1（M0） |
| plan/04-数据计划.md | 三框架真实产物清单、合成语料生成器、真值台账结构、基准口径 | ✅ v1（M0） |
| plan/05-里程碑与发布.md | 逐里程碑 DoD、退出码退役表、发布流程、状态列 | ✅ v1（M0） |
| plan/06-交付对标与决策.md | 提交材料对标、评分对标、形态自查表、待定决策、开放项 | ✅ v1（M0） |
| plan/HANDOFF-M1.md | M1 续接交接单（六节） | ✅ M0 收尾落盘 |
| plan/RELEASE-M6.md | 发布留档（tag 时点事实 / tag 后追加事实分栏） | ⬜ 待 M6 |
| data/README.md | 依据查证记录 + 数据源可获取性 + 合成数据与数值口径纪律 | ✅ v1 |
| data/synth/ | 合成 run 语料（生成器 + `expect.json` 真值） | ⬜ 待 M1 |
| bench/ | 四套基准（ingest / flaky / slow / export）与统一入口 | ⬜ 待 M1–M5 |
| docs/demo/demo.gif | TUI 实际运行录屏（三栏 + `F` + `S` + `D`） | ⬜ 待 M5 |
| pyproject.toml / src/testdeck/ / tests/ | 可安装骨架：`testdeck selftest`、键位表、退出码语义、规则包、零网络/分层守门 | ✅ M0（功能待 M2–M5） |
| tools/check-sprint-layout.py / AGENTS.md | 方法论装订：布局门 + 仓库锚点 | ✅ M0 |
| .gitignore / .gitattributes / LICENSE | 运行时产物不入仓；行尾归一；MIT | ✅ M0 |

## 二、决策记录表

> 本表同时登记已定案决策与**弃选项**（含弃选理由），后续里程碑不再重复论证。

| 日期 | 决策 | 结论与理由 |
|---|---|---|
| 2026-10-17 | **形态定案：终端 TUI（Textual），唯一形态** | 跨 run 下钻是键盘密集型动作，三栏同屏比"打开浏览器看报告"快一个数量级；Textual 的 Tree/DataTable/Sparkline/Footer 都是现成控件，`Pilot` 可做无头键盘测试，`textual run --dev` 便于录屏。不设 Web/GUI 备选形态，避免"任选其一"留空壳后门。 |
| 2026-10-17 | **存储定案：单文件 SQLite（`~/.local/share/testdeck/testdeck.db`）** | 上千次 run 的 occurrence 矩阵需要按 run 切片与聚合；SQLite 单文件免服务、可备份、可删除重建。JSON 文件在跨 run 聚合上会退化为全量加载。 |
| 2026-10-17 | **输入定案：JUnit XML 家族为唯一首期输入** | pytest / gotestsum / Playwright / Maven Surefire 默认都能产 JUnit XML，用户零改造成本；TAP/CTRF/Allure 原生格式留扩展项，避免首期解析器数量失控。 |
| 2026-10-17 | **分型定案：flaky / broken / watch / stable 四类** | 把"恒失败"从 flaky 列表里剔除，是对 HN 47839948 那条"抖动与恒失败要分开看"的直接回应；`watch` 兜底避免"要么 flaky 要么稳定"的二元误判。 |
| 2026-10-17 | **确定性定案：所有结论为算术，不引入模型** | flaky 分数、p50/p95、回归比值都必须能被 CI 门禁复算；任何"AI 分析失败原因"都会让 `--fail-on` 失去可解释性。 |
| 2026-10-17 | **弃：HAR 终端查看器** | Chrome / Firefox DevTools 已免费覆盖同一场景（请求瀑布、时序、响应体），终端形态的增量只剩"不离开键盘"，不足以撑起一个项目；且 HAR 动辄数百 MB，流式解析与大文件交互会吃掉首期预算。 |
| 2026-10-17 | **弃：Postgres 迁移锁模拟** | 规则集已被 squawk（1226★）、strong_migrations（4459★）、pgroll（6605★）占住；且"这次迁移会不会锁表"的结论高度依赖目标库版本、数据量、索引状态，无法在纯本地给出确定性真值。 |
| 2026-10-17 | **弃：SSH 信任面审计** | 单机场景价值窄（配置项数量有限），多机场景需要编排与凭据分发，与"纯本地、无账号"冲突；真值也难以在不接触真实主机的条件下复现。 |
| 2026-10-17 | **弃：cron / systemd 面板** | cronboard（1467★）与 isd（2152★）已占住这一形态；本系列再做一遍只是界面复刻，且系统级调度器状态依赖发行版与权限。 |
| 2026-10-17 | **弃：覆盖率 TUI** | 冷启动长（需要完整跑测试 + 覆盖率插桩），与"只读结果、秒级打开"的定位冲突；且与本题的用例树高度重叠，作为本题的后续扩展模块（覆盖率叠加）更合理。 |
| 2026-10-17 | **弃：解析 TAP / CTRF / Allure 原生格式** | 三者各有自己的生态与标准演进节奏；首期只承诺 JUnit XML 家族，避免"看起来支持很多、实际每个都半成品"。 |
| 2026-10-17 | **弃：直接调用 CI API 拉取历史 run** | 需要凭据、需要为每家 CI 写适配、会引入网络失败面；改为"用户自行 `gh run download` 到本地目录后喂给 ingest"，保持纯本地与零凭据。 |
| 2026-10-17 | **弃：在 TUI 内执行测试或重跑失败用例** | 执行会带来进程管理、超时、环境污染与安全面；本题只读结果，职责边界清晰。 |

## 三、承诺-证据台账

> 全项目只此一份。状态列随里程碑同步翻转；"待 Mx"是欠债，M6 前必须翻转或明确写成"永不进判定路径"。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| 多框架 JUnit XML 归一入库 | pytest / gotestsum / Playwright 真实产物 + `data/synth/` 生成器 | 随仓 fixtures + 生成器；无网络依赖 | `bench/bench_ingest.py`：用例数/失败数/skipped 与框架汇总逐项相等 | ⬜ 待 M1–M2 |
| 5 万用例单文件解析 < 2s | 合成大文件生成器 | 生成器随仓，语料不入仓（体积） | `bench/bench_ingest.py` 计时（`iterparse`） | ⬜ 待 M1 |
| 三栏失败优先视图 + 键盘全流程 | Textual 控件 | `testdeck tui` 入口 | `tests/test_tui_pilot.py`：无鼠标完成"定位失败用例并读到 stack 首行" | ⬜ 待 M3 |
| flaky 矩阵与四类分型 | occurrence 状态序列 | `F` 视图 + `export --format json` 的 `flaky` 字段 | `bench/bench_flaky.py`：固定 fixtures 手算逐项一致 | ⬜ 待 M4 |
| 恒失败用例不进 flaky 列表 | fail_rate == 1 的固定 fixture | 同上 | 独立测试断言 broken 与 flaky 两个集合互斥 | ⬜ 待 M4 |
| 慢测试 p50/p95（线性插值） | 固定耗时 fixture | `S` 视图 + `export` 字段 | `bench/bench_slow.py`：与独立参照脚本逐值相等 | ⬜ 待 M5 |
| 回归判定（1.2x 且 +200ms） | 固定耗时 fixture | `S` 视图 + `--fail-on regressions` | 边界单测：恰好等于 / 略低 / 略高 | ⬜ 待 M5 |
| 两次 run 用例级 diff | 两次 run 的 occurrences | `D` 视图 | `tests/test_diff.py`：新增失败 / 修复 / 仍失败三类对账 | ⬜ 待 M3–M4 |
| md / json 导出与 TUI 字段一致 | 同一 `report_model` | `testdeck export` | `bench/bench_export.py`：字段集合相等 + 两次导出逐字节一致 | ⬜ 待 M5 |
| CI 门禁退出码（0/1/2/3） | 样例仓库 | `--fail-on` | `bench/bench_export.py`：三种 `--fail-on` 的预期退出码 | ⬜ 待 M5 |
| 纯本地零上传 | 无网络调用的实现 | 全仓 | 源码扫描：无 HTTP 客户端调用；`selftest` 断言 | ✅ M0（AST 守门 + selftest 第 4 项） |
| TUI 录屏 | `textual run --dev` | `docs/demo/demo.gif` | 文件存在性 + 人工复核三视图 | ⬜ 待 M5 |

## 四、提交材料实物表

| 承诺项 | 应存在的文件路径 | 由哪个里程碑产出 | 用哪条命令核对 |
|---|---|---|---|
| 可运行源码与入口 | `pyproject.toml`、`src/testdeck/` | M0 | `pip install -e .` 后 `testdeck selftest` |
| TUI 录屏 | `docs/demo/demo.gif` | M5 | `git ls-files docs/demo/demo.gif` |
| 四套基准 | `bench/bench_ingest.py`、`bench/bench_flaky.py`、`bench/bench_slow.py`、`bench/bench_export.py` | M1–M5 | `python bench/run_all.py` |
| 三框架真实产物 | `bench/fixtures/pytest/`、`bench/fixtures/gotestsum/`、`bench/fixtures/playwright/` | M1 | `git ls-files bench/fixtures` |
| 合成语料与真值 | `data/synth/gen_runs.py`、`data/synth/expect.json` | M1 | `python data/synth/gen_runs.py --check` |
| plan 文档套件 | `plan/00`–`plan/06` | M0–M6 | `ls plan/` |
| 发布三件套 | git tag、GitHub Release（附产物）、`plan/RELEASE-M6.md` | M6 | `gh release view` + `git cat-file -e <tag>:plan/RELEASE-M6.md` |

## 五、形态自查表（唯一形态：终端 TUI）

| 形态 | 主入口 | 主控件/命令 | 接到哪个业务函数 | 断言在哪条测试 | 产物在哪个附件 |
|---|---|---|---|---|---|
| 终端 TUI | `pyproject.toml [project.scripts]` → `testdeck` | 左树 `Tree` / 右中 `Static`+`Sparkline` / `F`、`S`、`D` 三个视图 | `queries.py`（SQL 读取）→ `app.py`（控件装配）；`export` 与 TUI 共用 `report_model.py` | `tests/test_tui_pilot.py`（Pilot 键盘全流程）、`bench/bench_export.py`（字段一致） | `docs/demo/demo.gif`；Release 附源码包 |

> 该形态的"死壳"判据：若 `F`/`S`/`D` 任一视图只画标题不接查询，或 `demo.gif` 与实现不符，即视为未交付。

## 六、里程碑初稿

> 状态列是**四个副本之一**（另三处：`plan/05` §一、`plan/06` §二、`README.md` 状态表）。
> 布局门逐里程碑比对，任一处不一致即红。✅ 的里程碑必须同时有 `plan/HANDOFF-M<k>.md`（M0 按声明豁免）。

| 里程碑 | 内容 | DoD | 状态 |
|---|---|---|---|
| M0 | 方法论装订 + plan/00–06 + 可运行骨架（CLI 参数面 / 键位单点 / 退出码 / 规则包 / selftest） | 干净环境 `pip install -e ".[dev]"` 后 `testdeck selftest` 退出 0；`pytest` 全绿；布局门绿且 6 组变异全红 | ✅ 已完成（2026-10-18） |
| M1 | 三框架真实产物落 `bench/fixtures/`；合成 200 run × 5k 用例语料生成器与 `expect.json` 真值；大文件基准 | 三份产物的用例数/失败数/skipped 与框架汇总逐项相等；生成器 `--check` 可重放；5 万用例单文件解析 < 2s | ⬜ 待 M1 |
| M2 | `iterparse` 解析器、框架识别、四表 schema、upsert 与 ingest 摘要 | 重复 ingest 行数不变；坏文件记 `skipped:<reason>` 不静默；跨三框架的身份键一致；退出码 4 对 `ingest` 退役 | ⬜ 待 M2 |
| M3 | Textual 三栏布局、失败优先树、summary、failure 原文与 sparkline、键位栏 | `Pilot` 键盘全流程读到 stack 首行；summary 与 SQL 逐项相等 | ⬜ 待 M3 |
| M4 | 四态矩阵、四类分型、`D` 视图两次 run 用例级 diff | `bench/bench_flaky.py` 全绿；恒失败不进 flaky 的独立断言存在 | ⬜ 待 M4 |
| M5 | p50/p95、回归判定、瀑布条、`export --format md\|json`、`--fail-on`、录屏 | `bench/bench_slow.py` + `bench/bench_export.py` 全绿；md 字段与 TUI 一致；`docs/demo/demo.gif` 入库 | ⬜ 待 M5 |
| M6 | 脱敏、tag、GitHub Release、发布留档 | **git tag + GitHub Release（附产物）+ `plan/RELEASE-M6.md` 三件套**；`check_release.py` 无 FAIL | ⬜ 待 M6 |

## 七、M0 实测证据（2026-10-18，命令 + 结果）

> 只记**跑过的**；没跑的写在 `plan/05` §五「已知未验证项」，不在此表。

| 检查 | 命令 | 结果 |
|---|---|---|
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 1 / 状态副本 4 / 里程碑 7 |
| 布局门变异 | `py -3.12 tools/verify-layout-gate.py` | 7 组全部按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest -q` | 78 passed |
| 自检 | `py -3.12 -m testdeck selftest` | exit 0；键位 11 条 / 退出码 0–4 / 规则包 3 份 / 源码 10 个 |
| 干净安装 | 新 venv + `pip install -e ".[dev]"` | 裸 `testdeck` 与 `python -m testdeck` 两条通路均 exit 0；pytest 78 passed |
| 打包面 | `pip wheel .` | wheel 内含 `testdeck/rules/*.json` |
| 出题门 | `check_topic.py .`（只读） | 0 FAIL / 0 WARN / 25 PASS |
| CI workflow | 本地 `yaml.safe_load` + 断言 | 1 job / 7 steps 解析通过（**未接远端，CI 待首推验证**） |

## 八、风险登记

| 风险 | 说明 | 缓解 |
|---|---|---|
| 超大 XML | 单文件可能 > 50MB，整树 `parse` 会吃满内存 | 强制 `iterparse` + 逐元素 `clear()`；基准脚本设 5 万用例门槛 |
| 框架格式漂移 | 同名节点在不同框架下的属性/嵌套不同 | 只依赖 `testsuite/testcase/failure/error/skipped` 的核心形状；识别失败记 `unknown` 而不是猜 |
| 用例身份漂移 | 参数化用例名、动态类名会导致同一测试被拆成多条 | 身份键固定为 `(suite_name, classname, name)` 并保留完整参数串；文档说明改名即新用例 |
| 状态口径被误读 | skip/missing 若混入分母会让 flaky 分数失真 | 分母只含 pass/fail；skip/missing 不制造 transition（单点口径 + 测试） |
| 小样本误判 | 只有 2 次 run 时 transitions/(n-1) 极不稳定 | `transitions ≥ 3` 门槛；不足样本落 `watch` 而不是 flaky |
| 终端兼容性 | 窄终端、无真彩色、Windows Terminal 与 ConPTY 差异 | Textual 自适应布局；最小宽度以下降级为单栏；录屏固定终端尺寸 |
| 隐私 | 测试日志可能含路径、token、内部域名 | 纯本地、零上传、零遥测；导出文件由用户自行决定去向 |
| 形态退化为"又一个报告页" | 若砍掉 `F`/`S`/`D` 三个视图，产品只剩一棵树 | 写入本表：三个视图任一缺失即视为失败 |
