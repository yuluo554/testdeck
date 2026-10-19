# HANDOFF-M2 · 下一棒 = 解析落库（M2）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（装订 + 计划套件 + 可运行骨架，2026-10-18）、M1（数据先行，2026-10-19）。**

| 项 | 证据（M1 本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿 |
| 全量测试 | `py -3.12 -m pytest` → **150 passed**（3.12 通道） |
| 三框架真实产物 | pytest 6/1/0/1、gotestsum 5/1/0/1、playwright 7/1/0/1（tests/failures/errors/skipped）；**全部真跑产出**（见各 `README.md` 的 `produced_by`） |
| 产物逐项对账 | `py -3.12 bench/run_all.py --suites ingest` → 11 项检查全过，exit 0 |
| 5 万用例性能 | `iterparse` 解析 `data/synth/big.xml`（3.6 MB / 50000 用例）→ **0.071–0.081s**（门槛 2s） |
| 真值台账 | `py -3.12 data/synth/gen_runs.py --check` → 与已登记台账逐字节一致（436803 字节） |
| 生成器确定性 | 同 seed 多次独立运行 sha256 相同：`281e2a271f60ec30e1649415402f7dd1bbbf1e1640816ae2e78582d234cdd8eb` |
| 坏真值证伪 | 篡改一条锚点的 `label` 后 `--check` → exit 1（不是恒绿） |
| 探活 | `bench/run_all.py --probe` → 参照实现守门 / 对账 off-by-one / 性能门槛三处注入均被报出 |
| 脱敏扫描 | `py -3.12 bench/fixtures/scan_leaks.py` → 14 文件，0 处泄漏 |
| `run_all` 三语义 | `--suites ingest` → 0；不带参数（含未就绪套件）→ 1；`--suites nope` → 2 |

**本轮交付/改动的文件**（相对路径）：

```
data/synth/gen_runs.py              # D5/D6/D7：合成语料 + 真值台账生成器
data/synth/expect.json              # D7 真值（22 锚点 + 50 样本 + 全语料汇总，约 0.43 MB）
bench/refimpl.py                    # 参照实现（禁 import testdeck.*）
bench/bench_ingest.py               # 三框架逐项对账 + 大文件 iterparse 计时
bench/run_all.py                    # 统一入口（0/1/2、not_enabled、--probe、AST 守门）
bench/fixtures/regen_fixtures.py    # 真跑三框架 + 三通道对账 + 确定性脱敏 + 写 expected.json
bench/fixtures/scan_leaks.py        # 入库产物脱敏守门
bench/fixtures/{pytest,gotestsum,playwright}/   # 产物 + expected.json + README.md（+ 被测源码）
tests/conftest.py                   # 按路径装载仓库内脚本（避开 README 门的第三方误判）
tests/test_bench_refimpl.py         # 参照实现算术 + 独立性守门（含变异验证）
tests/test_bench_synth.py           # 生成器可重放 / 真值纪律 / 模式覆盖 / 白名单
tests/test_bench_suites.py          # 三框架对账 + run_all 退出码三语义
AGENTS.md / .gitignore / MANIFEST.in / README.md
tools/verify-layout-gate.py         # 变异 marker 跟着新缺口表重排（M1 关闭 G1/G2 后）
plan/00,04,05,06（状态与口径回写）
```

## 2. 下一棒待办（M2，按顺序）

1. **生产解析器** `src/testdeck/junit.py`：`iterparse(events=("start","end"))` 流式解析；
   - `testsuite@name` → `suite_name`；`testcase@classname`（缺省空串）→ `classname`；
     `testcase@name` → `name`（**参数化用例保留完整参数串，不归一**，K2）；
   - `failure`/`error` → `fail`，`skipped` → `skip`；`failure_type` 取 `type`（缺省空串），
     `failure_message` 取 `message`，`stack_first_line` 取 `text` 第一行（去首尾空白）；
   - 耗时用 `model.seconds_to_ms`（Decimal + ROUND_HALF_UP，K3）；缺失写 `None`；
   - 坏文件记 `skipped:<reason>`（`bad_xml` / `bad_encoding` / `no_testsuite`），**不静默、不中断整批**。
   - **实测坑（务必照做）**：`testsuites` 根**不一定**带 totals（pytest 不带）；
     gotestsum 的根**不写 `skipped` 属性**（尽管含 skipped 用例）。把"属性缺失"当 0 会让
     对账出现假红——见 `bench/fixtures/gotestsum/README.md` 与
     `bench/bench_ingest.py:declared_in_xml`。
2. **框架识别** `src/testdeck/framework.py`：按根/`testsuite@name` 前缀 + 文件名判定
   `pytest` / `gotestsum` / `playwright`；判不出写 `"unknown"`。**Playwright 的 suite name 是文件名**，
   gotestsum 的是包名——不要用同一套假设。
3. **四表 schema + upsert** `db.py`：`runs` / `suites` / `cases` / `occurrences`；
   `INSERT … ON CONFLICT DO UPDATE`；重复 ingest 行数不变（K1：未知值写**空串**不写 NULL）。
4. **`ingest` 命令实装 + 退出码 4 退役**：摘要行（机读 + 人读）按 `plan/03` 模块① 的格式；
   `--db` 覆盖值**必须回显**；`--dry-run` 零副作用。
   → `tests/test_selftest.py::test_not_ready_commands_return_4_in_m0` 必须改成"断言退役"
   （`plan/05` §二 的退役判据：`grep -rn "NOT_READY" src/ tests/` 只在 `exit_codes.py` 与历史测试里出现）。
5. **把 `bench/bench_ingest.py` 改为消费生产解析器**：现在的 `parse_junit_stream` 是基准侧实现
   （M1 数据先行期的临时方案）。改完后"基准侧 vs 生产"互为对照；`plan/04` §五 已写明这条。
6. **回写状态**：`plan/00` 台账行 + 里程碑表、`plan/05` §一、`plan/06` §二 + 缺口（G1 关闭）、
   `README.md` 状态表（四处一致），`bench/run_all.py` 的 `CURRENT_MILESTONE` 保持 1
   （M2 不新增套件，故不用改），然后写 `plan/HANDOFF-M3.md` 并跑布局门。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

> M0 的 K1–K16 全部继续有效（原表见 `plan/HANDOFF-M1.md` §3）。M1 新增：

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K17 | 参照实现 `bench/refimpl.py` **禁 import `testdeck.*`**（含相对导入与 `importlib.import_module("testdeck…")`） | `bench/run_all.py:no_production_import_problems` | `tests/test_bench_refimpl.py` 5 条（四种写法 + 动态） |
| K18 | 参照实现的阈值取自台账 `rules_snapshot`，**不读** `src/testdeck/rules/` | `refimpl.py` + `gen_runs.load_rules_snapshot` | `test_bench_synth.py::test_rules_snapshot_matches_production_rules` |
| K19 | 零计数样本（全 skip/missing，`n == 0`）落 **`watch`**，**不得**落 `stable` | `refimpl.compute_profile` + 生产 `flaky.py` | `test_bench_refimpl.py::test_zero_counted_runs_is_watch_not_stable`；语料锚点 `watch_no_counted_runs` |
| K20 | `fail_rate` / `flaky_score` / p50 / p95 用**精确有理数**（`Fraction`）运算，渲染为终止十进制串，不终止用 `p/q`；**禁 float** | `refimpl.py:render` + `flaky.py` / `slow.py` | `test_bench_refimpl.py::test_render_is_exact_not_float`、`test_percentile_p95_linear_interpolation` |
| K21 | 回归窗口切分 `split` 由**输入侧**给出（台账里显式存 `regression_split`），引擎不得自行发明切分 | 台账 schema + `slow.py` | `test_bench_synth.py::test_regression_boundary_anchors_are_exact` |
| K22 | 回归不可判返回 `None`（`undefined_base` / `missing_window`），**不是 `False`**——"不可判"不得伪装成"无回归" | `refimpl.regression` + `slow.py` | `test_bench_refimpl.py::test_regression_undefined_base_is_not_a_verdict` |
| K23 | `run_all` 的 `not_enabled` **计入 exit 1**；拿 exit 0 必须显式 `--suites` | `bench/run_all.py` | `test_bench_suites.py` 的 `test_not_enabled_forces_exit_1` / `test_not_enabled_suite_is_not_a_pass` |
| K24 | XML 属性缺失 **不等于 0**（"没声明"与"声明为 0"要分开）；gotestsum 不声明 `skipped` | `bench_ingest.declared_in_xml` + M2 生产解析器 | `test_bench_suites.py::test_bench_ingest_records_undeclared_fields_honestly` |
| K25 | fixture 入库前只允许两步确定性脱敏（删 `hostname`、绝对路径改相对）；其余字节不动 | `bench/fixtures/regen_fixtures.py:_scrub` | `bench/fixtures/scan_leaks.py`（0 泄漏） |

## 4. 本机环境坑（实测于 2026-10-19）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**。项目 `requires-python >=3.9`，**本机一律用 `py -3.12`**。
- `python` 是商店占位符 → 用 `py`；中文输出加 `-X utf8`。
- **`go` 不在 PATH 上，但可以下载**：`https://dl.google.com/go/go1.23.4.windows-amd64.zip`
  实测 5.7s 下完。`gotestsum` 经 `GOPROXY=https://goproxy.cn,direct` 安装成功（19s）。
  → 需要真跑 Go fixture 时不必再走"预置产物"。
- **Playwright 可装**：`npm install --registry=https://registry.npmmirror.com @playwright/test@1.48.2`，
  浏览器设 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright` 后
  `npx playwright install chromium`。**官方源 `registry.npmjs.org` / `proxy.golang.org` 当时不通**。
- fixture 目录里的 `node_modules/` 会被 `.gitignore` 的 `bench/fixtures/**/node_modules/` 挡掉；
  Playwright 还会产生 `test-results/`（也已忽略）。
- **`/tmp` 在 Git Bash 与 Windows Python 里不是同一个目录**：Git Bash 的 `/tmp` =
  `C:\Users\<用户>\AppData\Local\Temp`，而 `py -3.12` 收到 `/tmp/x` 会解析成 `D:\tmp\x`。
  跨工具传路径用仓库内相对路径（本仓库用 `bench/.tmp/`，已忽略）。
- **`os.path.relpath` 跨盘符抛 `ValueError`**（仓库 `D:`、临时目录 `C:`）；展示用相对路径要
  try/except 回落（M1 已在 `bench_ingest._display` 修过一次）。
- 本机注册表代理会污染 pip：`NO_PROXY="*" no_proxy="*" py -3.12 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` 再重试。
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用 `py -3.12` 以
  `encoding="utf-8"` 回读，或直接读文件。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**。`github.com` git 通道间歇失败，
  判据是"远端 sha == 本地 sha"，不是 push 退出码。

## 5. DoD 逐项 checklist（M2）

- [ ] `src/testdeck/junit.py` 流式解析：5 万用例单文件 < 2s（沿用 M1 的 D6 语料）
- [ ] 三框架身份键一致：同一用例在三份 fixture 里解析出的 `(suite_name, classname, name)` 形如预期
- [ ] 坏文件记 `skipped:<reason>`：`bad_xml` / `bad_encoding` / `no_testsuite` 三种各一条实测
- [ ] 四表 schema 落盘；**重复 ingest 四表行数不变**（upsert 生效）
- [ ] `ingest` 摘要回显 `--db` 覆盖值；`--dry-run` 前后全仓快照差集为空
- [ ] `ingest` 的 `NOT_READY(4)` 退役，且 `tests/test_selftest.py` 相应改成"断言退役"
- [ ] `bench/bench_ingest.py` 改为消费生产解析器，对账仍 0 差异
- [ ] 四处状态副本回写一致；`plan/HANDOFF-M3.md` 落盘；布局门绿
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

# M1 数据面（本轮新增）
py -3.12 data/synth/gen_runs.py --check                       # 真值台账位级一致
py -3.12 data/synth/gen_runs.py --seed 42 --runs 200 --cases 5000 --sample-size 50 --big 50000
py -3.12 bench/run_all.py --suites ingest                     # 对账 + 性能（exit 0）
py -3.12 bench/run_all.py                                     # 全部登记套件（含未就绪 -> exit 1）
py -3.12 bench/run_all.py --probe                             # 探活
py -3.12 bench/refimpl.py                                     # 参照实现独立复算台账
py -3.12 bench/fixtures/regen_fixtures.py                     # 真跑三框架 fixture（需 go / node）
py -3.12 bench/fixtures/scan_leaks.py                         # 入库产物脱敏守门

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .
```
