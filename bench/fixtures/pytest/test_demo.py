"""最小 pytest 测试集：产出 TestDeck 的 D1 真实产物（`junit.xml`）。

设计意图：一次 `pytest` 运行同时给出**通过 / 失败 / 跳过**三种状态，
让 `bench/bench_ingest.py` 能对账三态计数，而不是只对账"全绿"这一种退化情形。

产出命令见同目录 `README.md`；本文件不属于主测试套件
（`pyproject.toml` 的 `testpaths = ["tests"]` 把收集面限制在 `tests/`）。
"""

import pytest


def _add(a, b):
    return a + b


def _div(a, b):
    if b == 0:
        return 0
    return a / b


def test_add_returns_sum():
    assert _add(2, 3) == 5


def test_add_is_commutative():
    assert _add(7, 9) == _add(9, 7)


def test_div_guards_zero():
    assert _div(1, 0) == 0


def test_div_returns_quotient():
    assert _div(9, 3) == 3


def test_deliberate_failure_fixture():
    """故意写错的期望值：让产物里稳定带一条 `failure`，供三态对账使用。"""
    assert _add(6, 1) == 8, "deliberate failure fixture: want 8, got 7"


@pytest.mark.skip(reason="not implemented yet: subtract()")
def test_not_implemented_yet_subtract():
    raise AssertionError("unreachable: this fixture is skipped on purpose")
