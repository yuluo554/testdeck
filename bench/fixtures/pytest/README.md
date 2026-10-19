# pytest fixture（D1 · 真实产物）

> 本目录是 `plan/04` 数据清单里的 **D1**：pytest 的 JUnit XML 真实产物。
> 用途：解析回归 + 用例数/失败数/skipped 对账（`bench/bench_ingest.py`）。

## 产出信息（实测 2026-10-19）

| 项 | 值 |
| --- | --- |
| 工具 | pytest |
| 工具版本 | 8.4.2 |
| Python 版本 | 3.12.10 |
| 来源 | **本机真实运行**（非预置、非手抄） |
| 命令 | `python -m pytest test_demo.py --junitxml=junit.xml -p no:cacheprovider -q` |
| 工作目录 | 本目录（相对路径产出，避免把仓库绝对路径写进 XML） |

## 文件

| 文件 | 说明 |
| --- | --- |
| `test_demo.py` | 被测的最小测试集（6 条：4 通过 / 1 失败 / 1 跳过） |
| `junit.xml` | 真实产物（入库）；`testsuite` 声明 `tests="6" failures="1" skipped="1"` |
| `expected.json` | 真值（用例数 / 失败数 / errors / skipped + 各 suite 明细） |

## 为什么产物里带失败与跳过

只产"全绿"的 XML 会让三态对账退化成"对了个 0"。本 fixture 刻意各留一条：

- `test_deliberate_failure_fixture` —— 故意写错的断言，稳定产出 1 条 `failure`；
- `test_not_implemented_yet_subtract` —— `pytest.mark.skip`，稳定产出 1 条 `skipped`。

## 复核方式（两条独立命令）

```bash
# ① 重新产出（真跑 pytest，并当场三条通道对账）
py -3.12 bench/fixtures/regen_fixtures.py --only pytest

# ② 只读扫描：入库产物里不得出现本机绝对路径 / 机器名 / 真实域名
py -3.12 bench/fixtures/scan_leaks.py
```

## 入库前的脱敏归一（如实声明）

`regen_fixtures.py:_scrub` 在写盘前**只做两件事**，其余字节原样保留：

1. 删除 `testsuite` 上的 `hostname="…"` 属性（机器名）；
2. 把仓库根的绝对路径前缀改写成相对路径（pytest 的 skip 文本会带绝对路径）。

这两条都可复核：把 `_scrub` 的两条规则与本文件的描述对照即可。
**没有**做过任何"改写用例名 / 伪造计数 / 调换状态"的动作。

## 已知的框架差异（实测，解析层必须知道）

- pytest 的 `<testsuites>` **根节点不带 totals**，声明值只在 `<testsuite>` 上；
  解析器不能假设"根一定有总数"，否则会把 6 条读成 0。
- pytest 的 `skipped` 文本里含源码绝对路径——这是入库脱敏必须处理的一项。
