# HANDOFF-M5 · 下一棒 = 慢测试与回归 + 导出与门禁 + 录屏（M5）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（装订 + 计划套件 + 可运行骨架，2026-10-18）、M1（数据先行）、
M2（解析落库）、M3（三栏视图）、M4（flaky 分型 + 两次 run diff，均 2026-10-19）。**

| 项 | 证据（M4 本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿（文档 10 / 交接单 5 / 状态副本 4 / 里程碑 7） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` → 7 组变异全红、还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` → **375 passed**（M3 是 308）；连跑 8 次稳定 |
| flaky 分型逐值对账 | `py -3.12 bench/bench_flaky.py` → 7 项检查全过：22 锚点 + 50 样本 × 7 字段逐值相等；生产 vs 参照 72 条记录逐值相等；全语料 5000 条分型计数逐类相等 |
| `broken ∩ flaky == ∅` | 同上（`flaky/broken_flaky_exclusive`）→ 两份集合求交为空（broken 1 / flaky 22，都非空）；`force_flaky` 注入必红 |
| 两条降级 | 同上（`degrade_zero_counted` / `degrade_short_window`）→ 零计数样本落 `watch` 且 `fail_rate` 无定义；窗口不足一律 `watch` |
| 零字面量门禁 | `tests/test_no_rule_literals.py`（8 例）→ 判定层无阈值字面量；注入 `3` / `0.05` 必红；白名单穷尽式 |
| diff 三类对账 | `tests/test_diff.py`（24 例）→ 14 组状态对逐类断言；`fail→skip`/`fail→缺` 不判"修复"；接真实库对账 |
| summary 接分型 | `tests/test_queries.py` → `flaky`/`broken` 由 `flaky.py` 填（非 `None`）；summary 计数与矩阵行数同源 |
| 两套基准 | `py -3.12 bench/run_all.py --suites ingest,flaky` → 27 项检查全过，exit 0 |
| 探活 | `py -3.12 bench/run_all.py --probe` → 参照实现违规 import + ingest 两处 + flaky 两处注入全被报出，exit 0 |
| 自检 | `py -3.12 -m testdeck selftest` → exit 0（键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 20 个） |
| 真值台账位级一致 | `py -3.12 data/synth/gen_runs.py --check` → PASS（436804 字节；零计数 `fail_rate` 由 `"0"` 改为无定义） |
| 出题门 | `check_topic.py .`（只读）→ 无 FAIL |

**本轮交付/改动的文件**（相对路径）：

```
src/testdeck/flaky.py              # 判定层（新增）：classify + CaseProfile + label_counts
src/testdeck/diff.py               # 判定层（新增）：两次 run 三类分类（new-failures/fixed/still-failing）
src/testdeck/model.py              # 精确有理数渲染单点：as_fraction / render_exact / mean_fraction
src/testdeck/queries.py            # summary 的 flaky/broken 由 flaky.py 填；矩阵行序改 flaky_score 降序；
                                   #   MatrixRow 带 profile；新增 case_profiles / profile_summary_counts
src/testdeck/tui/view.py           # matrix_text 画分型标签；diff_text 改为 diff.py 三类分组；summary 色调
bench/bench_flaky.py               # 基准②（新增）：分型逐值对账 + 互斥独立断言 + 两条降级 + 探活
bench/refimpl.py                   # 零计数样本 fail_rate 由 Fraction(0) 改为 None（口径修正）
bench/run_all.py                   # CURRENT_MILESTONE 3 → 4；--probe 改为逐套件探活
data/synth/expect.json             # 重生成（零计数 fail_rate: "0" → null；436803 → 436804 字节）
tests/test_flaky.py                # 27 例：分母/transitions/分型顺序/两条降级/互斥独立断言
tests/test_diff.py                 # 24 例：三类逐类对账 + 边界（fail→skip 不是修复）+ 接真实库
tests/test_no_rule_literals.py     # 8 例：零字面量门禁 + 变异验证 + 白名单穷尽式
tests/test_queries.py              # 矩阵行序改 flaky_score；新增 summary 接分型用例
tests/test_view.py                 # matrix/diff 渲染用例改为 M4 口径
tests/test_bench_suites.py         # 新增 flaky 套件对账 + 探活 + M4 就绪用例
tests/test_bench_refimpl.py        # 零计数 fail_rate 断言改为 None
tests/test_layering.py             # queries.py 变异目标跟着 import 行改
tests/test_tui_pilot.py            # 新增 _wait_for_report（修全量 pytest 下的竞态，见 §4）
tests/conftest.py                  # 新增 bench_flaky fixture
plan/00,02,03,04,05,06 + README.md + data/README.md   # 状态与口径回写
```

## 2. 下一棒待办（M5，按顺序）

1. **`slow.py`（判定层纯函数，`plan/03` 模块④）**：
   - `percentile(values, p)`：线性插值，索引 `(n-1)*p`，`lo=floor`/`hi=ceil`，
     `lo==hi` 取该值，否则 `v[lo] + (v[hi]-v[lo])*(idx-lo)`；输入升序排序（稳定）；
     空样本 → `None`，单样本 → 该值；
   - 缺失耗时（`None`）**不补 0、不进样本**（K28）；
   - `regression(base_p50, curr_p50, rules)`：`curr/base >= ratio` **且** `curr-base >= delta_ms`，
     边界计入（`>=`）；`base_p50 == 0` → `undefined_base`，任一侧无样本 → `missing_window`
     （返回 `None`，不是 `False`）；
   - **阈值/分位数全部从 `rules/slow.json` 读**，代码里不得出现阈值字面量
     （`tests/test_no_rule_literals.py` 已把 `slow.py` 纳入扫描面）；
   - 瀑布条宽度 = `round(time_ms / max_time_ms * width)`（整数运算）。
2. **把 p50/p95 与回归判定接进 `S` 视图**：`view.slow_text` 现在只画耗时降序与比例条，
   M5 换成"每条用例的 p50/p95 + 回归标记"（口径在 `slow.py`，`queries.py` 只取数）。
3. **`export.py` + `render_md` / `render_json`（`plan/03` 模块⑤）**：
   - `report_model.py` 已有 `REPORT_FIELDS`（有序元组）与 `build_report`；M5 加 `render_md`
     / `render_json`，**只消费** `build_report` 的 dict（md 列序 = JSON 键序 = 字段声明序）；
   - JSON：`json.dumps(..., ensure_ascii=False, sort_keys=False, indent=2)` + 末尾换行；
     **不写生成时刻**、不含 `ingested_at`、不含绝对路径；
   - md：列顺序 = 字段声明序，单元格内 `|` / 换行转义；
   - 两次导出逐字节一致（`tests/test_export_determinism.py` 双跑 `cmp`）；
   - `cli.py` 的 `export` 分支实装（**退出码 4 对 `export` 退役**：`tests/test_exit_codes.py`
     的 `IMPLEMENTED` 加 `export`、`UNIMPLEMENTED` 清空；`cli.py` 的 `NOT_READY` 分支删除）。
4. **`--fail-on` 语义**：`flaky`（分型 flaky 数 > 0）/ `new-failures`（`diff.new_failure_count > 0`）/
   `regressions`（回归清单非空）→ 命中 exit 1；未知值 / 缺参数 → argparse exit 2；
   库不存在 / 无 run → exit 3。判定**只读模型**，不重新查库。
5. **`bench/bench_slow.py` + `bench/bench_export.py` 上线**，把
   `bench/run_all.py:CURRENT_MILESTONE` 调到 **5**；两套件各自带 `_probe`。
6. **录屏**：`docs/demo/demo.gif`（`textual run --dev` + 终端录屏，时长 ≤ 30s）；
   录屏时一并复核真终端（字体/尺寸/ConPTY）——这是 `plan/05` §五 与 `plan/06` G6 的关闭条件。
7. **回写状态**：`plan/00` 台账行 + 里程碑表、`plan/05` §一 + 退役表（`export` 退役）、
   `plan/06` §二 + 缺口（G1/G2/G3/G6 关闭）、`README.md` 状态表（四处一致）；
   然后写 `plan/HANDOFF-M6.md` 并跑布局门。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

> M0 的 K1–K16（`plan/HANDOFF-M1.md` §3）、M1 的 K17–K25（`plan/HANDOFF-M2.md` §3）、
> M2 的 K26–K33（`plan/HANDOFF-M3.md` §3）、M3 的 K34–K47（`plan/HANDOFF-M4.md` §3）
> **全部继续有效**。M4 新增：

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K48 | **零计数样本的 `fail_rate` 记"无定义"（`None`），不是 `"0"`**：`"0"` 与"跑过且从没失败"（stable）在数值上撞车，正是 K34 要禁的误导。`model.mean_fraction(x, 0)` → `None`；参照实现同步（`bench/refimpl.py`）并重生成台账 | `model.py` + `flaky.py` + `bench/refimpl.py` | `tests/test_flaky.py::test_zero_counted_sample_falls_to_watch_not_stable`、`test_bench_refimpl.py::test_zero_counted_runs_is_watch_not_stable`、`bench_flaky.py:degrade_zero_counted` |
| K49 | **分型顺序先判恒失败，但互斥靠独立断言**：`fail_rate == 1` → `broken` 在 `flaky` 之前；`broken ∩ flaky == ∅` 另拿两份集合求交（不靠顺序自证） | `flaky.py` | `test_flaky.py::test_broken_and_flaky_sets_are_disjoint_independently` / `test_flaky_broken_excluded`、`bench_flaky.py:broken_flaky_exclusive` |
| K50 | **`flaky_score = transitions / (n - 1)`，`n < 2` → `0`**；表达式用 `> 1` 而非 `< 2`，避免与阈值字面量撞车（零字面量门禁） | `flaky.py` | `test_flaky.py::test_flaky_score_of_fewer_than_two_counted_runs_is_zero`、`test_no_rule_literals.py` |
| K51 | **`diff` 的"修复"要求 `after == pass`**：`fail→skip` / `fail→缺` 落 `unchanged`，**不是** `fixed`（没有 pass 就没有修好的证据） | `diff.py` | `test_diff.py::test_fixed_requires_after_pass_not_skip_or_missing`、`test_diff_reverses_to_unchanged` |
| K52 | **`diff` 的缺行（`None`）不等于任何状态**：`缺→fail` 是 `new-failures`，`fail→缺` 落 `unchanged` | `diff.py` | `test_diff.py::test_diff_against_future_run_reports_new_failures` 与 `classify` 参数化矩阵 |
| K53 | **矩阵行序 = `flaky_score` 降序，同分按 `(suite_name, classname, name)`**：判定在 `flaky.py`，`queries.matrix_rows` 只排序与挂载，不复制判定 | `queries.py` + `flaky.py` | `test_queries.py::test_matrix_rows_are_raw_statuses` |
| K54 | **summary 的 `flaky`/`broken` 与矩阵行数同源**：都取 `case_profiles(窗口=view.sparkline_runs)` 的同一份判定；`slow` 仍 `None`（K37 收窄到只剩 `slow`） | `queries.py` | `test_queries.py::test_flaky_and_broken_summary_fields_come_from_flaky_py`、`test_pending_summary_fields_are_none_not_guessed` |
| K55 | **判定层零阈值字面量**：`flaky.py`/`slow.py`/`report_model.py` 的数值常量不得等于规则包里任一阈值；豁免 `0`/`1` 且白名单**穷尽式** | `tests/test_no_rule_literals.py` | 该文件 8 条（含注入 `3` / `0.05` 必红） |
| K56 | **`--probe` 逐套件探活**：`run_all.py` 对每个"已就绪且被选中"的套件都跑它自己的 `_probe`；套件没实现 `_probe` 时跳过（不冒充探过） | `bench/run_all.py` | `test_bench_suites.py::test_probe_reports_all_detected` + 各套件的 `_probe` 用例 |
| K57 | **Pilot 测试必须等"报告真的到了"**：`on_mount` 取数走 worker 线程，一次 `pause()` 在满负载下不足；`test_tui_pilot.py` 用 `_wait_for_report` 轮询 `app.report` | `tests/test_tui_pilot.py` | 删掉 `_wait_for_report` → 全量 pytest 下 `nav_nodes` 偶发为空（不是变红，是**间歇性**红） |

## 4. 本机环境坑（M4 实测补充）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**；项目 `requires-python >=3.9`，**一律 `py -3.12`**；
  中文输出加 `-X utf8`。
- `python` 是商店占位符 → 用 `py`。pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`。
- `textual` 8.2.8 + `rich` 15.0.0 已装；`NO_PROXY="*" no_proxy="*"` + 清华镜像装包。
- **Textual 8.x 键名**：`/` 写 `slash`、`?` 是 `question_mark`、`Enter` 是 `enter`、`Esc` 是 `escape`。
- **`Static` 读内容用 `.content`**（旧版 `.renderable` 已无）；`textual.worker_manager`（不是 `textual.workers`）。
- **worker 线程回投的竞态（M4 实测踩到）**：`on_mount` 里 `@work(thread=True)` 取数，
  `await pilot.pause()` 一次在满负载下**不足**以保证 `ReportLoaded` 已回投——
  表现为全量 pytest 下 `test_tui_pilot.py` 的 `app.nav_nodes` / `app.report` **偶发为空**
  （单独跑 `tests/test_tui_pilot.py` 又全绿）。修法：`_wait_for_report` 轮询 `app.report`。
  **M4 把 `case_profiles` 加进 worker 后这个既有竞态被放大**——遇到"单跑绿、全量偶发红"先怀疑它。
- **`os.path.relpath` 跨盘符抛 `ValueError`**：凡"展示用相对路径"都 try/except（`paths.relative_to_root` 已封好）。
- **行尾（实测坑）**：本仓 `.gitattributes` 是 `* text=auto eol=lf`；改写文件后工作树里**可能变 CRLF**，
  后果是 `tools/verify-layout-gate.py` 的 `delete_line` 变异**直接崩**（`"\n".split()` 逐行比对，
  CRLF 行带 `\r` → "删行后字节未变"）。收尾前先扫：
  `py -3.12 -c "import glob;print([f for f in glob.glob('**/*.md',recursive=True) if open(f,'rb').read().count(b'\r\n')])"`
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用 `py -3.12` 以
  `encoding="utf-8"` 回读，或直接读文件。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**。`github.com` git 通道间歇失败，
  判据是"远端 sha == 本地 sha"，不是 push 退出码。
- **本机默认库** `~/.local/share/testdeck/testdeck.db` 已有数据：它是环境事实，不是仓库内容；
  `git status` 看不到它。**别把它当判据**。

## 5. DoD 逐项 checklist（M5）

- [ ] `slow.py` 落地：`percentile` 线性插值（索引 `(n-1)*p`）；缺失耗时不补 0、不进样本
- [ ] `regression`：`>=` 边界计入；`base_p50 == 0` → `undefined_base`（返回 `None` 不谎报"无回归"）
- [ ] `slow.py` 里**不得出现阈值字面量**（`tests/test_no_rule_literals.py` 已纳入扫描面）
- [ ] `S` 视图接 p50/p95 与回归判定（不再是"只有耗时降序"）
- [ ] `export.py` + `render_md` / `render_json` 落地；md 列序 = JSON 键序 = `REPORT_FIELDS`
- [ ] 两次导出逐字节一致；不含 `ingested_at` / 绝对路径 / 生成时刻
- [ ] `--fail-on` 三种值命中 → exit 1；未知值 → 2；库/run 不可用 → 3；判定只读模型
- [ ] `cli.py` 的 `export` 实装；**退出码 4 对 `export` 退役**（`test_exit_codes.py` 的 `IMPLEMENTED` 含 `export`、`UNIMPLEMENTED` 清空、`NOT_READY` 分支删除）
- [ ] `bench/bench_slow.py` + `bench/bench_export.py` 上线；`CURRENT_MILESTONE` 调到 **5**；两套件各带 `_probe`
- [ ] `bench/run_all.py --suites ingest,flaky,slow,export` exit 0；`--probe` 四套件注入全检出
- [ ] `docs/demo/demo.gif` 入库（时长 ≤ 30s）；真终端（字体/尺寸/ConPTY）复核
- [ ] 四处状态副本回写一致；`plan/HANDOFF-M6.md` 落盘；布局门绿；布局门变异 7 组全红
- [ ] 全量 `pytest` 绿（连跑多次确认不间歇）；`check_topic.py` 无 FAIL
- [ ] 本轮**未接远端** → 留档写"本地等价校验（CI 待首推验证）"，不得写"CI 绿"

## 6. 关键命令速查

```bash
# 布局门（第一件事）
py -3.12 tools/check-sprint-layout.py
py -3.12 tools/verify-layout-gate.py          # 布局门自身的变异验证

# 测试 / 自检
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest tests/test_tui_pilot.py -q   # 无头键盘全流程
PYTHONPATH=src py -3.12 -m testdeck selftest

# M4 分型与 diff（本轮）
py -3.12 bench/bench_flaky.py                 # 分型逐值对账（exit 0）
py -3.12 bench/bench_flaky.py --probe         # flaky 套件探活
py -3.12 bench/run_all.py --suites ingest,flaky   # 两套基准（exit 0）
py -3.12 bench/run_all.py --probe             # 全部注入（exit 0）

# M3 三栏视图（仍是这些）
PYTHONPATH=src py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db bench/.tmp/demo.db
PYTHONPATH=src py -3.12 -m testdeck tui --db bench/.tmp/demo.db      # 需真终端

# M1 数据面（仍是下面这些）
py -3.12 data/synth/gen_runs.py --check                       # 真值台账位级一致
py -3.12 bench/fixtures/regen_fixtures.py                     # 真跑三框架 fixture（需 go / node）
py -3.12 bench/fixtures/scan_leaks.py                         # 入库产物脱敏守门
py -3.12 bench/refimpl.py                                     # 参照实现独立复算台账

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .
```
