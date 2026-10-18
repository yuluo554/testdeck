# HANDOFF-M1 · 下一棒 = 数据先行（M1）

> 启动方式（用户侧）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`
> **第一动作（硬约束③）**：先跑布局门 `py -3.12 tools/check-sprint-layout.py`，绿了再读别的。

## 1. 当前进度与证据

**已完成：M0（方法论装订 + 计划套件 + 可运行骨架）**，2026-10-18。

| 项 | 证据（本轮实跑） |
| --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` → 全绿；扫到 文档 10 / 交接单 1 / 状态副本 4 / 里程碑 7 |
| 布局门 6 组变异 | `py -3.12 tools/verify-layout-gate.py` → 7/7 按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest -q` → 78 passed（3.12 通道） |
| 自检 | `PYTHONPATH=src py -3.12 -m testdeck selftest` → exit 0，`[OK] selftest：键位表 11 条，退出码 0–4，规则包 3 份，源码 10 个` |
| 干净安装 | 新建 venv `pip install -e ".[dev]"` → 裸 `testdeck.exe selftest` 与 `python -m testdeck selftest` 均 exit 0；全量 pytest 78 passed |
| 打包面 | `pip wheel .` → 产物含 `testdeck/rules/{flaky,slow,view}.json`（装好的 CLI 读得到规则） |
| 出题门 | `py -X utf8 <skill>/scripts/check_topic.py .` → 0 FAIL / 0 WARN（M0 前 23 PASS；plan/02–06 落盘后 CROSS_MODULES 也已可跑） |
| CI | `.github/workflows/ci.yml` 已落盘并本地 `yaml.safe_load` 解析 + 断言步骤数（**未接远端，CI 待首推验证**） |
| 安装面 | `pip install -e ".[dev]"` + 裸 `testdeck selftest` + `python -m testdeck selftest` 两条通路都进 CI 步骤 |

**本轮交付的文件**（相对路径）：

```
AGENTS.md
tools/check-sprint-layout.py        # 布局门
tools/verify-layout-gate.py         # 布局门自身的 6 组变异验证
plan/00-README总览.md               # 顶部装订行 + 索引 + 台账 + 里程碑表
plan/02-架构与技术选型.md
plan/03-模块详设.md
plan/04-数据计划.md
plan/05-里程碑与发布.md
plan/06-交付对标与决策.md
src/testdeck/{__init__,__main__,cli,model,identity,paths,db,rules,keys,exit_codes}.py
src/testdeck/rules/{flaky,slow,view}.json
tests/{test_selftest,test_model,test_identity,test_paths,test_rules,test_guards,test_db,test_readme_gate}.py
pyproject.toml / MANIFEST.in / .gitattributes / .github/workflows/ci.yml
README.md
```

## 2. 下一棒待办（M1，按顺序）

1. **产出三份真实 fixture**（`bench/fixtures/{pytest,gotestsum,playwright}/`）：
   - pytest：仓库内最小测试集 `pytest --junitxml=...`；
   - gotestsum：**本机无 Go**（2026-10-18 实测 `go: command not found`）→ 用预置产物，
     在 `bench/fixtures/gotestsum/README.md` 写明"产出工具 + 版本 + 命令"，并如实标注"非本机重跑"；
   - Playwright：本机 `npx playwright` 未安装 → 同上，预置产物 + 来源说明；**不要伪造"本机跑过"**。
   - 每份 fixture 旁放 `expected.json`（用例数 / 失败数 / skipped / 各 suite 汇总），
     供 `bench_ingest.py` 对账。
2. **合成语料生成器** `data/synth/gen_runs.py`：
   - `--seed`、`--check`（只校验不写盘）、`--runs 200 --cases 5000`、`--big 50000`；
   - 同 seed 输出逐字节一致；写出 `expect.json`（只存输入侧 + 期望侧，不存 `observed`）；
   - 生成期断言覆盖：四种分型各 ≥1、`missing` ≥1、`skip` ≥1、transitions 1..5 梯度、
     回归六边界（1.2x / 200ms 的恰好/略低/略高）；
   - 假数据白名单（分支 `main`/`feature/synth-*`/`fix/synth-*`，commit 40 位全数字占位，run id 从 `1000000000`）。
3. **参照实现** `bench/refimpl.py`：只读 `expect.json` 的输入侧独立复算期望值；
   **禁 import `testdeck.*`**（AST 守门 + 变异验证）。
4. **`bench/bench_ingest.py`**：三框架逐项对账 + 5 万用例计时（< 2s）；
   `bench/run_all.py` 统一入口（`0/1/2` 三语义、`not_enabled` 不冒充通过、`--probe` 探活）。
5. **回写状态**：`plan/00` 台账行 + 里程碑表、`plan/05` §一、`plan/06` §二、`README.md` 状态表
   （四处一致），然后写 `plan/HANDOFF-M2.md` 并跑布局门。

## 3. 既定口径清单（K 编号，"动了会打挂测试"）

| 编号 | 口径 | 落点 | 动了会红在哪 |
| --- | --- | --- | --- |
| K1 | run 身份 = `(branch, commit_sha, ci_run_id)`；未知值写**空串**不写 NULL | `identity.py` / `db.py` | `test_identity.py`、`test_db.py::test_unknown_value_must_be_empty_string_not_null` |
| K2 | 用例身份 = `(suite_name, classname, name)`；参数串**不归一** | `identity.py` | `test_identity.py::test_case_identity_keeps_parameterized_name_verbatim` |
| K3 | 耗时 = 整数毫秒，ROUND_HALF_UP（**不是** `round()`） | `model.py:seconds_to_ms` | `test_model.py` 的 `0.0025 -> 3` 与银行家舍入反证 |
| K4 | 四态 `pass/fail/skip/missing`；只有 pass/fail 进分母、制造 transition | `model.py` | `test_model.py::test_is_counted_excludes_skip_and_missing` |
| K5 | 阈值全部来自 `rules/*.json`，**引擎零默认值**；阈值以十进制字符串存 | `rules.py` | `test_rules.py` 的缺文件/缺键/倒置三条 |
| K6 | 规则包必须在**包内**（`src/testdeck/rules/`），不放 `data/` | `rules.rules_dir()` | `test_rules.py::test_rules_dir_is_inside_package` |
| K7 | 导出**不写生成时刻**；`write_generated_at=true` 在规则层直接拒绝 | `rules.load_view_rules` | `test_rules.py::test_write_generated_at_true_is_rejected` |
| K8 | 退出码 `0/1/2/3`；`4` 仅 M0，M2 起 `ingest` 退役 | `exit_codes.py` / `plan/05` §二 | `test_selftest.py::test_not_ready_commands_return_4_in_m0`（M2 要改成断言退役） |
| K9 | `--db ""` 是用法错误（exit 2），**不回落默认库** | `paths.resolve_db_path` | `test_selftest.py::test_empty_db_argument_is_usage_error_not_default` |
| K10 | 键位表唯一来源 `keys.py`（11 条，含 `Enter` 别名归一） | `keys.py` | `test_selftest.py` 两条 |
| K11 | 零网络：`src/` 禁 import `socket/urllib/http/requests/...` | `cli.FORBIDDEN_NETWORK_MODULES` + selftest | `test_guards.py` 四种写法 + selftest 第 4 项 |
| K12 | 分层：`flaky/slow/report_model/model/identity` 禁 import 入口层/DB/Textual | `cli.LAYER_RULES` | `test_guards.py::test_layer_violation_is_detected` |
| K13 | 里程碑状态**四处副本一致**（`plan/00` 表、`plan/05` 表、`plan/06` 表、`README` 表） | 四个文件 | 布局门 `LAYOUT.STATUS` + 变异 M2 |
| K14 | 每个 ✅ 里程碑一份 HANDOFF，**且当前棒的下一棒 HANDOFF 必须在位** | `plan/HANDOFF-M<k>.md` | 布局门 `LAYOUT.HANDOFFS` |
| K15 | 布局门判据只落仓库内文件（**不读 git 元数据**） | `tools/check-sprint-layout.py` | 变异 M1–M6 全红 |
| K16 | README extras ↔ pyproject extras 双向一致；测试 import 的第三方必须进 dev extra | `tests/test_readme_gate.py` | 变异：README 加 `[report]` 或 tests 加 `pandas` |

## 4. 本机环境坑（实测于 2026-10-18）

- `py -0p`：只有 **3.8.8-64 与 3.12-64**。项目 `requires-python >=3.9`，**本机一律用 `py -3.12`**。
- `python` 是商店占位符 → 用 `py`；中文输出加 `-X utf8`。
- `node v24.15.0` / `npm 11.12.1` 在；**`go` 不在**；**Playwright 未安装**（`npx --no-install playwright` 报缺包）。
  → M1 的 gotestsum / playwright fixture 走"预置产物 + 来源说明"，**不要写成"本机重跑"**。
- `gh` 已登录 `yuluo554`（repo scope）；远端**尚未创建**（`git remote -v` 为空）。
- `github.com` git 通道间歇 `Failed to connect`；判据是"远端 sha == 本地 sha"，不是 push 退出码。
- 本机注册表代理会污染 pip：`NO_PROXY="*" no_proxy="*" py -3.12 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- pyc 偶发损坏 → 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` 再重试。
- 本机 Git Bash 里 `grep`/`sed` 打印中文 UTF-8 会乱码（**只是显示问题**）：验收用 `py -3.12` 以
  `encoding="utf-8"` 回读，或直接读文件。

## 5. DoD 逐项 checklist（M1）

- [ ] `bench/fixtures/{pytest,gotestsum,playwright}/` 三份产物入库，各带 `README.md`（来源/工具版本/命令）
- [ ] 每份产物旁 `expected.json`，`bench/bench_ingest.py` 用例数/失败数/skipped 与汇总**逐项相等**
- [ ] 5 万用例单文件 `iterparse` 解析 < 2s（本机实测数值写入 `plan/00` 台账）
- [ ] `data/synth/gen_runs.py --seed 42` 两次输出**逐字节一致**
- [ ] `gen_runs.py --check` 只校验不写盘，且能对坏真值报红
- [ ] `expect.json` 不含 `observed` 类字段（真值只存输入与期望）
- [ ] 生成期断言：四类分型各 ≥1、missing ≥1、skip ≥1、transitions 1..5、回归六边界
- [ ] `bench/refimpl.py` 不 import `testdeck.*`（AST 守门 + 变异验证）
- [ ] `bench/run_all.py` 退出码 0/1/2 三语义锁进测试；`not_enabled` 不冒充通过
- [ ] 四处状态副本回写一致；`plan/HANDOFF-M2.md` 落盘；布局门绿
- [ ] 全量 `pytest` 绿；`check_topic.py` 无 FAIL
- [ ] 本轮**未接远端** → 留档写"本地等价校验（CI 待首推验证）"，不得写"CI 绿"

## 6. 关键命令速查

```bash
# 布局门（第一件事）
py -3.12 tools/check-sprint-layout.py
py -3.12 tools/verify-layout-gate.py          # 6 组变异验证

# 测试 / 自检
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest -q
PYTHONPATH=src py -3.12 -m testdeck selftest

# 干净安装（本机）
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m testdeck selftest

# 出题门（只读；<skill> = 本机 ai-tool-topic-definer 技能目录，绝对路径只出现在会话命令里）
py -X utf8 "<skill>/scripts/check_topic.py" .

# M1 将新增
py -3.12 data/synth/gen_runs.py --seed 42 --check
py -3.12 bench/run_all.py
py -3.12 bench/run_all.py --probe
```
