# HANDOFF-M3 · 下一棒 = 三栏视图（M3）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（装订 + 计划套件 + 可运行骨架，2026-10-18）、M1（数据先行，2026-10-19）、
M2（解析落库，2026-10-19）。**

| 项 | 证据（M2 本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿（文档 10 / 交接单 3 / 状态副本 4 / 里程碑 7） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` → 7 组变异全红、还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` → **221 passed** |
| 四通道逐项对账 | `py -3.12 bench/run_all.py --suites ingest` → 20 项检查全过，exit 0 |
| 生产解析器性能 | 同上（`perf/iterparse_big_file`）→ **0.17–0.28s** / 50000 用例（门槛 2s，取 3 次最小值；多轮实测抖动区间） |
| 框架识别 | 同上（`fixture/*/framework_detected`）→ pytest / gotestsum / playwright 三份真跑产物全中 |
| 归一入库 | `ingest` 三份产物 → `files=3 runs=1 cases=18 occurrences=18 skipped=0`；四表 1 / 3 / 18 / 18 |
| upsert 幂等 | 同一条 ingest 跑两遍 → 四表行数不变 |
| 坏文件不中断 | 一批里放一个坏 XML → `skipped: bad_xml=1 (...)`，好文件照样入库 |
| dry-run 零副作用 | 仓内快照差集为空，且默认库目录都没被建出来 |
| 退出码退役 | `tests/test_exit_codes.py` → `ingest` 任何入参形态都不返回 4；`NOT_READY` 只在未实装分支（AST 断言） |
| 探活（基准侧） | `py -3.12 bench/run_all.py --probe` → 三处注入（参照实现违规 import / 对账 off-by-one / 性能门槛压 0）全被报出 |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` → PASS（436803 字节） |
| 入库产物脱敏 | `py -3.12 bench/fixtures/scan_leaks.py` → 0 泄漏 |
| 出题门 | `check_topic.py .`（只读）→ 无 FAIL |

**本轮交付/改动的文件**（相对路径）：

```
src/testdeck/junit.py               # 生产解析器（iterparse 流式、四态、耗时、坏文件原因码、降级计数）
src/testdeck/framework.py           # 框架识别（name → properties 键 → 文件名 → unknown）
src/testdeck/ingest.py              # 扫描发现 + 编排 + 摘要（机读/人读）+ dry-run 零副作用
src/testdeck/db.py                  # 四表 upsert（ON CONFLICT）+ schema v2（suites.time_ms 可空）
src/testdeck/cli.py                 # ingest 实装接线；NOT_READY 只留给未实装命令
src/testdeck/model.py               # seconds_to_ms 文档口径对齐（单项降级，不是 skipped）
bench/bench_ingest.py               # 改为消费生产解析器 + 保留基准侧独立重数 + 性能门测生产解析器
tests/test_junit.py                 # 解析器 28 例（含四类坏文件、参数化名、半进位、命名空间）
tests/test_framework.py             # 框架识别 9 例（真跑产物 + 无线索 → unknown）
tests/test_ingest.py                # 21 例：四表落库 / 幂等 / 摘要契约 / 三类坏文件 / dry-run 快照 / 退出码
tests/test_exit_codes.py            # 9 例：退役判据（行为断言 + AST 断言）
tests/test_db.py                    # upsert 幂等、缺失耗时写 NULL、schema 版本不符报错
tests/test_selftest.py              # 原 M0 版"返回 4"用例改成"断言退役"
plan/00,02,03,04,05,06 + README.md + data/README.md   # 状态与口径回写
tools/verify-layout-gate.py         # 变异 marker 跟着新缺口表重排（M2 关闭原 G1 后）
```

## 2. 下一棒待办（M3，按顺序）

1. **`tui/` 包 + `queries.py`**（`plan/03` 模块②）：
   - `queries.py` 只读 SQL：`tree_rows(run_id)` / `summary(run_id)` / `case_detail(run_id, case_id)` /
     `history(case_id, window)`，返回纯 dataclass/dict，**不返回 Textual 对象**；
   - **失败优先排序单点在 `queries.py`**：同父节点下 `fail_count > 0` 的子树在前；组内
     suite 按 `suites.suite_id`（XML 出现序）升序，class/name 按字典序；树与导出共用；
   - `app.py` 只装配控件与事件（`Tree` / summary `Static` / failure 原文 / `Sparkline` / `Footer`），
     大库查询走 `run_worker`；键位**全部**从 `keys.py` 取（AST 扫描禁止另写字面量）。
2. **失败优先树 + summary + failure 原文 + sparkline + 键位栏**接真实查询；
   **`F`/`S`/`D` 三视图在 M3 只需骨架但必须接真实查询**（死壳判据：只画标题不接查询即视为未交付）。
   分型（M4）与瀑布/回归（M5）的**口径**先别在 M3 里另写一份——骨架只做"取数 + 展示"。
3. **降级**：终端宽度 < `view.min_width_single_column`（`rules/view.json`）→ 单栏模式；
   `NO_COLOR=1` / 无真彩色 → 保留结构、颜色退化。两条都要有不依赖 Pilot 的快照/单元测试。
4. **`tui` 命令实装 + 退出码 4 对 `tui` 退役**：`NOT_READY` 分支此后只剩 `export`；
   `tests/test_exit_codes.py` 里的 `UNIMPLEMENTED` 常量要同步改成 `("export",)`。
5. **两条 AST 守门**（`plan/02` §一）：`tests/test_no_network.py`（禁网络模块与
   `importlib.import_module` 动态导入）与 `tests/test_layering.py`（判定层不得 import
   入口层/Textual、`queries.py` 不得 import `tui/`、`report_model.py` 不得 import Textual）；
   **两条都要做变异验证**（删掉 `app.py` 里对 `report_model` 的引用 → 守门必须红）。
6. **回写状态**：`plan/00` 台账行 + 里程碑表、`plan/05` §一、`plan/06` §二 + 缺口（G1 关闭）、
   `README.md` 状态表（四处一致）；`bench/run_all.py` 的 `CURRENT_MILESTONE` 见 §3 K33；
   然后写 `plan/HANDOFF-M4.md` 并跑布局门。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

> M0 的 K1–K16（见 `plan/HANDOFF-M1.md` §3）与 M1 的 K17–K25（见 `plan/HANDOFF-M2.md` §3）
> **全部继续有效**。M2 新增：

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K26 | run 身份**只从 XML 声明值读**（根/`testsuite` 的 `branch`/`commit[_sha]`/`ci_run_id`/`timestamp`）；读不到写空串。**没声明身份的产物因此全部归入同一个"未标注 run"**（三元组全空串）；`runs.framework` = 该 run 的框架集合（字典序逗号连接），`runs.source_path` = 展示路径字典序的**首个**产物 | `junit.py` + `ingest.py` | `test_junit.py` 的元数据三条、`test_ingest.py::test_identity_declared_in_xml_splits_runs` / `test_three_fixtures_fill_four_tables` |
| K27 | **单项缺失走"降级"，整文件坏才 skip**。文件级原因码只有四个：`bad_xml` / `bad_encoding` / `no_testsuite` / `unreadable`（分类顺序：字节层 → 缺根 → 坏结构）；单项降级码四个：`bad_time` / `missing_name` / `started_at_missing` / `bad_commit`。**缺 `name` 的 testcase 不落库，但仍计入元素重数** | `junit.py` | `test_junit.py::test_bad_*` / `test_nameless_case_is_degraded_but_still_counted`；`test_ingest.py::test_summary_reports_skipped_file_with_reason` |
| K28 | 元素重数**按标签分桶**（`failure`→failures、`error`→errors、`skipped`→skipped），四态再把 failure/error 合成 `fail`；耗时列缺失写 **NULL 不是 0**（`suites.time_ms` 因此可空） | `junit.py` + `db.py` DDL | `test_junit.py::test_error_element_maps_to_fail_but_counts_in_errors_bucket`、`test_db.py::test_missing_time_is_null_not_zero`、`bench` 的 `parser_vs_recount` |
| K29 | 退出码 4 **逐命令退役**：`ingest` 已退役（任何入参形态只能 0/2/3）；`NOT_READY` 只允许出现在**未实装命令**的分支里；**常量保留**（历史留档要能读） | `cli.py` + `exit_codes.py` | `tests/test_exit_codes.py` 三条（行为 + AST + 常量仍在） |
| K30 | 库 `SCHEMA_VERSION` 不符时**报错不静默复用**（exit 3 并提示删库重建）；当前 = 2 | `db.py` | `test_db.py::test_schema_version_mismatch_is_refused`、`test_ingest.py::test_old_schema_version_is_refused_not_silently_reused` |
| K31 | `ingest` 摘要**首行字段与顺序是契约**（`files/runs/cases/occurrences/skipped/framework`）；`skipped:`/`degraded:` 每个原因一行、按单点顺序；`--dry-run` 不建连接不建目录；入参不存在 = exit 2 且**一个都不写**；整批落**一个事务** | `ingest.py` | `test_ingest.py` 的摘要四条 + `test_dry_run_leaves_repo_and_default_db_untouched` |
| K32 | 基准**不得退化成"生产跟自己比"**：`bench_ingest` 消费生产解析器，但保留基准侧独立重数实现，`parser_vs_recount` 要求两者逐项相等；性能门计时的是**生产解析器** | `bench/bench_ingest.py` | `tests/test_bench_suites.py::test_bench_ingest_parses_streaming_counts`（基准侧实现仍在）+ 对账各条 |
| K33 | `bench/run_all.py:CURRENT_MILESTONE` 当前**仍是 1**（M2 未新增套件；它只影响打印标签与 `since` 判定，当前无 `since∈{2,3}` 的套件）。**M4 上线 `flaky` 套件时必须调到 4**；下一棒若想把标签对齐 M3 可以调到 3（不影响任何判定） | `bench/run_all.py` | `test_not_enabled_suite_is_not_a_pass`（monkeypatch 覆盖，不受影响） |

## 4. 本机环境坑（M2 实测补充）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**；项目 `requires-python >=3.9`，**一律 `py -3.12`**；
  中文输出加 `-X utf8`。
- `python` 是商店占位符 → 用 `py`。pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`。
- **`pytest` 靠 `pyproject` 的 `pythonpath = ["src"]` 才 import 得到 `testdeck`**；
  裸跑 `bench/*.py` / `data/synth/*.py` 没有这层，所以 `bench_ingest.py` 自己往
  `sys.path` 里补 `src/`（补法写在文件顶部）。
- **Python 下限 3.9**：不能用 `@dataclass(slots=True)`（3.10+）；也**不用 `RETURNING`**
  （要 SQLite ≥ 3.35）——upsert 后另发一条 SELECT 拿主键，别把 sqlite 版本当隐含依赖。
- fixture 的 `node_modules/`、`test-results/` 已被 `.gitignore` 挡掉（Playwright 会重造）。
- **`/tmp` 在 Git Bash 与 Windows Python 里不是同一个目录**：跨工具传路径用仓库内相对路径。
- **`os.path.relpath` 跨盘符抛 `ValueError`**（仓库在 `D:`、临时目录在 `C:`）：凡"展示用相对
  路径"都 try/except 回落原路径（`paths.relative_to_root` 已封好，直接用它）。
- 本机注册表代理会污染 pip：`NO_PROXY="*" no_proxy="*" py -3.12 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用
  `py -3.12` 以 `encoding="utf-8"` 回读。**M2 实测补充**：`grep -c` 之类对 UTF-8 文件计数
  也可能给出让人误解的结果——判据尽量落成 Python 断言或直接读文件。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**。`github.com` git 通道间歇失败，
  判据是"远端 sha == 本地 sha"，不是 push 退出码。

## 5. DoD 逐项 checklist（M3）

- [ ] `tui/` + `queries.py` 落地；`queries.py` 只读 SQL、不返回 Textual 对象
- [ ] 失败优先树 / summary / failure 原文 / sparkline / 键位栏接**真实查询**（死壳判据）
- [ ] `tests/test_tui_pilot.py`：纯键盘完成"进入 → 移到失败用例 → 读到 stack 首行"
- [ ] summary 各计数与直接 SQL 查询逐项相等
- [ ] 窄终端（< `min_width_single_column`）与 `NO_COLOR=1` 两条降级各有断言
- [ ] `tests/test_no_network.py` + `tests/test_layering.py` 在位且**各有变异验证**
- [ ] 键位字面量只出现在 `keys.py`（AST 扫描）
- [ ] `tui` 的 `NOT_READY(4)` 退役，`tests/test_exit_codes.py` 的未实装集合同步为 `("export",)`
- [ ] 四处状态副本回写一致；`plan/HANDOFF-M4.md` 落盘；布局门绿；布局门变异 7 组全红
- [ ] 全量 `pytest` 绿；`bench/run_all.py --suites ingest` 仍 exit 0；`check_topic.py` 无 FAIL
- [ ] 本轮**未接远端** → 留档写"本地等价校验（CI 待首推验证）"，不得写"CI 绿"

## 6. 关键命令速查

```bash
# 布局门（第一件事）
py -3.12 tools/check-sprint-layout.py
py -3.12 tools/verify-layout-gate.py          # 布局门自身的变异验证

# 测试 / 自检
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest -q
PYTHONPATH=src py -3.12 -m testdeck selftest

# M2 解析落库（本轮）
py -3.12 -m testdeck selftest
PYTHONPATH=src py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db bench/.tmp/demo.db
PYTHONPATH=src py -3.12 -m testdeck ingest bench/fixtures --glob "**/*.xml" --dry-run
py -3.12 bench/run_all.py --suites ingest     # 四通道对账 + 生产解析器性能（exit 0）
py -3.12 bench/run_all.py --probe             # 探活

# M1 数据面（仍是下面这些）
py -3.12 data/synth/gen_runs.py --check                       # 真值台账位级一致
py -3.12 bench/fixtures/regen_fixtures.py                     # 真跑三框架 fixture（需 go / node）
py -3.12 bench/fixtures/scan_leaks.py                         # 入库产物脱敏守门
py -3.12 bench/refimpl.py                                     # 参照实现独立复算台账

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .
```
