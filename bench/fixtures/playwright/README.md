# Playwright fixture（D3 · 真实产物）

> 本目录是 `plan/04` 数据清单里的 **D3**：Playwright 的 JUnit XML 真实产物。
> 用途：解析回归 + 用例数/失败数/skipped 对账（`bench/bench_ingest.py`）。

## 产出信息（实测 2026-10-19）

| 项 | 值 |
| --- | --- |
| 工具 | `@playwright/test` |
| 工具版本 | 1.48.2 |
| 浏览器 | Chromium 130.0.6723.31（playwright build v1140） |
| Node 版本 | v24.15.0 |
| 来源 | **本机真实运行**（非预置、非手抄） |
| 命令 | `npx playwright test`（reporter 见 `playwright.config.js`） |
| 工作目录 | 本目录 |

## 关于"Playwright 未安装"的口径更新（重要）

`plan/HANDOFF-M1.md` §4 与 `plan/05` §五记录的是 **2026-10-18 实测**："本机 `npx playwright` 未安装 → D3 用预置产物"。
本轮（**2026-10-19**）复测并取得真实工具链后，**改为真跑产出**：

- `@playwright/test@1.48.2` 经 `https://registry.npmmirror.com` 安装成功（实测可达）；
- Chromium 经 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright` 下载成功；
- 因此本 fixture 的 `produced_by.source` 写 **"本机真实运行"**，
  **不是**"预置产物"。

这条口径变更已回写 `plan/05` §五"已知未验证项"。**不要**再把本 fixture 描述成"预置产物"。

## 文件

| 文件 | 说明 |
| --- | --- |
| `package.json` / `package-lock.json` | 依赖声明与锁定（保证版本可复核） |
| `playwright.config.js` | reporter 配置（junit → `playwright.xml`，headless） |
| `tests/todo.spec.js` | 被测的最小用例集（7 条：5 通过 / 1 失败 / 1 跳过） |
| `playwright.xml` | 真实产物（入库） |
| `expected.json` | 真值（用例数 / 失败数 / errors / skipped + 各 suite 明细） |

`node_modules/` 与工具运行残留（`test-results/`）**不入仓**（见 `.gitignore`）。

## 零网络约束（重要）

测试页面由 `page.setContent()` 注入静态 HTML，**不访问任何网络地址**：
不启本地 HTTP 服务、不打开外部站点。这样产物在离线环境里可重跑，
且 XML 里不会出现任何真实域名（`scan_leaks.py` 会守这一条）。

## 复核方式

```bash
cd bench/fixtures/playwright && npm install --registry=https://registry.npmmirror.com
cd - && py -3.12 bench/fixtures/regen_fixtures.py --only playwright
py -3.12 bench/fixtures/scan_leaks.py
```

## 已知的框架差异（实测，解析层必须知道）

- Playwright 的 `<testsuite>` 的 `name` 是**文件名**（`todo.spec.js`），不是"包名/模块名"；
  `testcase@classname` 也等于文件名。这与 gotestsum（classname = 包名）不同，
  是"同一份核心形状、不同语义填充"的典型例子。
- `<skipped/>` 是**空元素**，跳过原因在 `<properties><property name="skip" value="…"/></properties>` 里，
  不在 `message` 属性上。只读 `skipped@message` 会得到空串。
- 失败用例的 `<failure>` 带 `type="FAILURE"`，正文是 CDATA 包裹的多行文本
  （含 `Call log` 与源码行号），末行是 `at <路径>:行:列`。
  原始产物此处是**绝对路径**，入库前被 `_scrub` 改写成仓库内相对路径
  （本目录里能看到 `at bench\fixtures\playwright\tests\todo.spec.js:81:40`）——
  解析层不能假设这里一定是绝对路径或一定是相对路径。

## 入库前的脱敏归一（如实声明）

`regen_fixtures.py:_scrub` 在写盘前**只做两件事**，其余字节原样保留：

1. 删除 `hostname="…"` 属性（若有）；
2. 把仓库根的绝对路径前缀改写成相对路径（`failure` 正文的 `at …` 行）。

Playwright 的 JUnit XML 实测**不带** `hostname` 属性，故本目录实际只触发了第 2 条。
