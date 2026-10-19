# 00 · README 总览 — 10-19-testdeck（测试结果终端工作台）

> 方法论：`ai-tool-project-sprint`（装订 2026-10-18）｜布局门：`py -3.12 tools/check-sprint-layout.py`｜续接对话第一件事 = 跑它

- 性质：不参赛项目题 · 发布 GitHub **公开仓库** · 署名 yuluo554
- 交付形态：**唯一形态 = 纯本地终端 TUI（Python + Textual）**；无服务器、无 GPU、无网络调用、无账号。
- 定位宣言："一条命令扫本地 `**/junit*.xml`、`target/surefire-reports/`、`gh run download` 目录，把上千次 run 归一到本地 SQLite；三栏 TUI：左侧 suite→class→test 树、右侧 failure 原文与历史 sparkline，`F` 切 flaky 矩阵、`S` 切慢测试瀑布、`D` 做两次 run 的用例级 diff。CI 只给一次 run 的红绿，跨 run 的'谁在抖、谁在变慢、这次是不是新坏'无人本地归档。"
- 版本史：v1 2026-10-17（题面定稿，查证基准日 2026-10-17；GitHub 检索实测窗口 2026-10-18 10:33–10:50 UTC）；v2 2026-10-19（M6 发布：`v0.1.0` tag + Release + 发布留档，M0–M6 全部 ✅）。
- 发布状态：**已发布** `v0.1.0`（GitHub Release 附手工源码包 `testdeck-0.1.0.tar.gz`）；发布留档 `plan/RELEASE-M6.md`（tag 前事实 / tag 后追加事实两栏 + 阶段 7 覆盖对账表）。

## 一、文档索引表

| 文档 | 内容 | 状态 |
|---|---|---|
| plan/00-README总览.md | 本文档：索引 / 决策记录 / 承诺-证据台账 / 里程碑 | ✅ v3（M4 回写状态与证据） |
| plan/01-题目文档.md | 十段式题目定稿（含需求原话、检索快照、招牌动词表、风险与边界） | ✅ v1 |
| plan/02-架构与技术选型.md | 分层架构、CLI 契约、退出码、数据库 schema、渲染与查询分离 | ✅ v3（M3 补查询层与两条守门的落点） |
| plan/03-模块详设.md | 五个模块的输入/输出/实现/降级/验收，编排与数据流 | ✅ v5（M5 落模块④慢测试与模块⑤导出） |
| plan/04-数据计划.md | 三框架真实产物清单、合成语料生成器、真值台账结构、基准口径 | ✅ v4（M4 补零计数 fail_rate 口径与 flaky 基准） |
| plan/05-里程碑与发布.md | 逐里程碑 DoD、退出码退役表、发布流程、状态列 | ✅ v5（M5 更新状态与退役表收尾） |
| plan/06-交付对标与决策.md | 提交材料对标、评分对标、形态自查表、待定决策、开放项 | ✅ v5（M5 更新状态与缺口表） |
| plan/HANDOFF-M1.md | M1 续接交接单（六节） | ✅ M0 收尾落盘 |
| plan/HANDOFF-M2.md | M2 续接交接单（六节） | ✅ M1 收尾落盘 |
| plan/HANDOFF-M3.md | M3 续接交接单（六节） | ✅ M2 收尾落盘 |
| plan/HANDOFF-M4.md | M4 续接交接单（六节） | ✅ M3 收尾落盘 |
| plan/HANDOFF-M5.md | M5 续接交接单（六节） | ✅ M4 收尾落盘 |
| plan/HANDOFF-M6.md | M6 续接交接单（六节） | ✅ M5 收尾落盘 |
| plan/RELEASE-M6.md | 发布留档（tag 前事实 / tag 后追加事实分栏 + 阶段 7 覆盖对账表） | ✅ M6（tag 树内） |
| data/README.md | 依据查证记录 + 数据源可获取性 + 合成数据与数值口径纪律 | ✅ v5（M5 补分位数/回归/导出三处落地记录） |
| data/synth/gen_runs.py + expect.json | D5 合成语料生成器 + D7 真值台账（22 锚点 + 50 样本 + 全语料汇总） | ✅ M1（M4 重生成：零计数 fail_rate 由 "0" 改为无定义） |
| bench/fixtures/{pytest,gotestsum,playwright}/ | D1–D3 三框架真实产物（各带 `expected.json` + `README.md` 来源说明） | ✅ M1 |
| bench/{refimpl,bench_ingest,bench_flaky,bench_slow,bench_export,run_all}.py | 参照实现 + 四套基准（ingest 四通道 / flaky 分型 / slow 分位数与回归 / export 字段与门禁）+ 统一入口（0/1/2 三语义、`--probe` 逐套件探活） | ✅ M5（四套件全绿，`CURRENT_MILESTONE` 调到 5，无 `not_enabled`） |
| src/testdeck/{junit,framework,ingest}.py + db.py | 流式解析 / 框架识别 / 扫描编排 / 四表 upsert（schema v2） | ✅ M2 |
| src/testdeck/{queries,report_model}.py + tui/{app,view}.py | 只读 SQL 层 + 报告模型（TUI 与导出共用）+ Textual 三栏 App + 纯呈现层 | ✅ M3（M4 接分型与 diff 分类） |
| src/testdeck/{flaky,diff}.py | 判定层纯函数：分型（含两条降级）/ 两次 run 三类分类 | ✅ M4 |
| src/testdeck/slow.py | 判定层纯函数：分位数（线性插值）/ 回归三态 / 瀑布条宽 | ✅ M5 |
| src/testdeck/export.py + report_model 的 render_md/render_json | 编排层：模型 → md/json + `--fail-on` 门禁（只读模型） | ✅ M5 |
| docs/demo/demo.gif + README.md | TUI 渲染输出录屏（三栏 + `F` + `S` + `D` + 帮助层；8 帧 / 24.0s） | ✅ M5（由 `tools/make-demo-gif.py` 可复跑） |
| pyproject.toml / src/testdeck/ / tests/ | 可安装骨架：`testdeck selftest`、键位表、退出码语义、规则包、零网络/分层守门 | ✅ M0（M2–M5 功能已全部落地） |
| tools/check-sprint-layout.py / verify-layout-gate.py / make-demo-gif.py / AGENTS.md | 方法论装订（布局门 + 变异验证）+ 录屏产出脚本 | ✅ M0 / M5 |
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
| 2026-10-19 | **D2/D3 产物改真跑**（M1） | 旧口径"本机无 Go / Playwright 未安装"是 2026-10-18 的实测结论；2026-10-19 复测发现三个工具链都能经可达镜像取得（`goproxy.cn` / `registry.npmmirror.com` / `cdn.npmmirror.com`）。真跑产出的证据强度高于预置产物，故改为真跑，并加 `bench/fixtures/regen_fixtures.py` 让"真跑 + 抄真值"可重跑。 |
| 2026-10-19 | **真值入仓用"锚点 + 确定性样本 + 汇总"**（M1） | 200×5000 全语料的输入侧会把 `expect.json` 推到 MB 级，与"入库文件要小"冲突。锚点（逐一覆盖 DoD 要求的手工样本）+ 确定性样本（切片）+ 全语料汇总三者结合：既让每个要求都有可复核的真值，又让台账留在 0.43 MB。全语料由同一条命令按种子重建，`--check` 位级比对。 |
| 2026-10-19 | **零计数样本落 `watch`，不落 `stable`**（M1） | 全 skip/missing 的用例 `fail_rate` 是 0/0、无定义。按字面规则会因 `fails == 0` 判成 `stable`，但"一次都没真正跑过"不构成"稳定"证据；判成 stable 会让 stable 计数虚高并掩盖"这个用例根本没在跑"。这条口径已在 `data/README.md` §四 定钉，M4 的生产 `flaky.py` 必须遵守。 |
| 2026-10-19 | **`run_all` 的"未就绪"计入 exit 1**（M1） | 未到里程碑的套件登记 `not_enabled` 并计入退出码 1；想只跑已就绪套件拿 0 必须显式 `--suites`。避免"默认只跑一部分却报告成功"。 |
| 2026-10-19 | **run 身份只从 XML 声明值读，不拿路径凑**（M2） | 三个分量（branch / commit / ci_run_id）只认 XML 自己声明的属性；读不到写空串。代价是**没声明身份的产物全部落进同一个"未标注 run"**——换来的是"未知"不会被伪装成"已知"，也不会架空 K1 的空串约定。前提是诚实标注这个边界（`plan/02` §三、`plan/03` 模块①）。 |
| 2026-10-19 | **单项缺失按"降级"处理，不报废整个文件**（M2） | 坏 XML / 坏编码 / 缺根 / 不可读 → 整个文件记 `skipped:<reason>`；而"耗时非法 / 用例缺 name / 缺 started_at / commit 非 40 位" → 文件照常入库，该项记 `None`/空串并计入 `degraded`。粒度分开才能既不静默、也不过度丢弃。 |
| 2026-10-19 | **退出码 4 逐命令退役，不删常量**（M2） | `ingest` 实装后不再返回 4（`tui`/`export` 到 M3/M5 才退役）。退役判据落成可跑断言：`tests/test_exit_codes.py` 既断言"已实装命令不返回 4"，也用 AST 断言 `NOT_READY` 只出现在未实装命令的分支里。 |
| 2026-10-19 | **库 schema 版本不符时报错，不静默复用**（M2） | `suites.time_ms` 由 `NOT NULL DEFAULT 0` 改为可空（"没声明耗时"≠"耗时 0"），`SCHEMA_VERSION` 升到 2；连接时版本不符直接 exit 3 并提示删库重建——晚一点炸不如早说。 |
| 2026-10-19 | **`queries.py` 只读、不返回 Textual 对象**（M3） | 这是"UI 之外第二条通路"的兑现方式：summary 的每个数字都能用一条 SQL 直接验（`test_queries.py`），而不用靠 Pilot 截图比对。返回 dataclass/dict 也意味着导出（M5）能直接复用这一层。 |
| 2026-10-19 | **失败优先排序单点在 `queries.fail_first_key`**（M3） | 树、矩阵、瀑布共用同一个排序键。两处各写一份必然出现"屏幕上的顺序"与"导出里的顺序"两套口径；单点之后这条差异在结构上不可能发生（K35）。 |
| 2026-10-19 | **两条降级放纯函数、不放 App**（M3） | `plan/03` 要求两条降级都有不依赖 Pilot 的测试。把 `column_mode` / `style_mode` 做成纯函数，App 只把结果落到 CSS 类上——于是"屏幕上的行为"与"单元测试钉住的判据"是同一份代码，不是两份。 |
| 2026-10-19 | **TUI 默认不聚焦任何控件**（M3） | Textual 默认把首焦点给第一个可聚焦控件，本项目里那是搜索框——`j`/`F` 全被它吃掉（实测：敲 `j` 只会多一个字符）。改为 `Input.can_focus=False` + `on_ready` 清焦点，`/` 时才临时打开。 |
| 2026-10-19 | **分层守门必须有两半**（M3） | 只有"不许 import 什么"是半条守门：把 `app.py` 里对 `report_model` 的引用删掉，界面照样能跑，但"md 字段与 TUI 一致"就悄悄失效了。加了 `REQUIRED_IMPORTS`（必须 import），并做了点名要求的那次变异验证（删引用 → 必红）。 |
| 2026-10-19 | **测试绝不碰用户默认库**（M3） | 实测两次踩坑（写默认库 / `tui` 在默认库有数据时把测试挂住），故在 `tests/conftest.py` 加 autouse 的 `XDG_DATA_HOME` 隔离。"默认库不存在"从此在任何机器上都成立，判据不随环境翻转。 |
| 2026-10-19 | **`F/S/D` 在 M3 只交"接真实查询的骨架"**（M3） | 分型、分位数、diff 三类分类的**口径**留给 M4/M5，M3 不另写一份（否则口径复制成第二套）。骨架的验收线是"真实查询结果出现在面板里"（死壳判据），而不是"画了标题"。 |
| 2026-10-19 | **零计数样本 `fail_rate` 记为"无定义"（None），不是 `"0"`**（M4） | `data/README.md` §四 早已定钉"零计数 → watch，不得判 stable"，但参照实现当时把 `fail_rate` 渲染成 `"0"`——`"0"` 与"跑过且从没失败"（stable）在数值上撞车，正是 K34 要禁的误导。按 `plan/04` §二.6「引擎与真值同源修正」，改参照实现并重生成台账；生产 `flaky.py` 从一开始就按口径记无定义。 |
| 2026-10-19 | **`broken ∩ flaky == ∅` 用独立断言，不靠分型顺序自证**（M4） | "先判恒失败"只是让相交在**结构上**不可能；但那条顺序若被改动，仅靠顺序本身无法察觉。故在 `tests/test_flaky.py` 与 `bench/bench_flaky.py` 各拿一份固定 fixture 的 broken / flaky 两份集合**求交**——判据与"先判哪个分支"无关。 |
| 2026-10-19 | **`diff` 的"修复"要求 `after == pass`**（M4） | `fail→skip` / `fail→缺` 落"其余"，**不是**修复：没有 `pass` 就没有"修好了"的证据。把"这次没跑/被跳过"算成修复会让修复数虚高——那正是 `--fail-on new-failures` 想抓的自欺。 |
| 2026-10-19 | **判定层阈值全部走规则包，零字面量门禁落地**（M4） | `flaky.py` 里的阈值只从 `rules/flaky.json` 读；`tests/test_no_rule_literals.py` AST 扫 `flaky.py`/`slow.py`/`report_model.py` 的数值常量，凡等于规则阈值即红（豁免 `0`/`1` 这类结构常量，且豁免**穷尽式**）。 |

## 三、承诺-证据台账

> 全项目只此一份。状态列随里程碑同步翻转；"待 Mx"是欠债，M6 前必须翻转或明确写成"永不进判定路径"。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| 多框架 JUnit XML 归一入库 | pytest / gotestsum / Playwright 真实产物 + `data/synth/` 生成器 | 随仓 fixtures + 生成器；无网络依赖 | `bench/bench_ingest.py`：生产解析器 vs 基准侧重数 vs XML 声明值 vs `expected.json` 四通道逐项相等；`tests/test_ingest.py`：四表落库与 upsert 幂等 | ✅ M2（归一入库已实装：18 条用例 / 3 suite / 1 run，重复 ingest 行数不变） |
| 5 万用例单文件解析 < 2s | 合成大文件生成器 | 生成器随仓，语料不入仓（体积） | `bench/bench_ingest.py` 计时**生产解析器**（`iterparse`） | ✅ M2（本机实测 0.28s / 门槛 2s） |
| 三栏失败优先视图 + 键盘全流程 | Textual 控件 | `testdeck tui` 入口 | `tests/test_tui_pilot.py`：无鼠标完成"定位失败用例并读到 stack 首行" | ✅ M3（15 例无头 Pilot 全绿；纯键盘走 `j`/`G`/`g`/`/`/`Enter`/`Esc`/`q`） |
| flaky 矩阵与四类分型 | occurrence 状态序列 | `F` 视图 + `export --format json` 的 `flaky` 字段 | `bench/bench_flaky.py`：`flaky.classify` 与台账期望侧、参照实现逐值相等（22 锚点 + 50 样本 + 全语料 5000 条） | ✅ M4（`F` 视图渲染四态矩阵 + 分型标签；summary 的 `flaky`/`broken` 由 `flaky.py` 填） |
| 恒失败用例不进 flaky 列表 | fail_rate == 1 的固定 fixture | 同上 | 独立测试断言 broken 与 flaky 两个集合互斥（`test_flaky_broken_excluded` + `bench/bench_flaky.py:broken_flaky_exclusive`，拿两份集合求交，不靠函数内部顺序自证） | ✅ M4 |
| 慢测试 p50/p95（线性插值） | 固定耗时 fixture | `S` 视图 + `export` 字段 | `bench/bench_slow.py`：与独立参照脚本逐值相等（22 锚点 + 50 样本 + 全语料 5000 条） | ✅ M5（`S` 视图每条用例带 `p50/p95/reg`；导出带回归清单） |
| 回归判定（1.2x 且 +200ms） | 固定耗时 fixture | `S` 视图 + `--fail-on regressions` | 边界单测：恰好等于 / 略低 / 略高（`slow/regression_boundaries` 三态齐全） | ✅ M5（`--fail-on regressions` 命中 → exit 1；只读模型） |
| 两次 run 用例级 diff | 两次 run 的 occurrences | `D` 视图 | `tests/test_diff.py`：新增失败 / 修复 / 仍失败三类对账（逐类断言 + 与"未来 run"的 `缺→fail` 对账） | ✅ M4（`D` 视图按 `diff.py` 三类分类分组渲染） |
| md / json 导出与 TUI 字段一致 | 同一 `report_model` | `testdeck export` | `bench/bench_export.py`：字段集合相等 + 两次导出逐字节一致（`tests/test_export_determinism.py` 双跑 `cmp`） | ✅ M5 |
| CI 门禁退出码（0/1/2/3） | 样例仓库 | `--fail-on` | `bench/bench_export.py`：三种 `--fail-on` 的预期退出码（命中 1 / 未命中 0 / 未知值 2 / 库不可用 3） | ✅ M5（判定只读模型，不重新查库） |
| 纯本地零上传 | 无网络调用的实现 | 全仓 | 源码扫描：无 HTTP 客户端调用；`selftest` 断言 | ✅ M0（AST 守门 + selftest 第 4 项）；M3 把守门拆成 `tests/test_no_network.py`（含动态导入与变异验证） |
| TUI 录屏 | Textual 渲染输出（`App.export_screenshot`） | `docs/demo/demo.gif` | 文件存在性 + 时长 ≤30s + 帧数 >1（`tests/test_demo_gif.py`） | ✅ M5（**真终端表现未验**，见 G6） |

## 四、提交材料实物表

| 承诺项 | 应存在的文件路径 | 由哪个里程碑产出 | 用哪条命令核对 |
|---|---|---|---|
| 可运行源码与入口 | `pyproject.toml`、`src/testdeck/` | M0 | `pip install -e .` 后 `testdeck selftest` |
| TUI 录屏 | `docs/demo/demo.gif` | M5 | `git ls-files docs/demo/demo.gif`（+ `py -3.12 tools/make-demo-gif.py --check`） |
| 四套基准 | `bench/bench_ingest.py`、`bench/bench_flaky.py`、`bench/bench_slow.py`、`bench/bench_export.py` | M1–M5 | `python bench/run_all.py`（**四套件全就绪**，43 项检查全绿 exit 0；`--probe` 逐套件探活全检出） |
| 三框架真实产物 | `bench/fixtures/pytest/`、`bench/fixtures/gotestsum/`、`bench/fixtures/playwright/` | M1 | `git ls-files bench/fixtures` |
| 合成语料与真值 | `data/synth/gen_runs.py`、`data/synth/expect.json` | M1 | `python data/synth/gen_runs.py --check` |
| plan 文档套件 | `plan/00`–`plan/06` | M0–M6 | `ls plan/` |
| 发布三件套 | git tag、GitHub Release（附产物）、`plan/RELEASE-M6.md` | M6 | `gh release view` + `git cat-file -e <tag>:plan/RELEASE-M6.md` |

## 五、形态自查表（唯一形态：终端 TUI）

| 形态 | 主入口 | 主控件/命令 | 接到哪个业务函数 | 断言在哪条测试 | 产物在哪个附件 |
|---|---|---|---|---|---|
| 终端 TUI | `pyproject.toml [project.scripts]` → `testdeck` | 左树 `Tree` / 右中 `Static`+`Sparkline` / `F`、`S`、`D` 三个视图 | `queries.py`（SQL 读取）→ `app.py`（控件装配）；`report_model.py` 是 TUI 与导出的共用模型（`view.py` 只做纯渲染） | `tests/test_tui_pilot.py`（Pilot 键盘全流程）、`bench/bench_export.py`（字段一致） | `docs/demo/demo.gif`；Release 附源码包 |

> 该形态的"死壳"判据：若 `F`/`S`/`D` 任一视图只画标题不接查询，或 `demo.gif` 与实现不符，即视为未交付。

## 六、里程碑初稿

> 状态列是**四个副本之一**（另三处：`plan/05` §一、`plan/06` §二、`README.md` 状态表）。
> 布局门逐里程碑比对，任一处不一致即红。✅ 的里程碑必须同时有 `plan/HANDOFF-M<k>.md`（M0 按声明豁免）。

| 里程碑 | 内容 | DoD | 状态 |
|---|---|---|---|
| M0 | 方法论装订 + plan/00–06 + 可运行骨架（CLI 参数面 / 键位单点 / 退出码 / 规则包 / selftest） | 干净环境 `pip install -e ".[dev]"` 后 `testdeck selftest` 退出 0；`pytest` 全绿；布局门绿且 6 组变异全红 | ✅ 已完成（2026-10-18） |
| M1 | 三框架真实产物落 `bench/fixtures/`；合成 200 run × 5k 用例语料生成器与 `expect.json` 真值；大文件基准 | 三份产物的用例数/失败数/skipped 与框架汇总逐项相等；生成器 `--check` 可重放；5 万用例单文件解析 < 2s | ✅ 已完成（2026-10-19） |
| M2 | `iterparse` 解析器、框架识别、四表 schema、upsert 与 ingest 摘要 | 重复 ingest 行数不变；坏文件记 `skipped:<reason>` 不静默；跨三框架的身份键一致；退出码 4 对 `ingest` 退役 | ✅ 已完成（2026-10-19） |
| M3 | Textual 三栏布局、失败优先树、summary、failure 原文与 sparkline、键位栏 | `Pilot` 键盘全流程读到 stack 首行；summary 与 SQL 逐项相等 | ✅ 已完成（2026-10-19） |
| M4 | 四态矩阵、四类分型、`D` 视图两次 run 用例级 diff | `bench/bench_flaky.py` 全绿；恒失败不进 flaky 的独立断言存在 | ✅ 已完成（2026-10-19） |
| M5 | p50/p95、回归判定、瀑布条、`export --format md\|json`、`--fail-on`、录屏 | `bench/bench_slow.py` + `bench/bench_export.py` 全绿；md 字段与 TUI 一致；`docs/demo/demo.gif` 入库 | ✅ 已完成（2026-10-19） |
| M6 | 脱敏、tag、GitHub Release、发布留档 | **git tag + GitHub Release（附产物）+ `plan/RELEASE-M6.md` 三件套**；`check_release.py` 无 FAIL | ✅ 已完成（2026-10-19） |

## 七、实测证据（按里程碑分表，命令 + 结果）

> 只记**跑过的**；没跑的写在 `plan/05` §五「已知未验证项」，不在此表。

### 7.1 M0（2026-10-18）

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

### 7.2 M1（2026-10-19，数据先行）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 2 / 状态副本 4 / 里程碑 7 |
| 全量测试 | `py -3.12 -m pytest` | **150 passed** |
| 三框架真实产物 | `bench/fixtures/regen_fixtures.py`（真跑） | pytest 6/1/0/1、gotestsum 5/1/0/1、playwright 7/1/0/1（tests/failures/errors/skipped） |
| 产物逐项对账 | `py -3.12 bench/run_all.py --suites ingest` | 11 项检查全过，exit 0（元素重数 / XML 声明值 / expected.json 三通道逐项相等） |
| 5 万用例性能 | 同上（`perf/iterparse_big_file`） | **0.071–0.081s**（取 3 次最小值；门槛 2s），语料 3.6 MB / 50000 用例 |
| 真值台账位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS，436803 字节逐字节一致 |
| 生成器确定性 | 同 seed 三次独立运行 | sha256 `281e2a271f60ec30e1649415402f7dd1bbbf1e1640816ae2e78582d234cdd8eb` 全同 |
| 坏真值证伪 | 篡改一条锚点 `label` 后 `--check` | exit 1（不是恒绿） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 3 处注入（参照实现违规 import / 对账 off-by-one / 性能门槛压 0）全部被报出 |
| `run_all` 三语义 | `--suites ingest` / 不带参数 / `--suites nope` | exit `0` / `1`（3 套件未就绪，不冒充通过）/ `2` |
| 入库脱敏 | `py -3.12 bench/fixtures/scan_leaks.py` | 17 文件 0 泄漏（且造违规样本能报红） |
| 参照实现独立性 | `bench/refimpl.py` AST 守门 + 变异验证 | 未 import `testdeck.*`；注入违规 import 能被报出 |
| 出题门 | `check_topic.py .`（只读） | 0 FAIL / 0 WARN / 25 PASS |

> **本机环境口径更新（2026-10-19 复测）**：Go 1.23.4 与 gotestsum v1.12.0 可真装
> （`dl.google.com` + `goproxy.cn`），Playwright 1.48.2 + Chromium 130 可真装
> （`registry.npmmirror.com` + `cdn.npmmirror.com`）——**D2/D3 因此改为真跑产出**，
> 不再是预置产物。

### 7.3 M2（2026-10-19，解析落库）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 3 / 状态副本 4 / 里程碑 7 |
| 全量测试 | `py -3.12 -m pytest` | **221 passed** |
| 四通道逐项对账 | `py -3.12 bench/run_all.py --suites ingest` | 20 项检查全过，exit 0（生产解析器 / 基准侧重数 / XML 声明值 / `expected.json`） |
| 生产解析器性能 | 同上（`perf/iterparse_big_file`） | **0.17–0.28s** / 50000 用例（门槛 2s，取 3 次最小值；多轮实测抖动区间） |
| 框架识别 | 同上（`fixture/*/framework_detected`） | 三份真跑产物分别识别为 pytest / gotestsum / playwright |
| 归一入库 | `testdeck ingest <三份产物> --db <临时库>` | `files=3 runs=1 cases=18 occurrences=18 skipped=0`；四表 1/3/18/18 |
| upsert 幂等 | 同一条 ingest 跑两遍 | 四表行数不变（`test_repeat_ingest_keeps_row_counts`） |
| 坏文件不中断 | 一批里放一个坏 XML | `skipped: bad_xml=1 (...)`，好文件照样入库 |
| dry-run 零副作用 | `ingest <目录> --dry-run` + 全仓快照 | 仓内快照差集为空、默认库目录都没建出来 |
| 退出码退役 | `tests/test_exit_codes.py` | `ingest` 任何入参形态都不返回 4；`NOT_READY` 只留在未实装命令分支（AST 断言） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 参照实现违规 import / 对账 off-by-one / 性能门槛压 0 三处注入全被报出 |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS（436803 字节） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | 7 组变异全按预期变红，还原后全绿 |
| 打包面 | `py -3.12 -m pip wheel --no-build-isolation --no-deps .` | wheel 内含 `junit.py` / `framework.py` / `ingest.py` + `rules/*.json`（33 KB） |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |

> **本轮未接远端**（`git remote -v` 为空）：CI 一栏只能是"本地等价校验
> （CI 待首推验证）"，不得写成"CI 绿"。

### 7.4 M3（2026-10-19，三栏视图）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 4 / 状态副本 4 / 里程碑 7 |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | 7 组变异全按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` | **308 passed**（M2 为 221） |
| 三栏键盘全流程 | `py -3.12 -m pytest tests/test_tui_pilot.py` | 15 例全绿：纯键盘"进入 → `j` 移到失败用例 → 右栏读到 `stack:` 首行" |
| summary 与 SQL 逐项相等 | 同上 + `tests/test_queries.py` | `total=18 fail=3 skip=3` 与直出 SQL 逐项相等；键序来自规则包 |
| `F/S/D` 接真实查询 | `tests/test_tui_pilot.py::test_three_views_render_real_query_results` | 三视图都断言了**真实数据行**出现在面板（矩阵首行、瀑布首条耗时、diff 的 `before→after`） |
| 两条降级（纯函数） | `py -3.12 -m pytest tests/test_view.py` | 27 例：`column_mode` 5 例阈值 + `style_mode` 7 例矩阵 + 9 个渲染器"剥标记后逐字符相同" |
| 两条降级（真 App） | `tests/test_tui_pilot.py` | 窄终端 → `single-column` 类 + `Enter` 进详情页；`NO_COLOR=1` → `mono` 类且结构不丢 |
| 零网络守门 | `tests/test_no_network.py` | 6 例：四写法 + 动态导入字符串 + 白名单；注入违规必红 |
| 分层守门（含变异） | `tests/test_layering.py` | 6 例：8 条 LAYER_RULES 逐条可命中；**删掉 `app.py` 的 `report_model` 引用 → 必红** |
| 键位单点 | `tests/test_keys_single_source.py` | 7 例：AST 扫 `src/`，豁免表穷尽式（登记了却不存在 → 红） |
| 退出码 4 对 `tui` 退役 | `tests/test_exit_codes.py` | 13 例：`tui` 任何入参形态不返回 4；`NOT_READY` 分支只点名 `export` |
| 自检 | `py -3.12 -m testdeck selftest` | exit 0；键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 18 个 |
| 四通道逐项对账 | `py -3.12 bench/run_all.py --suites ingest` | 20 项检查全过，exit 0 |
| 生产解析器性能 | 同上（`perf/iterparse_big_file`） | **0.209s** / 50000 用例（门槛 2s，取 3 次最小值） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 三处注入全被报出，exit 0 |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS（436803 字节） |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |

> **M3 实测踩到的两个"测试依赖环境"坑**（已修，写进 `plan/HANDOFF-M4.md` §4）：
> ① `["ingest", "."]` 会把 fixture 写进**用户默认库**；② 本机默认库**恰好有数据**时
> `["tui"]` 会真的把 TUI 起起来并**挂住整个 pytest**（后台跑卡在 23% 不动）。
> 修法是 `tests/conftest.py` 的 autouse `XDG_DATA_HOME` 隔离——测试绝不碰默认库。

### 7.5 M4（2026-10-19，flaky 分型与 diff）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 5 / 状态副本 4 / 里程碑 7 |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | 7 组变异全按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` | **375 passed**（M3 为 308） |
| 分型逐值对账 | `py -3.12 bench/bench_flaky.py` | 7 项检查全过：22 锚点 + 50 样本 7 字段逐值相等；生产 vs 参照 72 条记录逐值相等；全语料 5000 条分型计数逐类相等 |
| `broken ∩ flaky == ∅` 独立断言 | 同上（`flaky/broken_flaky_exclusive`） | 两份集合求交为空（broken 1 / flaky 22，两份都非空）；强行判 flaky 的注入能报红 |
| 两条降级 | 同上（`degrade_zero_counted` / `degrade_short_window`） | 零计数样本落 `watch` 且 `fail_rate` 无定义；窗口不足一律 `watch`（不得输出 flaky） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 参照实现违规 import / ingest 两处 / flaky 两处注入全被报出，exit 0 |
| 零字面量门禁 | `py -3.12 -m pytest tests/test_no_rule_literals.py` | 8 例：判定层无阈值字面量；注入 `3` / `0.05` 必红；白名单穷尽式 |
| diff 三类对账 | `py -3.12 -m pytest tests/test_diff.py` | 24 例：14 组状态对逐类断言；`fail→skip`/`fail→缺` 不判"修复"；接真实库对账 |
| summary 接分型 | `py -3.12 -m pytest tests/test_queries.py` | `flaky`/`broken` 由 `flaky.py` 填（非 `None`）；summary 计数与矩阵行数同源 |
| 四通道逐项对账 | `py -3.12 bench/run_all.py --suites ingest,flaky` | 27 项检查全过，exit 0 |
| 真值台账位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS（436804 字节；零计数 `fail_rate` 由 `"0"` 改为无定义） |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |

> **M4 修正的一处口径**：参照实现把零计数样本的 `fail_rate` 渲染成 `"0"`，
> 与 `data/README.md` §四「零计数样本 `fail_rate` 无定义」（K34）冲突——
> `"0"` 会与"跑过且从没失败"（stable）撞车。按 `plan/04` §二.6「引擎与真值同源修正」，
> 改 `bench/refimpl.py`（`fail_rate` 记 ``None``）并**重生成** `expect.json`
> （436803 → 436804 字节）；生产 `flaky.py` 本就从口径出发记为无定义，两边由此对齐。
>
> **M4 实测踩到的一处竞态**（已修，写进 `plan/HANDOFF-M5.md` §4）：`on_mount` 取数走
> worker 线程，`await pilot.pause()` 一次在满负载下不足以保证 `ReportLoaded` 已回投——
> 表现为**全量 pytest 下 `test_tui_pilot.py` 偶发红、单跑又全绿**。M4 把 `case_profiles`
> 加进 worker 后这个既有竞态被放大，修法是 `_wait_for_report` 轮询 `app.report`。
>
> **本轮未接远端**（`git remote -v` 为空）：CI 一栏只能是"本地等价校验
> （CI 待首推验证）"，不得写成"CI 绿"。

### 7.6 M5（2026-10-19，慢测试与回归 + 导出与门禁 + 录屏）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；扫到 文档 10 / 交接单 6 / 状态副本 4 / 里程碑 7 |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | 7 组变异全按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` | **474 passed**（M4 为 375） |
| 分位数/回归逐值对账 | `py -3.12 bench/bench_slow.py` | 8 项检查全过：22 锚点 + 50 样本 5 字段逐值相等；生产 vs 参照 72 条记录逐值相等；全语料 5000 条回归三态计数逐项相等 |
| 回归边界六种 | 同上（`slow/regression_boundaries`） | ratio/delta 恰好 / 略低 / 略高 八锚点逐项相符，**True/False/None 三态齐全** |
| 缺失耗时口径可证伪 | 同上（`slow/missing_time_not_zero`） | 缺失 p50=150 != 补 0 的 p50=100（缺失不进样本） |
| 不可判不谎报 | 同上（`slow/undefined_is_none_not_false`） | `base==0 → undefined_base`、缺样本 → `missing_window`，两者都返回 `None` |
| 导出字段一致 + 逐字节一致 | `py -3.12 bench/bench_export.py` | 8 项检查全过：md 列序 = JSON 键序 = 字段声明序；两次渲染逐字节一致；不含 `ingested_at`/生成时刻/绝对路径 |
| `--fail-on` 退出码 | 同上（`export/fail_on_exit_codes`）+ `tests/test_export.py` | 三种值 × 命中/干净 六例全部相符；未知值 → 2；库不可用 → 3；**判定只读模型**（篡改模型结论随之变） |
| 四套件总账 | `py -3.12 bench/run_all.py --suites ingest,flaky,slow,export` | **43 项检查全过，exit 0**（四套件全就绪，无 `not_enabled`） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 参照实现违规 import + ingest 两处 + flaky 两处 + slow 两处 + export 四处注入**全被报出**，exit 0 |
| 零字面量门禁 | `py -3.12 -m pytest tests/test_no_rule_literals.py` | 9 例：`slow.py` 纳入扫描面（三文件全在）；注入 `3`/`0.05`/`200` 必红；白名单穷尽式 |
| 退出码 4 全面退役 | `py -3.12 -m pytest tests/test_exit_codes.py` | `export` 任何入参形态不返回 4；`cli.py` 里**已无返回 4 的分支**（AST 断言） |
| 分层守门（含 export.py） | `py -3.12 -m pytest tests/test_layering.py` | 9 条 LAYER_RULES 逐条可命中（注入表与 `LAYER_RULES` 同步断言） |
| `S` 视图接判定 | `tests/test_tui_pilot.py` + `tests/test_queries.py` | Pilot 断言面板带 `p50=`/`p95=`/`reg=`；两次 run 真库上 1000→1500ms 判回归 |
| 录屏 | `py -3.12 tools/make-demo-gif.py --check` | `docs/demo/demo.gif`：8 帧 / **24.0s**（上限 30s）/ 478380 字节；`tests/test_demo_gif.py` 9 例 |
| 自检 | `py -3.12 -m testdeck selftest` | exit 0（键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 22 个） |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS（436804 字节） |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |

> **本轮未接远端**（`git remote -v` 为空）：CI 一栏只能是"本地等价校验
> （CI 待首推验证）"，不得写成"CI 绿"。
>
> **录屏口径（如实写）**：`docs/demo/demo.gif` 是 **Textual 渲染输出**（`App.export_screenshot`
> 的 SVG）经 Pillow 栅格化拼成，不是真终端字节流录制——本机 Windows 无 `pty`/`termios`，
> `winpty` 非 tty 下断言失败，`asciinema`/`agg`/`pyte` 都不在且本轮不下载。真终端
> （字体/像素级/ConPTY）表现仍**未验**，G6 未关闭。
>
> **本节 byte 数修正（M6）**：M5 原记 `demo.gif` 为 432976 字节，实测入库文件是 **478380**。
> 属"同源数字失真"（阶段 7 出口门第 9 项），M6 按实测改写；文件本身未变。

### 7.7 M6（2026-10-19，脱敏发布：干净环境 + tag + Release + 留档）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿；`LAYOUT.RELEASE` 生效（两栏 + 覆盖对账 + 25 三态行） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | **8 组**变异全按预期变红（新增 M8 验发布门两栏），还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` | **476 passed**（M5 为 474；+1 = 仓库脚本安装面门，+1 = 跨盘符回落用例） |
| 干净环境验证 | `git archive HEAD` → 中立目录 → 新 venv → `pip install -e ".[dev]"` → README 逐条 | **8 条命令全 exit 0**；两通路（裸 `testdeck` / `python -m testdeck`）`selftest` 均 0；`pytest` 全绿 |
| 首推 CI | `gh run list --workflow ci.yml` | 四矩阵 3.9/3.12 × ubuntu/windows 实跑；首跑 1 红（暴露 py3.9 标准库名单 + 跨盘符断言两缺陷）→ 修复后全绿（run 39206916398 / 39207422066） |
| 干净环境抓到的缺陷 | 同上 | **2 处**：① `Pillow` 未进 dev extra（干净环境 6 例红）② 字体硬编码 `C:/Windows/Fonts/simsun.ttc`（ubuntu CI 会 `OSError`）——均已修，并补安装面门 |
| 脱敏·源码常量面 | 扫 `src/**` 机器路径/真域名/凭据/`hostname=` | 25 文件 **0 命中** |
| 脱敏·文档面 | `py -3.12 -X utf8` 以 `encoding="utf-8"` 回读 | 4 处命中均为**抽象样例**（`/tmp` 跨工具说明 + 合成测试输入），非机器标识 |
| 脱敏·产物面 | `py -3.12 bench/fixtures/scan_leaks.py` | 17 文件**干净** |
| 脱敏·提交元数据面 | `git log --format='%ae%n%ce'` 去重 | 唯一邮箱 `282769740+yuluo554@users.noreply.github.com`（**全部 noreply**） |
| 四套基准（CI 形态） | `py -3.12 bench/run_all.py --no-perf-gate` | 四套件 43 项检查全绿，exit 0（已接进 CI 步骤） |
| 探活 | `py -3.12 bench/run_all.py --probe` | 逐套件注入全被报出，exit 0 |
| 录屏复核 | `py -3.12 tools/make-demo-gif.py --check` | 8 帧 / 24.0s / **478380 字节**；重生成逐字节一致 |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |
| 发布终态门（tag 前） | `check_release.py . --tag v0.1.0` | tag/附件/远端项如实标"待首推"（见 `plan/RELEASE-M6.md` §三） |

> **发布留档** `plan/RELEASE-M6.md`：§一 tag 前事实 / §二 tag 后追加事实（回填槽位）/
> §三 阶段 7 覆盖对账表（25 行三态）。tag 之后的实测值（run id / 附件 sha256 / 真下载复核）
> 在 **§二** 回填——它们**在结构上不可能**出现在 tag 树里。


## 八、风险登记
| 风险 | 说明 | 缓解 |
|---|---|---|
| 超大 XML | 单文件可能 > 50MB，整树 `parse` 会吃满内存 | 强制 `iterparse` + 逐元素 `clear()`；基准脚本设 5 万用例门槛 |
| 框架格式漂移 | 同名节点在不同框架下的属性/嵌套不同 | 只依赖 `testsuite/testcase/failure/error/skipped` 的核心形状；识别失败记 `unknown` 而不是猜 |
| run 身份缺失导致合并 | 产物里没写 `branch`/`commit`/`ci_run_id` 时，多份产物会落进同一个"未标注 run"，跨 run 视图失去分辨力 | 口径与代价已如实登记（K26 / `plan/02` §三）；CI 侧注入身份属性即可分开；若将来改为"按目录分组"，必须先改口径与测试 |
| 用例身份漂移 | 参数化用例名、动态类名会导致同一测试被拆成多条 | 身份键固定为 `(suite_name, classname, name)` 并保留完整参数串；文档说明改名即新用例 |
| 状态口径被误读 | skip/missing 若混入分母会让 flaky 分数失真 | 分母只含 pass/fail；skip/missing 不制造 transition（单点口径 + 测试） |
| 小样本误判 | 只有 2 次 run 时 transitions/(n-1) 极不稳定 | `transitions ≥ 3` 门槛；不足样本落 `watch` 而不是 flaky |
| 终端兼容性 | 窄终端、无真彩色、Windows Terminal 与 ConPTY 差异 | Textual 自适应布局；最小宽度以下降级为单栏；录屏固定终端尺寸 |
| 隐私 | 测试日志可能含路径、token、内部域名 | 纯本地、零上传、零遥测；导出文件由用户自行决定去向 |
| 形态退化为"又一个报告页" | 若砍掉 `F`/`S`/`D` 三个视图，产品只剩一棵树 | 写入本表：三个视图任一缺失即视为失败 |
