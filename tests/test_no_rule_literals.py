"""零字面量门禁（`plan/04` §四「零字面量门禁」）：判定层代码里不得出现规则阈值。

判据：把**规则包**（`src/testdeck/rules/*.json`）里所有数值叶子收集成一份阈值集合，
再 AST 扫描 `flaky.py` / `slow.py` 的数值常量；凡等于某个阈值即红。

**豁免口径**（写进白名单并注明理由，且**穷尽式**——登记了却不出现 → 判红）：

- `0` / `1`：结构性常量（`n < 2` 用 `> 1` 表达、`Fraction(0)` 的初值、布尔语义），
  不是"可调的阈值"；
- 其余一律不许。想改判定行为，改**规则包**，不改代码。

**变异验证**：往临时副本里注入一行含阈值的代码，扫描器必须报红——否则这条门
只是"仓库当前恰好干净"，不是"门真的在扫"。
"""

import ast
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from testdeck import rules

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "testdeck"

#: 被判定的文件（`plan/04` §四 点名的三个：判定层 + 报告模型）。
#: M5 起 `slow.py` 与 `report_model.py` 都已落地，三个文件**全部存在且都被扫**——
#: `test_flaky_module_exists_and_is_scanned` 断言扫描面非空且三份都在。
SCANNED_FILES = ("flaky.py", "slow.py", "report_model.py")

#: 结构性常量白名单（**穷尽式**：登记了却在被扫文件里不出现 → 判红）。
#: 只登记"与阈值语义无关"的整数；`0`/`1` 是索引、初值、布尔语义这类结构常量。
ALLOWED_STRUCTURAL = {
    Decimal("0"): "结构性初值 / 计数起点（不是可调阈值）",
    Decimal("1"): "结构性步长 / `n > 1` 的样本数判据（不是可调阈值）",
}


def _numeric_leaves(node, found):
    """递归收集规则 JSON 里的数值叶子（跳过 `version` 这类字符串）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "version":
                continue
            _numeric_leaves(value, found)
    elif isinstance(node, list):
        for item in node:
            _numeric_leaves(item, found)
    elif isinstance(node, bool):
        return
    elif isinstance(node, (int, float, str)):
        try:
            found.add(Decimal(str(node)))
        except InvalidOperation:
            pass


def rule_thresholds():
    """三份规则包里所有数值叶子（阈值集合）——门禁的判据面。"""
    found = set()
    for name in rules.RULE_FILES:
        data = rules.load_rule_file(name)
        _numeric_leaves(data, found)
    return found


def _numeric_constants(path):
    """一个文件里的数值常量 ``[(行号, Decimal)]``（`bool` 不算数值）。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            out.append((node.lineno, Decimal(str(node.value))))
    return out


def scan_literal_problems(root=SRC):
    """扫描判定层文件的数值常量；返回 ``(违规清单, 命中豁免清单, 已扫文件数)``。"""
    thresholds = rule_thresholds()
    violations = []
    used_exemptions = set()
    scanned = 0
    for name in SCANNED_FILES:
        path = Path(root) / name
        if not path.is_file():
            continue
        scanned += 1
        for lineno, value in _numeric_constants(path):
            if value in ALLOWED_STRUCTURAL:
                used_exemptions.add(value)
                continue
            if value in thresholds:
                violations.append("%s:%d 出现规则阈值字面量 %s（应改规则包）"
                                  % (name, lineno, value))
    return violations, used_exemptions, scanned


# ── 判据 ───────────────────────────────────────────────────────────────


def test_flaky_module_exists_and_is_scanned():
    """非空跑自证：三个被扫文件（`flaky.py` / `slow.py` / `report_model.py`）全在。"""
    _violations, _used, scanned = scan_literal_problems()
    assert scanned == len(SCANNED_FILES), "扫描面不完整：只扫到 %d 个" % scanned
    for name in SCANNED_FILES:
        assert (SRC / name).is_file(), "%s 不存在（扫描面失效）" % name


def test_no_rule_literals_in_decision_layer():
    violations, _used, _scanned = scan_literal_problems()
    assert violations == [], (
        "判定层出现规则阈值字面量：%s\n"
        "（阈值只有规则包一个来源；要改行为就改 src/testdeck/rules/*.json）" % violations)


def test_exemptions_are_exhaustive_not_a_dumping_ground():
    """白名单必须被用满：登记的 `0`/`1` 若在判定层里不出现 → 判红（防白名单腐化）。"""
    _violations, used, _scanned = scan_literal_problems()
    unused = sorted(set(ALLOWED_STRUCTURAL) - used)
    assert unused == [], "结构性常量白名单登记了却不存在：%s" % unused


def test_threshold_face_is_not_empty():
    """阈值集合本身要非空——否则"没有违规"只是因为集合是空的。"""
    thresholds = rule_thresholds()
    assert thresholds, "规则包里一个数值都没有（判据失效）"
    # 抽查三条口径里点名的阈值都在集合里
    for value in ("0.05", "0.95", "1.2", "200"):
        assert Decimal(value) in thresholds, value


def test_scan_detects_injected_threshold_literal(tmp_path):
    """**变异验证**：往副本注入一行含阈值的代码，扫描器必须报红。"""
    copy = tmp_path / "flaky.py"
    copy.write_text(
        (SRC / "flaky.py").read_text(encoding="utf-8")
        + "\nDEFAULT_MIN_TRANSITIONS = 3  # probe injection\n",
        encoding="utf-8",
    )
    violations, _used, scanned = scan_literal_problems(tmp_path)
    assert scanned == 1
    assert any("3" in item for item in violations), violations


def test_scan_detects_injected_slow_threshold(tmp_path):
    """`slow.py` 的阈值字面量（`200` = `regression_delta_ms`）注入也要被检出。"""
    copy = tmp_path / "slow.py"
    copy.write_text(
        (SRC / "slow.py").read_text(encoding="utf-8")
        + "\nDEFAULT_DELTA_MS = 200  # probe injection\n",
        encoding="utf-8",
    )
    violations, _used, _scanned = scan_literal_problems(tmp_path)
    assert any("200" in item for item in violations), violations


def test_scan_detects_injected_decimal_threshold(tmp_path):
    """十进制阈值（`0.05`）注入也要被检出。"""
    copy = tmp_path / "flaky.py"
    copy.write_text(
        (SRC / "flaky.py").read_text(encoding="utf-8")
        + "\nFLOOR = 0.05  # probe injection\n",
        encoding="utf-8",
    )
    violations, _used, _scanned = scan_literal_problems(tmp_path)
    assert any("0.05" in item for item in violations), violations


def test_clean_copy_stays_green(tmp_path):
    """对照组：只复制不改的副本必须干净（防"扫描器见谁咬谁"）。"""
    (tmp_path / "flaky.py").write_text(
        (SRC / "flaky.py").read_text(encoding="utf-8"), encoding="utf-8")
    violations, _used, scanned = scan_literal_problems(tmp_path)
    assert scanned == 1
    assert violations == [], violations


def test_structural_zero_and_one_are_not_flagged(tmp_path):
    """`0` / `1` 这类结构常量不该被误判（否则白名单会退化成垃圾桶）。"""
    (tmp_path / "flaky.py").write_text(
        "def f(n):\n    return 0 if n > 1 else 1\n", encoding="utf-8")
    violations, used, _scanned = scan_literal_problems(tmp_path)
    assert violations == [], violations
    assert Decimal("0") in used and Decimal("1") in used
