# HANDOFF-M6 · 下一棒 = 脱敏、tag、GitHub Release、发布留档（M6）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（装订 + 计划套件 + 可运行骨架，2026-10-18）、M1（数据先行）、
M2（解析落库）、M3（三栏视图）、M4（flaky 分型 + diff）、M5（慢测试与回归 + 导出与门禁 + 录屏，
均 2026-10-19）。**

| 项 | 证据（M5 本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿（文档 10 / 交接单 6 / 状态副本 4 / 里程碑 7） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` → 7 组变异全红、还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` → **474 passed**（M4 是 375）；连跑 3 次稳定 |
| 分位数/回归逐值对账 | `py -3.12 bench/bench_slow.py` → 8 项检查全过：22 锚点 + 50 样本 × 5 字段逐值相等；生产 vs 参照 72 条逐值相等；全语料 5000 条回归三态计数逐项相等 |
| 回归边界六种 | 同上（`slow/regression_boundaries`）→ 八锚点逐项相符，**True/False/None 三态齐全**（防恒真/恒假） |
| 缺失耗时口径可证伪 | 同上（`slow/missing_time_not_zero`）→ 缺失 p50=150 != 补 0 的 p50=100 |
| 不可判不谎报 | 同上（`slow/undefined_is_none_not_false`）→ `undefined_base`/`missing_window` 都返回 `None` |
| 导出字段一致 + 逐字节一致 | `py -3.12 bench/bench_export.py` → 8 项检查全过（md 列序 = JSON 键序 = 声明序；两次渲染逐字节一致） |
| `--fail-on` 退出码 | 同上（`export/fail_on_exit_codes`）+ `tests/test_export.py` → 三种值 × 命中/干净六例相符；**门禁只读模型** |
| 四套件总账 | `py -3.12 bench/run_all.py` → **43 项检查全过，exit 0**（四套件全就绪，无 `not_enabled`） |
| 探活 | `py -3.12 bench/run_all.py --probe` → 参照实现违规 import + ingest 两处 + flaky 两处 + slow 两处 + export 四处**全被报出**，exit 0 |
| 零字面量门禁 | `tests/test_no_rule_literals.py`（9 例）→ 三个判定/表示层文件全在扫描面；注入 `3`/`0.05`/`200` 必红 |
| 退出码 4 全面退役 | `tests/test_exit_codes.py` → `export` 任何入参形态不返回 4；`cli.py` 里**已无返回 4 的分支**（AST 断言） |
| 分层守门 | `tests/test_layering.py`（6 例）→ 9 条 LAYER_RULES 逐条可命中；注入表与 `LAYER_RULES` 同步断言 |
| `S` 视图接判定 | `tests/test_tui_pilot.py` + `tests/test_queries.py` → 面板带 `p50=`/`p95=`/`reg=`；两次 run 真库上 1000→1500ms 判回归 |
| 录屏 | `py -3.12 tools/make-demo-gif.py --check` → `docs/demo/demo.gif`：8 帧 / **24.0s**（≤30s）；`tests/test_demo_gif.py`（9 例） |
| 自检 | `py -3.12 -m testdeck selftest` → exit 0（键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 22 个） |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` → PASS（436804 字节） |
| 出题门 | `check_topic.py .`（只读）→ 无 FAIL |

**本轮交付/改动的文件**（相对路径）：

```
src/testdeck/slow.py               # 判定层（新增）：percentile/p50/p95 + regression 三态 + bar_width
                                   #   + profile_case/SlowProfile + sample_label/is_slow/regression_list
src/testdeck/export.py             # 编排层（新增）：模型 → md/json + --fail-on 门禁（只读模型）
src/testdeck/report_model.py       # 加 render_md/render_json/render + gate_hits + REGRESSION_FIELDS
                                   #   + build_report 扩出 profiles/slow/regressions/diff
src/testdeck/queries.py            # summary 的 slow 由 slow.py 填；slow_rows/slow_profiles 挂画像；
                                   #   PENDING_SUMMARY_FIELDS 收空（六字段全实装）
src/testdeck/tui/view.py           # slow_text 改 p50/p95 + 回归三态 + slow.bar_width；summary 文案
src/testdeck/tui/app.py            # S 视图标题 + `e` 的提示文案（导出已实装）
src/testdeck/cli.py                # export 实装接线；NOT_READY 分支删除；LAYER_RULES 加 export.py
bench/bench_slow.py                # 基准③（新增）：分位数/回归逐值对账 + 边界六种 + 两条硬断言 + 探活
bench/bench_export.py              # 基准④（新增）：字段序/逐字节一致/门禁退出码 + 探活（合成模型，不碰库）
bench/run_all.py                   # CURRENT_MILESTONE 4 → 5；--probe 逐套件参数分派
tools/make-demo-gif.py             # 录屏产出（新增）：Textual SVG 渲染输出 → Pillow 栅格化 → GIF
docs/demo/demo.gif                 # 入库（8 帧 / 24.0s）
docs/demo/README.md                # 录屏口径说明（如实：渲染输出，不是真终端字节流）
tests/test_slow.py                 # 34 例：分位数插值/缺失耗时/回归边界/两条降级/条宽整数运算
tests/test_export.py               # 26 例：字段序一致/逐字节/门禁语义/退出码/转义/分层
tests/test_export_determinism.py   # 7 例：双跑 cmp + 换连接稳定 + 不读时钟
tests/test_demo_gif.py             # 9 例：文件在/帧>1/≤30s/栅格化管线/帧计划覆盖三视图
tests/test_queries.py              # 加两次 run 真库回归对账 + 单 run single_sample；PENDING 收空
tests/test_view.py                 # slow_text 用例改 M5 口径
tests/test_tui_pilot.py            # S 视图断言 p50/p95/reg（不再是"只有耗时降序"）
tests/test_exit_codes.py           # 20 例：IMPLEMENTED 三条全含、UNIMPLEMENTED 清空；断言"无 NOT_READY 分支"
tests/test_selftest.py             # 加 export 退役用例
tests/test_no_rule_literals.py     # 扫描面三文件齐 + 加 slow 阈值注入变异
tests/test_layering.py             # 注入表与 LAYER_RULES 同步断言（加 export.py）
tests/test_keys_single_source.py   # 豁免表加 ("slow.py","?")（回归三态渲染）
tests/test_bench_suites.py         # 40 例：加 slow/export 套件对账与探活 + 四套件全就绪用例
tests/conftest.py                  # 加 bench_slow / bench_export fixture
tests/test_report_model.py         # build_report 形状扩为新键集
plan/00,02,03,04,05,06 + README.md + data/README.md   # 状态与口径回写
```

## 2. 下一棒待办（M6，按顺序）

> **M6 是本项目的收尾棒**：`plan/05` §三 写明"收尾棒（M6）也必须写 `HANDOFF-M6.md`"，
> 所以本轮已把本文件落盘（它同时是 M6 的交接单与 M5 的收尾记录）。

1. **干净环境验证**：`git clone --no-local`（或 `git archive` 解包）→ 新 venv →
   按 `README.md` 逐条跑 → **逐条记退出码与语义**（两条通路：裸 `testdeck` 与
   `python -m testdeck`）。注意：`pip install` 失败先加 `NO_PROXY="*"` 与清华镜像。
2. **脱敏四步**（`plan/05` §四.2）：源码常量 / 文档 / 产物 / **提交元数据**
   （作者与 tagger 邮箱）各扫一遍；本仓白名单只有 `yuluo554@users.noreply.github.com`
   形态。已有可跑守门：`bench/fixtures/scan_leaks.py`（fixture 面）；
   文档面用 `py -3.12` 以 `encoding="utf-8"` 回读扫（本机 grep 中文会乱码）。
3. **建仓与首推**：`gh repo create yuluo554/testdeck --public` → `git remote add origin ...`
   → push main → 等 CI 绿。**判据是"远端 sha == 本地 sha"**，不是 push 退出码
   （`github.com` git 通道间歇 `Failed to connect`）。
4. **tag + Release**：annotated tag `v0.1.0`；附件口径 = **手工源码包**
   （`python -m build --sdist`），sha256 **只写进 Release 正文**（写进包内文档会立刻失效）。
   tag 之后**不得再改代码面**（AGENTS.md 禁止条）。
5. **发布留档** `plan/RELEASE-M6.md`：§一 tag 前事实 / §二 tag 后追加事实 / §三 阶段 7
   覆盖对账表（逐条：**实现 / 不适用+理由 / 待首推**）。布局门会逐条核这张表
   （两栏小节 + 覆盖对账小节 + 三态行 ≥3），**M6 完成后它是硬门**。
6. **发布物本体复核**（`plan/05` §四.6）：真下载到中立目录 → `sha256sum -c` →
   解包树 vs `git archive <tag>` 解包树 `diff -r` → 在解包目录之外装并跑 `testdeck selftest`。
7. **CI 回填**：`plan/05` §五 的"CI 实跑未发生"与"跨版本行为差"两项在首推后回填**真实 run id**。
   **M5 已把四套基准全部上线**，`bench/run_all.py` 不带参数即可 exit 0——M6 应把
   `bench/run_all.py` 接进 CI 步骤（`plan/05` §五 的"bench 未接入 CI"一项的关闭条件）。
8. **D8–D10 决策收尾**：`plan/06` §四 的 D8（发布附件口径）/ D9（仓库名与可见性）/
   D10（录屏格式）此刻仍是"待确认"——M6 前必须逐项落成"用户确认"或"明确写不适用+理由"。
9. **最后**：回写四处状态（M6 那行翻 ✅）、跑布局门（此时 `LAYOUT.RELEASE` 生效）+
   布局门变异 + 全量 pytest + `check_topic.py`。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

> M0 的 K1–K16（`plan/HANDOFF-M1.md` §3）、M1 的 K17–K25（`plan/HANDOFF-M2.md` §3）、
> M2 的 K26–K33（`plan/HANDOFF-M3.md` §3）、M3 的 K34–K47（`plan/HANDOFF-M4.md` §3）、
> M4 的 K48–K57（`plan/HANDOFF-M5.md` §3）**全部继续有效**。M5 新增：

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K58 | **分位数线性插值**：索引 `(n-1)*p`，`lo=floor`/`hi=ceil`，`lo==hi` 取该值，否则 `v[lo]+(v[hi]-v[lo])*(idx-lo)`；输入按值升序（稳定）；空样本 → `None`、单样本 → 该值。`p` 一律走 `model.as_fraction`（**不用 float**） | `slow.py` | `tests/test_slow.py` 六条 + `bench_slow.py:slow/*_vs_expected` |
| K59 | **缺失耗时（`None`）不进样本、不补 0**（K28 在分位数上的延伸）：`slow.samples` 先剔 `None`；全缺失 → p50 无定义（`None`，不是 0） | `slow.py` | `test_slow.py::test_missing_time_is_excluded_not_zero` / `test_missing_time_changes_percentile_versus_zero_fill`、`bench_slow.py:slow/missing_time_not_zero` |
| K60 | **回归判定两处边界都计入**：`curr/base >= ratio` **且** `curr-base >= delta_ms`；全程精确 `Fraction` | `slow.py` | `test_slow.py` 五条边界 + `bench_slow.py:slow/regression_boundaries` |
| K61 | **"不可判"返回 `None` 而不是 `False`**：`base==0 → undefined_base`、任一侧无样本 → `missing_window`。把"判不了"当成"无回归"会让 CI 门禁在样本不足时静默放行 | `slow.py` | `test_slow.py::test_regression_undefined_base_is_not_a_verdict`、`bench_slow.py:slow/undefined_is_none_not_false` |
| K62 | **切分点由输入侧给出，判定层不发明**：台账显式存 `regression_split`；库里按**窗口中点**（`len(window)//2`）切——那是编排层的取数决定。`split` 为 `None`/越界 → 没有回归窗口（`base`/`curr` 都 `None`） | `slow.py` + `queries.py` | `bench_slow.py:_split_of` + `test_queries.py::test_slow_profiles_detect_regression_on_real_store` |
| K63 | **两条样本量降级**：总样本 0 或回归窗口任一侧无样本 → `insufficient_history`；总样本恰 1 → `single_sample`（p50 == p95） | `slow.py` | `test_slow.py` 三条降级用例 |
| K64 | **瀑布条宽度整数运算**：`divmod` + "余数加倍与除数比较"做四舍五入（不走浮点除法、不用 `round()`——银行家舍入在 `.5` 边界不同）；`max==0` → 全宽 0 | `slow.py` | `test_slow.py::test_bar_width_is_integer_arithmetic` / `test_bar_width_rounds_half_up_not_bankers` |
| K65 | **summary 的 `slow` = 本 run 有耗时声明且 ≥ `slow_ms` 的用例数**；`None`（没声明耗时）不算慢。判定只调 `slow.is_slow`，阈值取自规则包 | `queries.slow_summary_count` + `slow.is_slow` | `test_queries.py::test_pending_summary_fields_are_not_guessed` |
| K66 | **`PENDING_SUMMARY_FIELDS` 收空（六字段全实装）**：M5 起没有任何 summary 字段是"待实装"的 `None` | `queries.py` | `test_queries.py::test_pending_summary_fields_are_not_guessed`（断言集合为空且六字段全有值） |
| K67 | **导出键序 = 字段声明序**：`json.dumps(sort_keys=False)` + 末尾换行；md 列序 = `REPORT_FIELDS`。`RUN_FIELDS`/`REGRESSION_FIELDS` 同样是有序元组 | `report_model.py` | `test_export.py::test_render_json_key_order_matches_report_fields` / `test_render_md_column_order_matches_report_fields`、`bench_export.py:export/json_key_order` / `export/md_column_order` |
| K68 | **两次导出逐字节一致**：不写生成时刻（`write_generated_at` 为 true 时 `load_view_rules` 直接报错）、不含 `ingested_at`、不含绝对路径 | `report_model.py` + `rules/view.json` | `test_export_determinism.py`（双跑 `cmp` + 不读时钟）、`test_export.py::test_export_contains_no_generated_at_or_absolute_path` |
| K69 | **md 单元格转义**：`\|` → `\\\|`、换行 → `<br>`、`None` → `—`（不破坏表格） | `report_model._cell` | `test_export.py::test_md_cell_escapes_pipe_and_newline`、`bench_export.py:export/md_escaping` |
| K70 | **`--fail-on` 判定只读模型**：结论全取自 `build_report` 的 dict（`gate_hits`），**不重新查库**——保证"CI 拦下来的"就是"屏幕上看到的" | `report_model.gate_hits` + `export.py` | `test_export.py::test_gate_never_requeries_db`、`bench_export.py:export/gate_reads_model_only` |
| K71 | **`export` 退出码**：命中 → 1（并在 stderr 写命中原因）；未命中 → 0；未知 `--format`/`--fail-on` → 2（argparse `choices`）；库不存在 / 无 run / `--run` 不存在 → 3 | `export.py` + `cli.py` | `test_export.py` 四条 + `test_exit_codes.py::test_export_never_returns_not_ready` |
| K72 | **退出码 4 全面退役**：`ingest`(M2)/`tui`(M3)/`export`(M5) 全部实装后，`cli.py` 里**不得再有返回 4 的分支**；常量保留在 `exit_codes.py` | `cli.py` + `exit_codes.py` | `test_exit_codes.py::test_cli_has_no_not_ready_branch_left`（AST 断言 `branches == []`） |
| K73 | **零字面量门禁的扫描面必须完整**：`flaky.py` / `slow.py` / `report_model.py` 三份都要在（缺一即红）；豁免只有 `0`/`1`，且**穷尽式** | `tests/test_no_rule_literals.py` | 该文件 9 条（含 `slow.py` 阈值注入变异） |
| K74 | **`--probe` 逐套件探活**（K56 在四套件上的收尾）：每个"已就绪且被选中"的套件都跑自己的 `_probe`；参数分派按套件名（`export` 不读台账） | `bench/run_all.py` | `test_bench_suites.py::test_probe_reports_all_detected` + 各套件 `_probe` 用例 |
| K75 | **录屏是"渲染输出"而不是"真终端字节流"**：`demo.gif` 由 `tools/make-demo-gif.py` 从 Textual 的 `App.export_screenshot()` SVG 栅格化产出。**不得**把它写成"真终端已验证"（真终端表现是 G6，未关闭） | `tools/make-demo-gif.py` + `docs/demo/README.md` | `tests/test_demo_gif.py` 9 例（存在/帧>1/≤30s/管线可证伪/帧计划覆盖三视图） |
| K76 | **录屏帧计划 ≤ 30s 是机器判据**：`len(FRAMES) × SETTLE_FRAMES × FRAME_MS ≤ 30s`——改帧计划时这条会红，不靠人记 | `tools/make-demo-gif.py` | `test_demo_gif.py::test_frame_plan_stays_under_the_time_budget` |

## 4. 本机环境坑（M5 实测补充）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**；项目 `requires-python >=3.9`，**一律 `py -3.12`**；
  中文输出加 `-X utf8`。
- `python` 是商店占位符 → 用 `py`。pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`。
- `textual` 8.2.8 + `rich` + `Pillow 12.3.0` + `numpy 2.5.4` 已装；**本轮未装任何新包**
  （用户要求：不往 C 盘下载，C 盘曾爆满）。装包一律 `NO_PROXY="*" no_proxy="*"` + 清华镜像。
- **本机没有真终端录制工具链**（M5 实测）：标准库**无** `pty` / `termios`（Windows）；
  `winpty` 在非 tty 下直接 `Assertion failed: ... winpty.cc line 924`；
  `asciinema` / `agg` / `pyte` / `wcwidth` / `cairosvg` 都不在。
  → **不要**再试"抓 ConPTY 字节流"这条路，除非先装工具（本轮禁止）。
- **`App.export_screenshot()` 是 TUI 渲染输出的权威来源**：它渲染的正是
  `App.run()` 会画到终端上的同一份 `Screen._compositor.render_update()`（序列化成 SVG）。
  SVG 结构：`<style>` 里 `.terminal-<id>-r<n> {fill; font-weight}`；`</defs>` 之后依次是
  `<rect>`（背景，带 `fill`）+ `<g>` + `<text class=... x= y= textLength= ...>`。
  **`y` 是基线**（PIL 用 `anchor="ls"` 对齐）。
- **Rich SVG 里有一个"画布标题"** `<text class="terminal-*-title" ...>`：它按 `y=27`
  画在内容第一行上，会与 App 自己的 Header **重叠**（实测踩过：动图里出现两层标题）。
  栅格化时必须跳过它；`export_screenshot(title="")` 也去不掉（实测）。
- **字体度量（M5 实测）**：系统里 **SimSun**（`simsun.ttc`）ASCII 与 CJK **恰好 2:1**
  （10px / 20px @20px），与终端等宽网格一致——不需要 `wcwidth`。
  **`simsunb.ttf` 不是 SimSun 的粗体**，是 **SimSun-ExtB**（只有罕见扩展区汉字）：
  常用汉字会渲染成豆腐块（实测）。粗体改用同字体 + 描边模拟。
- **Textual 8.x 键名**：`/` 写 `slash`、`?` 是 `question_mark`、`Enter` 是 `enter`、
  `Esc` 是 `escape`。`Static` 读内容用 `.content`。`textual.worker_manager`（不是 `workers`）。
- **worker 线程回投的竞态**（M4 踩到，M5 沿用）：`on_mount` 取数走 worker，一次
  `await pilot.pause()` 在满负载下不足；`tests/test_tui_pilot.py` 用 `_wait_for_report`
  轮询 `app.report`。**"单跑绿、全量偶发红"先怀疑它。**
- **`os.path.relpath` 跨盘符抛 `ValueError`**：凡"展示用相对路径"都 try/except
  （`paths.relative_to_root` 已封好）。
- **行尾（实测坑）**：本仓 `.gitattributes` 是 `* text=auto eol=lf`；改写文件后工作树里
  **可能变 CRLF**，后果是 `tools/verify-layout-gate.py` 的 `delete_line` 变异**直接崩**。
  收尾前先扫：
  `py -3.12 -c "import glob;print([f for f in glob.glob('**/*.md',recursive=True) if open(f,'rb').read().count(b'\r\n')])"`
  （`docs/demo/demo.gif` 是 binary，已在 `.gitattributes` 里标 `*.gif binary`。）
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用
  `py -3.12` 以 `encoding="utf-8"` 回读，或直接读文件。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**。`github.com` git 通道间歇失败，
  判据是"远端 sha == 本地 sha"，不是 push 退出码。
- **本机默认库** `~/.local/share/testdeck/testdeck.db` 已有数据：它是环境事实，不是仓库内容；
  `git status` 看不到它。**别把它当判据**。演示库 `bench/.tmp/demo.db` **不入仓**（.gitignore）。

## 5. DoD 逐项 checklist（M5）

- [x] `slow.py` 落地：`percentile` 线性插值（索引 `(n-1)*p`）；缺失耗时不补 0、不进样本
- [x] `regression`：`>=` 边界计入；`base_p50 == 0` → `undefined_base`（返回 `None` 不谎报"无回归"）
- [x] `slow.py` 里**不得出现阈值字面量**（`tests/test_no_rule_literals.py` 已纳入扫描面）
- [x] `S` 视图接 p50/p95 与回归判定（不再是"只有耗时降序"）
- [x] `export.py` + `render_md` / `render_json` 落地；md 列序 = JSON 键序 = `REPORT_FIELDS`
- [x] 两次导出逐字节一致；不含 `ingested_at` / 绝对路径 / 生成时刻
- [x] `--fail-on` 三种值命中 → exit 1；未知值 → 2；库/run 不可用 → 3；判定只读模型
- [x] `cli.py` 的 `export` 实装；**退出码 4 对 `export` 退役**（`test_exit_codes.py` 的 `IMPLEMENTED` 含 `export`、`UNIMPLEMENTED` 清空、`NOT_READY` 分支删除）
- [x] `bench/bench_slow.py` + `bench/bench_export.py` 上线；`CURRENT_MILESTONE` 调到 **5**；两套件各带 `_probe`
- [x] `bench/run_all.py --suites ingest,flaky,slow,export` exit 0；`--probe` 四套件注入全检出
- [x] `docs/demo/demo.gif` 入库（时长 ≤ 30s）；真终端（字体/尺寸/ConPTY）复核 → **未验，G6 未关闭（如实登记）**
- [x] 四处状态副本回写一致；`plan/HANDOFF-M6.md` 落盘；布局门绿；布局门变异 7 组全红
- [x] 全量 `pytest` 绿（连跑多次确认不间歇）；`check_topic.py` 无 FAIL
- [x] 本轮**未接远端** → 留档写"本地等价校验（CI 待首推验证）"，不得写"CI 绿"

## 6. 关键命令速查

```bash
# 布局门（第一件事）
py -3.12 tools/check-sprint-layout.py
py -3.12 tools/verify-layout-gate.py          # 布局门自身的变异验证

# 测试 / 自检
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest tests/test_tui_pilot.py -q   # 无头键盘全流程
PYTHONPATH=src py -3.12 -m testdeck selftest

# M5 慢测试与导出（本轮）
py -3.12 bench/bench_slow.py                  # p50/p95 + 回归边界（exit 0）
py -3.12 bench/bench_slow.py --probe
py -3.12 bench/bench_export.py                # 字段一致 + 逐字节一致 + 门禁退出码（exit 0）
py -3.12 bench/bench_export.py --probe
py -3.12 bench/run_all.py                     # 四套件 43 项检查（exit 0）
py -3.12 bench/run_all.py --probe             # 逐套件探活（exit 0）

# 导出（真库上跑）
PYTHONPATH=src py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db bench/.tmp/demo.db
PYTHONPATH=src py -3.12 -m testdeck export --db bench/.tmp/demo.db --format md
PYTHONPATH=src py -3.12 -m testdeck export --db bench/.tmp/demo.db --fail-on regressions

# 录屏（渲染输出 → GIF）
py -3.12 tools/make-demo-gif.py               # 写 docs/demo/demo.gif（≤30s）
py -3.12 tools/make-demo-gif.py --check

# M3 三栏视图（仍是这些）
PYTHONPATH=src py -3.12 -m testdeck tui --db bench/.tmp/demo.db      # 需真终端

# M1 数据面（仍是下面这些）
py -3.12 data/synth/gen_runs.py --check                       # 真值台账位级一致
py -3.12 bench/fixtures/regen_fixtures.py                     # 真跑三框架 fixture（需 go / node）
py -3.12 bench/fixtures/scan_leaks.py                         # 入库产物脱敏守门
py -3.12 bench/refimpl.py                                     # 参照实现独立复算台账

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .
```
