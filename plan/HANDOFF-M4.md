# HANDOFF-M4 · 下一棒 = flaky 矩阵与分型 + 两次 run diff（M4）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（装订 + 计划套件 + 可运行骨架，2026-10-18）、M1（数据先行，2026-10-19）、
M2（解析落库，2026-10-19）、M3（三栏视图，2026-10-19）。**

| 项 | 证据（M3 本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿（文档 10 / 交接单 4 / 状态副本 4 / 里程碑 7） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` → 7 组变异全红、还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` → **308 passed**（M2 是 221） |
| 三栏视图 | `tests/test_tui_pilot.py`（15 例，无头 Pilot）：纯键盘"进入 → `j` 移到失败用例 → 右栏读到 `stack:` 首行" |
| summary 与 SQL 逐项相等 | 同上（`test_summary_panel_matches_direct_sql`）+ `tests/test_queries.py::test_summary_equals_direct_sql` |
| `F/S/D` 三视图接真实查询 | 同上（`test_three_views_render_real_query_results`）：断言矩阵/瀑布/diff 的**真实数据行**出现在面板里 |
| 两条降级（不依赖 Pilot） | `tests/test_view.py`：`column_mode` 5 例阈值 + `style_mode` 7 例矩阵 + "剥掉标记后逐字符相同" |
| 两条降级（真 App 上生效） | `tests/test_tui_pilot.py`：窄终端 → `single-column` 类 + `Enter` 进详情；`NO_COLOR=1` → `mono` 类 |
| 零网络 AST 守门 | `tests/test_no_network.py`（6 例）：四写法 + 动态导入字符串 + 白名单；变异后必红 |
| 分层 AST 守门 | `tests/test_layering.py`（6 例）：8 条 LAYER_RULES 逐条可命中 + **删掉 `app.py` 的 `report_model` 引用 → 必红** |
| 键位单点 | `tests/test_keys_single_source.py`（7 例）：AST 扫 `src/`，键位字母表外的单字符常量不误判；豁免表穷尽式 |
| 退出码 4 对 `tui` 退役 | `tests/test_exit_codes.py`（13 例）：`tui` 任何入参形态不返回 4；`NOT_READY` 分支只点名 `export` |
| 四通道逐项对账 | `py -3.12 bench/run_all.py --suites ingest` → 20 项检查全过，exit 0 |
| 生产解析器性能 | 同上（`perf/iterparse_big_file`）→ **0.209s** / 50000 用例（门槛 2s，取 3 次最小值） |
| 探活（基准侧） | `py -3.12 bench/run_all.py --probe` → 三处注入全被报出，exit 0 |
| 自检 | `py -3.12 -m testdeck selftest` → exit 0（键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 18 个） |
| 真值台账仍位级一致 | `py -3.12 data/synth/gen_runs.py --check` → PASS（436803 字节） |
| 出题门 | `check_topic.py .`（只读）→ 无 FAIL |

**本轮交付/改动的文件**（相对路径）：

```
src/testdeck/queries.py            # 只读 SQL 层（新增）：树/summary/详情/历史 + 矩阵/瀑布/diff 原料
src/testdeck/report_model.py       # 报告模型（新增）：REPORT_FIELDS 声明序 + build_report（TUI 与导出共用）
src/testdeck/tui/__init__.py       # 包导出（新增）
src/testdeck/tui/app.py            # Textual 三栏 App（新增）：控件装配 + 事件 + worker 取数
src/testdeck/tui/view.py           # 纯呈现层（新增）：两条降级 + 各视图渲染（不 import Textual）
src/testdeck/keys.py               # 键位单点：补 back/quit + description_for/display_label
src/testdeck/db.py                 # open_existing（只读意图打开已存在的库；库不存在 → exit 3）
src/testdeck/cli.py                # tui 实装接线；NOT_READY 分支只剩 export；守门扫描器拆成可测函数
bench/run_all.py                   # CURRENT_MILESTONE 1 → 3（标签对齐；M4 上线 flaky 套件时必须调到 4）
tests/test_queries.py              # 19 例：只读 / summary 对 SQL / 失败优先排序 / 矩阵与 diff 原料
tests/test_report_model.py         # 8 例：字段声明序 / history 窗口 / 空库报错 / 不 import Textual
tests/test_view.py                 # 27 例：两条降级 + 剥标记后结构不变 + 三视图渲染
tests/test_tui_pilot.py            # 15 例：Pilot 键盘全流程 + 三视图 + 降级 + 搜索 + 库不可用
tests/test_no_network.py           # 6 例（替代原 test_guards.py 的零网络部分，含变异验证）
tests/test_layering.py             # 6 例（分层方向，含"删掉 report_model 引用必红"的变异验证）
tests/test_keys_single_source.py   # 7 例：键位字面量只在 keys.py（AST + 穷尽豁免表）
tests/test_exit_codes.py           # IMPLEMENTED 加 tui、UNIMPLEMENTED 收敛为 ("export",)；+autouse 默认库隔离
tests/test_selftest.py             # 键位表 13 条 + tui 退役用例
tests/conftest.py                  # autouse 默认库隔离（测试绝不碰 ~/.local/share/testdeck/）
tests/test_readme_gate.py          # "测试 import 的库必须在安装面（dev extra ∪ 运行时依赖）"
plan/00,02,03,05,06 + README.md    # 状态与口径回写
```

> `tests/test_guards.py` 已删除：它的两条判据分别拆成 `test_no_network.py` 与
> `test_layering.py`（`plan/02` §一 点名的两个文件名），并按新要求各做**变异验证**。

## 2. 下一棒待办（M4，按顺序）

1. **`flaky.py`（判定层纯函数，`plan/03` 模块③）**：
   - `classify(history, rules) -> CaseProfile`：分母只含 pass/fail；`skip`/`missing`
     既不进分母也不制造 transition；`flaky_score = transitions / (n - 1)`，`n < 2` → 0；
   - 分型顺序**先判恒失败**：`fail_rate == 1` → `broken`；`== 0` → `stable`；
     `0.05 <= fail_rate <= 0.95` 且 `transitions >= 3` → `flaky`；其余 → `watch`；
   - **零计数样本落 `watch` 不落 `stable`**（K34，见 §3）——全 skip/missing 的用例
     `fail_rate` 无定义，"一次都没跑过"不是"稳定"；
   - 阈值/窗口/兜底标签全部从 `rules/flaky.json` 读，**代码里不得出现阈值字面量**
     （`tests/test_no_rule_literals.py` 扫描 `flaky.py` / `slow.py` 的数值常量）。
2. **`diff.py`（判定层纯函数，`plan/03` 模块④/模块②的 `D` 视图）**：两次 run 的用例级
   diff，三类对账（新增失败 / 修复 / 仍失败）；`tests/test_diff.py` 逐类断言。
3. **把分型接进 `queries.summary` 与矩阵**：`flaky` / `broken` 两个 summary 字段由
   `flaky.py` 填（现在恒 `None`）；矩阵行序改成 `flaky_score` 降序、同分按
   `(suite_name, classname, name)`。**注意**：`queries.py` 属编排层、`flaky.py` 属判定层，
   依赖方向是编排 → 判定（合法），别反过来。
4. **`D` 视图把 `diff_text` 的"原始状态对"升级为三类分类**：`view.diff_text` 现在只画
   `before→after` 并明确标注"分类待 M4"——M4 要把它换成 `diff.py` 的分类结果。
5. **`bench/bench_flaky.py` 上线**并把 `bench/run_all.py:CURRENT_MILESTONE` 调到 **4**
   （否则 `since=4` 的套件仍 `not_enabled`）。`run_all.py` 此刻已是 3。
6. **独立断言 `broken ∩ flaky == ∅`**（M4 DoD）：不靠"分类函数内部顺序"自证，
   而是拿固定 fixture 的两份集合求交。
7. **回写状态**：`plan/00` 台账行 + 里程碑表、`plan/05` §一 + 退役表（若 `export` 仍待 M5 则不动）、
   `plan/06` §二 + 缺口（G1 视实装范围收窄、G2 记 `flaky` 上线）、`README.md` 状态表
   （四处一致）；然后写 `plan/HANDOFF-M5.md` 并跑布局门。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

> M0 的 K1–K16（`plan/HANDOFF-M1.md` §3）、M1 的 K17–K25（`plan/HANDOFF-M2.md` §3）、
> M2 的 K26–K33（`plan/HANDOFF-M3.md` §3）**全部继续有效**。M3 新增：

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K34 | **零计数样本落 `watch`，不落 `stable`**（M1 已定，M3 再次强调给 M4 的 `flaky.py`）：全 skip/missing 的用例 `fail_rate` 是 0/0 无定义；判成 stable 会让 stable 虚高并掩盖"这用例根本没在跑" | `flaky.py`（M4） | `data/README.md` §四 已定钉；M4 的 `bench_flaky` 要有这条的对账 |
| K35 | **失败优先排序是单点**（`queries.fail_first_key`）：树、矩阵、瀑布共用；别处再写一份 = "屏幕顺序"与"导出顺序"两套口径 | `queries.py` | `test_queries.py::test_fail_first_key_is_the_single_sort_point` 三条 |
| K36 | **`queries.py` 只读**：只发 `SELECT`；**不返回 Textual 对象**；跑一遍全部查询函数后四表行数与 `meta` 不变 | `queries.py` | `test_queries.py::test_queries_never_write` / `test_query_layer_holds_no_textual_object` |
| K37 | **summary 的键序 = `view.summary_fields`**（规则包单点）；`flaky`/`broken`/`slow` 在各自里程碑前恒为 `None`（**不顺手算**，否则口径复制成第二套） | `queries.py` + `report_model.py` | `test_queries.py::test_summary_field_order_comes_from_rules` / `test_pending_summary_fields_are_none_not_guessed` |
| K38 | **`report_model.REPORT_FIELDS` 是有序元组**（md 列序 = JSON 键序 = TUI 取值来源）；`case_id` **不进报表**（本机自增主键跨机器无意义）；`ingested_at` 不进导出 | `report_model.py` | `test_report_model.py` 三条 |
| K39 | **两条降级由 `view.py` 的纯函数决定**（`column_mode` / `style_mode`），`app.py` 只把结果落到 CSS 类上；**颜色退化只去"色"**——剥掉标记后两种模式的文本逐字符相同 | `tui/view.py` + `tui/app.py` | `test_view.py::test_color_never_loses_structure`（9 个渲染器逐个比）+ `test_tui_pilot.py` 两条降级用例 |
| K40 | `NO_COLOR` **按"有没有设置"判**（`"NO_COLOR" in env`），不看取值——`NO_COLOR=""` 也是要退化（用 `env.get()` 会把它当假值，实测踩过） | `tui/view.py` | `test_view.py::test_style_mode_matrix` 的 `NO_COLOR=""` 一例 |
| K41 | **键位字面量只在 `keys.py`**；判据是"出现键位字母表里的单字符常量"（不是"任何单字符常量"，后者会把 `"+"`/`"\n"`/`"—"` 全扫进来）；豁免表**穷尽式**（登记了却不出现 → 判红） | `keys.py` + `tests/test_keys_single_source.py` | 该文件 7 条 |
| K42 | **TUI 默认不聚焦任何控件**：`Input` 默认 `can_focus=False`，`on_ready` 里 `set_focus(None)`。否则首焦点落在搜索框上，`j`/`F` 全被它吃掉（实测：敲 `j` 只会多一个字符） | `tui/app.py` | `test_tui_pilot.py` 的键盘流程（全部按键用例） |
| K43 | **键位 `escape`/`q` 也是键位表成员**（`back`/`quit`）：Footer 与帮助层从 `keys.KEYS` 生成，帮助层自己的关闭键也取 `keys.BINDINGS` | `keys.py` + `tui/app.py` | `test_selftest.py::test_display_keys_match_bindings`、`test_keys_single_source.py::test_help_screen_bindings_also_come_from_keys` |
| K44 | **测试绝不碰用户默认库**：`tests/conftest.py` 有 autouse 的 `XDG_DATA_HOME` 隔离。M3 实测踩过两次——`["ingest", "."]` 会写默认库；本机默认库**恰好有数据**时 `["tui"]` 会真把 TUI 起起来并**挂住整个 pytest** | `tests/conftest.py` | 删掉这个 fixture → 全量 pytest 会卡住（不是变红，是挂住） |
| K45 | **`tui` 的库不存在 / 无 run / `--run` 不存在 → exit 3**（不是 4、不是 0）：空库 ≠ "没有失败" | `tui/app.py:run_tui` | `test_tui_pilot.py` 三条 + `test_exit_codes.py::test_tui_never_returns_not_ready` |
| K46 | **分层守门有两半**：`LAYER_RULES`（不许 import）+ `REQUIRED_IMPORTS`（**必须** import：`app.py` 必须 import `report_model`、`queries.py` 必须 import `model`）。只有前一半时，"把共用模型的引用删掉"能悄悄过 | `cli.py` | `test_layering.py::test_removing_report_model_reference_is_detected`（本次的变异验证） |
| K47 | **测试 import 的第三方库必须在安装面内**（dev extra **∪ 运行时依赖**）：M3 起测试会 import `textual`（Pilot），它随包安装、合法；这条门拦的是第四方 | `tests/test_readme_gate.py` | `test_dev_extras_cover_test_imports` |

## 4. 本机环境坑（M3 实测补充）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**；项目 `requires-python >=3.9`，**一律 `py -3.12`**；
  中文输出加 `-X utf8`。
- `python` 是商店占位符 → 用 `py`。pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`。
- **`textual` 8.2.8 + `rich` 15.0.0 已装**（`pypi.tuna.tsinghua.edu.cn` 可达，2026-10-19）：
  `NO_PROXY="*" no_proxy="*" py -3.12 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple "textual>=1.0,<9"`。
  装完 `import textual` 即可；**不要**在测试里 `pytest.importorskip` 绕过——`textual` 是
  运行时依赖，装了才是常态。
- **Textual 8.x 的键名与字符不同**：`/` 要写 `slash`（写 `"/"` 也能绑上，但 `keys.py` 里
  存的是字面字符）、`?` 是 `question_mark`、`Enter` 是 `enter`、`Esc` 是 `escape`。
  Pilot 里按 `"/"` 用 `pilot.press("slash")`，按 `?` 用 `pilot.press("question_mark")`。
- **`Static` 没有 `.renderable`**（旧版有）：读面板内容用 `.content`（M3 实测）。
- **`textual.workers` 不存在**，是 `textual.worker_manager`；`WorkerManager.wait_for_complete` 在。
- **`Binding(key, action, description, priority=...)`**：`enter` 要用 `priority=True` 抢在
  `Tree` 自己的 enter 之前（树本身已 `can_focus=False`，双保险）。
- **`App.run()` 在非 tty 下会画出完整界面并挂住**：`["tui"]` 这类用例必须靠
  `XDG_DATA_HOME` 隔离让"库不存在"成立（K44），否则测试进程会卡死而不是失败。
- 本机默认库 `~/.local/share/testdeck/testdeck.db` **已有数据**（M2 期某次测试写进去的）：
  它是环境事实，不是仓库内容；`git status` 看不到它。**别把它当判据**。
- **`os.path.relpath` 跨盘符抛 `ValueError`**：凡"展示用相对路径"都 try/except
  （`paths.relative_to_root` 已封好）。
- **行尾（实测坑，M3 踩过）**：本仓 `.gitattributes` 是 `* text=auto eol=lf`，所有
  `.md`/`.py` 入库时都应是 **LF**。但在这台 Windows 上改写文件时，工作树里
  **可能被写成 CRLF**——后果不是"看起来不对"，而是 `tools/verify-layout-gate.py` 的
  `delete_line` 变异**直接崩**：它按 `"\n".split()` 逐行比对，CRLF 文件里每行都带 `\r`，
  于是"删掉那一行"后字节竟然没变 → `AssertionError: 删行后字节未变`
  （M3 实测：`plan/00` 被写成 CRLF，7 组变异在第 5 组中止）。
  **收尾前先扫一遍**：
  `py -3.12 -c "import glob;print([f for f in glob.glob('**/*.md',recursive=True) if open(f,'rb').read().count(b'\r\n')])"`
  ——有输出就先归一成 LF，再跑布局门变异。
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用
  `py -3.12` 以 `encoding="utf-8"` 回读，或直接读文件。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**。`github.com` git 通道间歇失败，
  判据是"远端 sha == 本地 sha"，不是 push 退出码。

## 5. DoD 逐项 checklist（M4）

- [ ] `flaky.py` 落地；分母只含 pass/fail；`skip`/`missing` 不制造 transition
- [ ] 分型顺序**先判恒失败**；`broken` 与 `flaky` 两个集合**独立断言互斥**（不靠函数内部顺序自证）
- [ ] 零计数样本落 `watch` 不落 `stable`（K34）
- [ ] `flaky.py` 里**不得出现阈值字面量**（`tests/test_no_rule_literals.py` 扫描通过）
- [ ] `diff.py` 落地；`tests/test_diff.py` 三类（新增失败 / 修复 / 仍失败）逐类对账
- [ ] `queries.summary` 的 `flaky`/`broken` 由 `flaky.py` 填（不再是 `None`）；矩阵行序改 `flaky_score` 降序
- [ ] `view.diff_text` 升级为 `diff.py` 的三类分类（不再是"原始状态对"）
- [ ] `bench/bench_flaky.py` 上线；`bench/run_all.py:CURRENT_MILESTONE` 调到 **4**
- [ ] `bench/run_all.py --suites ingest,flaky` exit 0；`--probe` 仍全检出
- [ ] 四处状态副本回写一致；`plan/HANDOFF-M5.md` 落盘；布局门绿；布局门变异 7 组全红
- [ ] 全量 `pytest` 绿；`check_topic.py` 无 FAIL
- [ ] 本轮**未接远端** → 留档写"本地等价校验（CI 待首推验证）"，不得写"CI 绿"

## 6. 关键命令速查

```bash
# 布局门（第一件事）
py -3.12 tools/check-sprint-layout.py
py -3.12 tools/verify-layout-gate.py          # 布局门自身的变异验证

# 测试 / 自检
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest -q
PYTHONPATH=src py -3.12 -m testdeck selftest

# M3 三栏视图（本轮）
PYTHONPATH=src py -3.12 -m testdeck ingest bench/fixtures/pytest/junit.xml \
    bench/fixtures/gotestsum/gotestsum.xml bench/fixtures/playwright/playwright.xml \
    --db bench/.tmp/demo.db
PYTHONPATH=src py -3.12 -m testdeck tui --db bench/.tmp/demo.db      # 需真终端
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest tests/test_tui_pilot.py -q   # 无头键盘全流程

# 基准
py -3.12 bench/run_all.py --suites ingest     # 四通道对账 + 生产解析器性能（exit 0）
py -3.12 bench/run_all.py --probe             # 探活（exit 0）

# M1 数据面（仍是下面这些）
py -3.12 data/synth/gen_runs.py --check                       # 真值台账位级一致
py -3.12 bench/fixtures/regen_fixtures.py                     # 真跑三框架 fixture（需 go / node）
py -3.12 bench/fixtures/scan_leaks.py                         # 入库产物脱敏守门
py -3.12 bench/refimpl.py                                     # 参照实现独立复算台账

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .
```
