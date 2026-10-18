"""规则包加载（阈值 / 窗口 / 枚举的唯一运行时来源）。

设计纪律：
  - **引擎零默认值**：规则文件缺失或键缺失 -> 抛 ``RulesError``，不回落硬编码默认值。
    这是"代码里藏第二份口径"的根治手段。
  - 规则包随包安装（``src/testdeck/rules/*.json``），不放仓库 ``data/``——
    否则装好的 CLI 读不到规则（源码态能跑、安装态炸）。
  - 十进制阈值以**字符串**存放，加载时转 ``Decimal``：浮点会引入 0.1+0.2 类漂移，
    而 `fail_rate` 的边界判定（5% / 95% / 1.2x）必须精确。
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

RULES_DIRNAME = "rules"
RULE_FILES = ("flaky.json", "slow.json", "view.json")


class RulesError(RuntimeError):
    """规则包缺失、不可解析或缺少必需键。"""


def rules_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), RULES_DIRNAME)


def load_rule_file(name):
    path = os.path.join(rules_dir(), name)
    if not os.path.isfile(path):
        raise RulesError("规则文件缺失：%s" % name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RulesError("规则文件不可解析：%s（%s）" % (name, exc))
    if not isinstance(data, dict):
        raise RulesError("规则文件根节点必须是对象：%s" % name)
    return data


def _require(mapping, key, where):
    if not isinstance(mapping, dict) or key not in mapping:
        raise RulesError("规则缺少必需键：%s.%s" % (where, key))
    return mapping[key]


def _decimal(value, where):
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - 规则值非法一律归为规则错误
        raise RulesError("规则值不是十进制数：%s = %r" % (where, value))


def load_flaky_rules():
    data = load_rule_file("flaky.json")
    flaky = _require(data, "flaky", "flaky.json")
    rules = {
        "min_fail_rate": _decimal(_require(flaky, "min_fail_rate", "flaky"), "flaky.min_fail_rate"),
        "max_fail_rate": _decimal(_require(flaky, "max_fail_rate", "flaky"), "flaky.max_fail_rate"),
        "min_transitions": int(_require(flaky, "min_transitions", "flaky")),
        "min_runs_for_flaky": int(_require(flaky, "min_runs_for_flaky", "flaky")),
        "fallback_label": str(_require(flaky, "fallback_label", "flaky")),
        "labels": dict(_require(flaky, "labels", "flaky")),
    }
    if rules["min_fail_rate"] > rules["max_fail_rate"]:
        raise RulesError("flaky.min_fail_rate 不得大于 flaky.max_fail_rate")
    if rules["min_transitions"] < 1:
        raise RulesError("flaky.min_transitions 必须 >= 1")
    return rules


def load_slow_rules():
    data = load_rule_file("slow.json")
    slow = _require(data, "slow", "slow.json")
    pct = _require(data, "percentile", "slow.json")
    rules = {
        "slow_ms": int(_require(slow, "slow_ms", "slow")),
        "regression_ratio": _decimal(
            _require(slow, "regression_ratio", "slow"), "slow.regression_ratio"
        ),
        "regression_delta_ms": int(_require(slow, "regression_delta_ms", "slow")),
        "waterfall_width": int(_require(slow, "waterfall_width", "slow")),
        "p50": _decimal(_require(pct, "p50", "percentile"), "percentile.p50"),
        "p95": _decimal(_require(pct, "p95", "percentile"), "percentile.p95"),
        "index_formula": str(_require(pct, "index_formula", "percentile")),
    }
    if rules["regression_delta_ms"] < 0:
        raise RulesError("slow.regression_delta_ms 不得为负")
    if not (0 <= rules["p50"] <= 1 and 0 <= rules["p95"] <= 1):
        raise RulesError("percentile 的 p50/p95 必须在 [0, 1] 内")
    return rules


def load_view_rules():
    data = load_rule_file("view.json")
    view = _require(data, "view", "view.json")
    export = _require(data, "export", "view.json")
    rules = {
        "sparkline_runs": int(_require(view, "sparkline_runs", "view")),
        "min_width_single_column": int(_require(view, "min_width_single_column", "view")),
        "summary_fields": list(_require(view, "summary_fields", "view")),
        "tree_sort": str(_require(view, "tree_sort", "view")),
        "formats": list(_require(export, "formats", "export")),
        "fail_on": list(_require(export, "fail_on", "export")),
        "json_indent": int(_require(export, "json_indent", "export")),
        "json_ensure_ascii": bool(_require(export, "json_ensure_ascii", "export")),
        "write_generated_at": bool(_require(export, "write_generated_at", "export")),
    }
    if rules["sparkline_runs"] < 1:
        raise RulesError("view.sparkline_runs 必须 >= 1")
    if rules["write_generated_at"]:
        raise RulesError("view.export.write_generated_at 必须为 false（导出必须可重放）")
    return rules


def load_all():
    """一次性加载并交叉校验三份规则包。"""
    return {
        "flaky": load_flaky_rules(),
        "slow": load_slow_rules(),
        "view": load_view_rules(),
    }
