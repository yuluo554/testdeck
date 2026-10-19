# gotestsum fixture（D2 · 真实产物）

> 本目录是 `plan/04` 数据清单里的 **D2**：gotestsum 的 JUnit XML 真实产物。
> 用途：解析回归 + 用例数/失败数/skipped 对账（`bench/bench_ingest.py`）。

## 产出信息（实测 2026-10-19）

| 项 | 值 |
| --- | --- |
| 工具 | gotestsum |
| 工具版本 | v1.12.0（`go install gotest.tools/gotestsum@v1.12.0`） |
| Go 版本 | `go1.23.4 windows/amd64` |
| 来源 | **本机真实运行**（非预置、非手抄） |
| 命令 | `gotestsum --junitfile gotestsum.xml --junitfile-testsuite-name short --junitfile-testcase-classname short ./...` |
| 工作目录 | 本目录 |

## 关于"本机无 Go"的口径更新（重要）

`plan/HANDOFF-M1.md` §4 与 `plan/05` §五记录的是 **2026-10-18 实测**："本机无 Go 工具链 → D2 用预置产物"。
本轮（**2026-10-19**）复测并取得真实工具链后，**改为真跑产出**：

- `go1.23.4` 经 `https://dl.google.com/go/` 下载（实测可达）；
- `gotestsum v1.12.0` 经模块代理 `https://goproxy.cn,direct` 安装成功（实测可达）；
- 因此本 fixture 的 `produced_by.source` 写 **"本机真实运行"**，
  **不是**"预置产物"。

这条口径变更已回写 `plan/05` §五"已知未验证项"。**不要**再把本 fixture 描述成"预置产物"。

## 文件

| 文件 | 说明 |
| --- | --- |
| `go.mod` / `calc.go` / `calc_test.go` | 被测的最小 Go 工程（5 条测试：3 通过 / 1 失败 / 1 跳过；只用标准库，离线可跑） |
| `gotestsum.xml` | 真实产物（入库） |
| `expected.json` | 真值（用例数 / 失败数 / errors / skipped + 各 suite 明细） |

## 复核方式

```bash
# 需要 go 与 gotestsum 在 PATH 上（缺则脚本打印 SKIP，不产出任何东西）
py -3.12 bench/fixtures/regen_fixtures.py --only gotestsum
py -3.12 bench/fixtures/scan_leaks.py
```

## 已知的框架差异（实测，解析层必须知道）

- gotestsum 的 `<testsuites>` **根节点不写 `skipped` 属性**，尽管它确实含一个
  `<skipped/>` 用例、且 stdout 摘要报 `1 skipped`。
  → 解析器与对账脚本**不得把"属性缺失"当成 0**：那会让"框架声明值 vs 元素重数"
  出现假红（0 != 1）。`expected.json` 的 `declared_in_xml` 用 `null` 明确标出"未声明"。
- `expected.json` 的 `totals` 是**元素重数**（文件内容），不是抄的框架声明值；
  三条通道（XML 属性 / 元素重数 / stdout 摘要）在 `regen_fixtures.py` 里当场对账。
- `<failure>` 的文本是 gotestsum 把 `go test -v` 的输出整段塞进来的，
  首行不是"断言语句"而是 `=== RUN …`。解析"stack 首行"口径时要留意这一层包裹。
