# RELEASE-M6 · 发布留档（TestDeck v0.1.0）

> 本文件是 **M6 收尾的发布留档**，按 `plan/05` §四.5 的两栏口径组织：
> **§一 tag 时点事实**（在打 tag 之前就已成立、且必须随 tag 树一起发布的那些事实）/
> **§二 tag 之后追加事实**（只能在 tag 之后才产生或才可核对的实测值）。
>
> **为什么分两栏**：发布后才产生的实测值（tag 对象 sha、远端 sha、CI run id、
> 附件 sha256、真下载复核结果）**在 tag 树里不可能存在**——把它们写进 §一 等于
> 声称一件当时还没发生的事。分栏后，tag 树内这份留档自身是终态（§二 的槽位如实标注
> "tag 后回填"），tag 之后再追加的只是 §二。
>
> 判据落点：布局门 `LAYOUT.RELEASE`（两栏小节 + 覆盖对账小节 + 三态行 ≥3）；
> 发布终态门 `check_release.py`（tag 树内留档存在 / 分栏自证 / tag 不早于留档 / 附件对账）。

## 一、tag 前事实（打 `v0.1.0` 之前已成立）

### 1.1 版本与形态

| 项 | 值 |
| --- | --- |
| 版本号 | `0.1.0`（单点 `src/testdeck/__init__.py`，`pyproject.toml` 用 `dynamic`） |
| 交付形态 | 唯一形态 = 纯本地终端 TUI（Textual）；`ingest` / `tui` / `export` / `selftest` 四命令 |
| Python 下限 | `>=3.9`（`requires-python`；本机用 `py -3.12` 跑） |
| 运行时依赖 | `textual>=1.0,<9`（**零网络**，由 `tests/test_no_network.py` 守门） |
| 许可证 | MIT（`LICENSE` 在仓内） |
| 仓库 | `yuluo554/testdeck`，public（`plan/06` §四 D9） |
| 发布附件口径 | 手工源码包（`python -m build --sdist`），**不用** GitHub 自动 Source code 包（D8） |

### 1.2 tag 时点的自检结论（全部在**本机**跑）

| 检查 | 命令 | 结论 |
| --- | --- | --- |
| 布局门 | `py -3.12 tools/check-sprint-layout.py` | 全绿（文档 10 / 交接单 6 / 状态副本 4 / 里程碑 7） |
| 布局门自身变异 | `py -3.12 tools/verify-layout-gate.py` | **8 组**变异全按预期变红，还原后全绿 |
| 全量测试 | `py -3.12 -m pytest` | **476 passed** |
| 四套基准 | `py -3.12 bench/run_all.py --no-perf-gate` | 达标套件 4 / 未达标 0 / 未就绪 0（43 项检查），exit 0 |
| 基准探活 | `py -3.12 bench/run_all.py --probe` | 逐套件注入全被报出，exit 0 |
| 自检 | `py -3.12 -m testdeck selftest` | exit 0（键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 22 个） |
| 真值台账位级一致 | `py -3.12 data/synth/gen_runs.py --check` | PASS（436804 字节） |
| 录屏 | `py -3.12 tools/make-demo-gif.py --check` | `docs/demo/demo.gif`：8 帧 / 24.0s（≤30s）/ 478380 字节 |
| 出题门 | `check_topic.py .`（只读） | 无 FAIL |
| 发布终态门（tag 前） | `check_release.py . --tag v0.1.0` | 见 §三「待首推」行——tag 相关项此刻必然未成立 |

### 1.4 首推 CI（branch push，tag 之前）

`plan/05` §四.3 的"建仓 → push main → 等 CI 绿"发生在 tag **之前**，故记在本栏。

| 项 | 值 |
| --- | --- |
| 远端 | `yuluo554/testdeck`（public，`gh repo create`，2026-10-19） |
| push 口径 | **push 事件数**（不是提交数）；权威 = `gh run list --workflow ci.yml --json event,headBranch,headSha,conclusion` 逐条配对，不用 Events API（事件面高频丢弃，只作旁证） |
| 对账规则 | **1 次 push = 1 条 run**（branch push 与 tag push 各计一次；同 sha 的 branch run 与 tag run 两条合法）。**规则不变，数字不必追着跑**——下表只记 tag 前三次 push 的实测，之后新增的 run 按同一规则计量，终态证据收在 §二 |
| run ①（首推 `4bd601d`） | id **39205759555**，push/main → **failure**（4 矩阵 3 红 1 绿） |
| run ②（CI 修复 `c4c61f2`） | id **39206916398**，push/main → **success**（4 矩阵全绿） |
| run ③（回填 CI 事实 `524525d`） | id **39207422066**，push/main → **success**（4 矩阵全绿） |
| 矩阵 | ubuntu-latest / windows-latest × 3.9 / 3.12 = 4 矩阵，run ②/③ 全 success |
| 远端 sha == 本地 sha | ✅ 逐次核对（`git ls-remote origin refs/heads/main` == `git rev-parse main`） |

**首跑失败照录不抹除**（DoD 纪律）。run ① 的失败面暴露两条**本机不可能发现**的缺陷：

1. **py3.9 没有 `sys.stdlib_module_names`**：两处各写一份的冻结兜底名单都漏了 8 个真实
   标准库模块（`__future__` / `codecs` / `fractions` / `asyncio` / `builtins` / `importlib` /
   `struct` / `random`），于是 py3.9 两个矩阵把标准库 import 误判成"未登记的第三方依赖"。
   修法：名单**单点**落到 `tests/conftest.py::stdlib_module_names()`（并入
   `builtin_module_names` + 穷尽式冻结名单），以 `stdlib_names` fixture 暴露，两个测试文件同源取用。
2. **跨盘符断言写死了 Windows 行为**：`test_relative_to_root_cross_drive_does_not_crash`
   断言"等于绝对路径"，而 Linux 上 `os.path.relpath` 不抛错、返回相对路径 → ubuntu 两个矩阵红。
   修法：该条只断言"不崩 + 正斜杠"（平台无关）；"回落绝对路径"由 monkeypatch 令
   `relpath` 抛 `ValueError` 的新用例跨平台钉住。

> **推送数 = run 数对账**：2 次 push main ↔ 2 条 run（run ① / run ②），逐条 `event/headBranch/
> headSha/conclusion` 可核（`gh run list --workflow ci.yml --json …`）。权威 = push 流水，
> 不用 Events API（事件面高频丢弃，只作旁证）。

### 1.5 干净环境验证（`plan/05` §四.1）

通路：`git archive HEAD` 解包到**中立目录**（仓库外）→ 新 venv →
`pip install -e ".[dev]"`（`NO_PROXY="*"` + 清华镜像）→ 按 `README.md` 逐条跑。

| # | 命令（README 形态） | 退出码 | 语义 |
| --- | --- | --- | --- |
| 1 | 裸 `testdeck selftest` | 0 | 键位 13 条 / 退出码 0–4 / 规则包 3 份 / 源码 22 个 |
| 2 | `python -m testdeck selftest` | 0 | 同上（**两条通路都验**，只验一条会漏安装面缺陷） |
| 3 | `python -m pytest` | 0 | **476 passed** |
| 4 | `python tools/check-sprint-layout.py` | 0 | 全绿 |
| 5 | `python -m testdeck ingest <三份产物> --db <临时库>` | 0 | `files=3 runs=1 cases=18 occurrences=18 skipped=0` |
| 6 | `python -m testdeck export --format md` | 0 | md 报告到 stdout（列序 = JSON 键序 = 字段声明序） |
| 7 | `python -m testdeck export --fail-on regressions` | 0 | 无回归命中 → 0（命中 → 1） |
| 8 | `python bench/run_all.py` | 0 | 四套件 43 项检查全绿 |

> 上表在本轮**两遍**跑：第一遍（干净环境首次）抓到 Pillow / 字体两缺陷并修复；
> 修后在**最终 HEAD** 上重跑，8 条命令全 exit 0。

**本轮干净环境验证抓到并修掉的两处真实缺陷**（这条通路存在的意义）：

1. `tools/make-demo-gif.py` 用 `PIL`（Pillow），但 `dev` extra **没登记**它。
   本地已装 Pillow 故全绿；干净环境 6 例红（`ModuleNotFoundError: No module named 'PIL'`）。
   旧门 `test_dev_extras_cover_test_imports` 只扫 `tests/*.py` 的顶层 AST，
   **看不见"被测试按路径动态装载的仓库脚本"的 import**。
2. `rasterize()` 硬编码 `C:/Windows/Fonts/simsun.ttc`：Linux/macOS 上不存在，
   CI（ubuntu）会抛 `OSError: cannot open resource`。

处置：`dev` extra 补 `Pillow>=10.1`；字体改按候选表探测（Windows SimSun / Linux DejaVu /
macOS Menlo），都不可用退回 `ImageFont.load_default(size)`；新增门
`test_dev_extras_cover_repo_script_imports`（扫描面扩到 `tools/` `bench/` `data/`），
变异验证：去掉 Pillow → 必红。修后干净环境 **475 passed**、两通路 exit 0。
`demo.gif` 重生成**逐字节一致**（478380 字节），证明字体重构未改内容。

### 1.4 脱敏四步（`plan/05` §四.2）

| 面 | 工具/命令 | 结论 |
| --- | --- | --- |
| 源码常量 | 扫 `src/**` 的机器路径 / 真域名 / 凭据 / `hostname=` | 25 文件 **0 命中** |
| 文档 | `py -3.12 -X utf8` 以 `encoding="utf-8"` 回读全仓（本机 grep 中文会乱码） | 4 处命中均为**抽象样例**：`AGENTS.md` / `plan/HANDOFF-M2.md` 的「`/tmp` 跨工具不是同一目录」说明（`D:\tmp\x`）、`tests/test_paths.py` 的合成输入 `C:/tmp/x.db`——非机器标识 |
| 产物 | `py -3.12 bench/fixtures/scan_leaks.py` | 17 文件 **干净**（真跑三框架产物无绝对路径/机器名/真域名） |
| 提交元数据 | `git log --format='%ae%n%ce'` 去重 | 唯一邮箱 `282769740+yuluo554@users.noreply.github.com`（**全部 noreply**，含 tag 指向的发布提交） |

> 白名单形态只有 `yuluo554@users.noreply.github.com`（`plan/05` §四.2）。
> 留档里出现的 `yuluo554` 是**署名**（`LICENSE` / `pyproject` / `plan` 的公开署名），
> 不是机器标识，按 `plan/01` §一定稿口径保留。

### 1.5 决策收尾（`plan/06` §四 D8–D10）

| 编号 | 议题 | 结论 | 状态 |
| --- | --- | --- | --- |
| D8 | 发布附件口径 | **手工 sdist**（`python -m build --sdist`），附件名 `testdeck-0.1.0.tar.gz` | ✅ 按 `plan/05` §四 既定口径执行 |
| D9 | 仓库名 / 可见性 | `yuluo554/testdeck`，public | ✅ 按 `plan/01` §一 既定口径执行 |
| D10 | 录屏格式 | `docs/demo/demo.gif`（8 帧 / 24.0s ≤ 30s） | ✅ M5 已产出，M6 复核通过 |

> **口径来源说明**：D8/D9 在本轮**未收到用户的新指示**。它们的既定口径已分别写在
> `plan/05` §四（sdist）与 `plan/01` §一（`yuluo554/testdeck` public、署名 yuluo554）——
> 那是题面定稿时确认过的方向。本轮据此执行，不另立第二套口径，也不静默改成更宽松的默认值。
> D10 在 M5 已按 `plan/01` §三 / `plan/06` D10 落地并复核。

## 二、tag 之后追加事实（tag 后回填）

> **本节槽位在 tag 树内如实标注"tag 后回填"**：下面这些值在打 tag 时**尚不存在**，
> 只能作为 tag 之后的追加提交回填。tag 之后的提交**只动文档面**
> （`plan/` + `README.md`），不得再改代码面（`AGENTS.md` 禁止条 / 阶段 7 出口门）。

### 2.1 仓库与远端同源

| 项 | 值（tag 后回填） |
| --- | --- |
| 本地 tag 对象 | `v0.1.0`（annotated） |
| tag 指向的提交 | （tag 后回填） |
| 远端 tag sha == 本地 | （tag 后回填）——判据是"远端 sha == 本地 sha"，**不是 push 退出码** |
| 远端 main sha == 本地 main | （tag 后回填） |

### 2.2 CI 实跑（`plan/05` §五 两项的关闭条件）

branch push 的 CI 已在 §1.4 记录（tag 前）。本节只留 **tag push** 的 run（tag 之后才产生）。

| 项 | 值（tag 后回填） |
| --- | --- |
| tag push run id | （tag 后回填） |
| tag push run 矩阵结果 | （tag 后回填）——须同样 4 矩阵全绿（tag 树与 branch 树同源） |
| 跨版本行为差 | **已关闭（2026-10-19）**：CI 四矩阵（3.9/3.12 × ubuntu/windows）run ② 全 success；本机仅 3.8/3.12，3.9 行为差已在 CI 实测（首跑暴露并修复 py3.9 标准库名单与跨盘符断言两处） |

### 2.3 附件本体复核（`plan/05` §四.6）

| 项 | 值（tag 后回填） |
| --- | --- |
| 附件名 | `testdeck-0.1.0.tar.gz` |
| sha256 | （tag 后回填，**只写进 Release 正文**——写进包内文档会立刻失效） |
| 真下载 → `sha256sum -c` | （tag 后回填） |
| 解包树 vs `git archive v0.1.0` 解包树 `diff -r` | （tag 后回填） |
| 解包目录之外装 + `testdeck selftest` | （tag 后回填） |
| 无 `.git` 树里入仓工具可跑 | （tag 后回填） |

## 三、阶段 7 覆盖对账表

> 逐条对 `ai-tool-project-sprint` 阶段 7 出口门（A 干净环境与本体复核 / B 附件与校验和 /
> C tag 与留档时序 / D CI 与对账 / E 门自身的纪律）做覆盖：每条标 **实现**（有可跑证据）/
> **不适用 + 理由** / **待首推**（首推后才能成立）。**不静默消失**是这张表存在的理由。

| 出口门条目 | 状态 | 证据 / 理由 |
| --- | --- | --- |
| A. 干净环境验证（中立目录 + 新 venv + README 逐条） | 实现 | §1.3：`git archive` 解包到仓库外 → 新 venv → 8 条命令逐条记退出码，全 0；抓到并修掉 Pillow/字体两缺陷 |
| A. 入仓工具在无 `.git` 树里也要能跑 | 实现 | §1.3 通路就是无 `.git` 树（`git archive` 解包，无 `.git`）：`tools/check-sprint-layout.py`、`bench/run_all.py` 都在该树里跑绿 |
| A. 附件与 tag 树逐字节同源（`diff -r`） | 待首推 | 附件尚未产出（tag 后）；复核方法已写进 §2.3 |
| A. 源码包自足（`MANIFEST.in` 白名单覆盖数据目录） | 实现 | 干净环境实测：sdist 含 `plan/`（14 文件）、`bench/`、`data/synth/`、`rules/*.json`，**不含** `node_modules`（`prune` 生效）；解包目录之外可装可跑 |
| A. README 提到的附件名必须真在 Release 里 | 待首推 | 附件名 `testdeck-0.1.0.tar.gz` 已按 setuptools 规范化写进 `plan/05` 与 §2.3；"真在 Release 里"待首推后核对 |
| A. 对外附带样例产物在中立目录生成 | 不适用 | 本仓无"对外附带样例产物"（`docs/demo/demo.gif` 是随仓演示素材，不是 Release 附件；`bench/.tmp/demo.db` 不入仓） |
| B. 附件口径 = 手工源码包（非 GitHub 自动 Source code 包） | 实现 | D8：`python -m build --sdist`；干净环境实测产出 `testdeck-0.1.0.tar.gz`（自动 Source code 包的 sha256 本地复算不出来，故不用） |
| B. 附件 sha256 写进"不动点"位置 | 实现 | 口径落 `plan/05` §四.4 + §2.3：**只写 Release 正文**；包内文档只写复验方法、不写哈希 |
| B. 复核三步：真下载 → `sha256sum -c` → 解包树 `diff -r` | 待首推 | 附件与远端 tag 都还不存在；方法已定，§2.3 留槽位 |
| C. tag 树内含发布留档本体（本文件） | 实现 | 本文件 `plan/RELEASE-M6.md` 在打 tag **之前**写好并进 tag 树；`check_release.py` 的 `TAG_TREE_RELEASE_DOC` / `TAG_BEFORE_RELEASE_DOC` 判它 |
| C. DoD 打勾只能在事实落地后 | 实现 | §一 只写已成立事实，§二 的槽位如实标"tag 后回填"；不在 tag 树里打未落地的勾 |
| C. tag 之后只允许文档面提交 | 实现 | 纪律已写进本文件 §二 引言；tag 后的回填提交只动 `plan/` + `README.md`（`POST_TAG_FILES` 判它） |
| C. 随包 README 的状态行不承载"发布到哪一步" | 实现 | `README.md` 状态行写"版本 + 能力"（M6 = 脱敏发布 ✅），"是否已发布/CI 是否绿"交给 Release 页与 `plan/`——随包读者没有 Release 页，故不让他靠 README 判断发布状态 |
| C. annotated tag 两端一致 = 对象哈希一致 | 待首推 | tag 尚未创建；口径 = 只对齐 `object.sha` 会留 message/tagger/时区漂移 |
| D. push 数 = run 数对账（branch 面） | 实现 | §1.4：2 次 push main ↔ 2 条 run（39205759555 failure / 39206916398 success），逐条 `event/headBranch/headSha/conclusion` 可核 |
| D. tag push 与 branch push 各一条 run（同 sha 两条合法） | 待首推 | branch push 两条 run 已在 §1.4；**tag push run 待 tag 后回填 §2.2** |
| D. 每条已交付命令都要有一条离线 CI 冒烟 | 实现 | CI 步骤：布局门 + 裸 `testdeck selftest` + `python -m testdeck selftest` + `pytest` + `bench/run_all.py --no-perf-gate` + `bench/run_all.py --probe`；`ingest`/`export` 由 `pytest` 与 bench 套件覆盖 |
| D. 推送前先本地 `yaml.safe_load` 解析 workflow 并断言 job/step 数 | 实现 | `tests/test_readme_gate.py::test_ci_workflow_parses_and_has_required_steps`（含 M6 新增的 bench 两条断言） |
| D. bench 接入 CI（`plan/05` §五 关闭条件） | 实现 | CI 加 `bench/run_all.py --no-perf-gate` + `--probe` 两步；本机等价校验 43 项检查 exit 0 |
| E. 发布终态门可复跑（离线 / `--online` / `--pre-tag` 三模） | 实现 | `check_release.py` 支持 `--no-gh`（离线）与 `--tag`；本项目取 `--tag v0.1.0`，tag 前相关项按"待首推"如实登记 |
| E. 离线模式报 SKIP 不报 PASS | 实现 | `check_release.py --no-gh` 对 `RELEASE_ASSETS` / `REMOTE_TAG` 报 SKIP |
| E. 门要自己数"这轮扫到了几个" | 实现 | 布局门打印"文档 10 / 交接单 6 / 状态副本 4 / 里程碑 7"；`scan_leaks.py` 打印"扫描 17 个文件"；均带非空跑下界 |
| E. `gh` 是原生程序，`/tmp/...` 路径它不认 | 实现 | 本轮 `gh` 相关命令一律用仓库内相对路径或 `C:/...`（`AGENTS.md` 环境坑条） |
| E. 门对"被检查对象不存在"要报 FAIL 不崩 | 实现 | 布局门 `run_guarded` 把异常本身记 FAIL；`check_release.py` 对缺 tag 报 `TAG_EXISTS` FAIL 并继续 |

**"待首推"项汇总（4 项，全部依赖 tag / 附件，tag 与 Release 之后回填 §二）**：
① 附件与 tag 树逐字节同源；② 附件 sha256 真下载复核；③ annotated tag 两端对象哈希一致；
④ tag push run 与 tag 后追加提交的 push 数对账。
这四项在 **tag 尚未创建的此刻**在结构上不可能成立，故如实标"待首推"，**不写成已完成**。
（branch 面的 CI 与 push 数对账已在 §1.4 完成，不在本汇总内。）
