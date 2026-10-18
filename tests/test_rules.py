"""规则包：缺失即报错（引擎零默认值），阈值以十进制字符串精确比较。"""

import json
import os
from decimal import Decimal

import pytest

from testdeck import rules


def test_rules_dir_is_inside_package():
    """规则包必须在包内（安装面可证伪）：装好的 CLI 读不到 = 项目没交付。"""
    root = os.path.dirname(os.path.abspath(rules.__file__))
    assert rules.rules_dir() == os.path.join(root, "rules")


@pytest.mark.parametrize("name", ["flaky.json", "slow.json", "view.json"])
def test_rule_files_exist_and_parse(name):
    data = rules.load_rule_file(name)
    assert isinstance(data, dict)
    assert data.get("version") == "1"


def test_load_all_returns_decimal_thresholds():
    loaded = rules.load_all()
    assert loaded["flaky"]["min_fail_rate"] == Decimal("0.05")
    assert loaded["flaky"]["max_fail_rate"] == Decimal("0.95")
    assert loaded["slow"]["regression_ratio"] == Decimal("1.2")
    assert loaded["slow"]["regression_delta_ms"] == 200
    assert loaded["view"]["write_generated_at"] is False


def test_thresholds_are_exact_not_float():
    """0.1 + 0.2 != 0.3 的浮点坑：阈值必须能精确比较。"""
    ratio = rules.load_slow_rules()["regression_ratio"]
    assert ratio == Decimal("1.2")
    assert Decimal("1.2") == Decimal(120) / Decimal(100)
    assert 0.1 + 0.2 != 0.3  # 反证：浮点在这里不可用


def test_missing_rule_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rules, "rules_dir", lambda: str(tmp_path))
    with pytest.raises(rules.RulesError):
        rules.load_rule_file("flaky.json")


def test_broken_json_raises(tmp_path, monkeypatch):
    (tmp_path / "flaky.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(rules, "rules_dir", lambda: str(tmp_path))
    with pytest.raises(rules.RulesError):
        rules.load_rule_file("flaky.json")


def test_missing_required_key_raises(tmp_path, monkeypatch):
    (tmp_path / "flaky.json").write_text(
        json.dumps({"version": "1", "flaky": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(rules, "rules_dir", lambda: str(tmp_path))
    with pytest.raises(rules.RulesError):
        rules.load_flaky_rules()


def test_inverted_threshold_raises(tmp_path, monkeypatch):
    payload = {
        "version": "1",
        "flaky": {
            "min_fail_rate": "0.95",
            "max_fail_rate": "0.05",
            "min_transitions": 3,
            "min_runs_for_flaky": 2,
            "fallback_label": "watch",
            "labels": {},
        },
    }
    (tmp_path / "flaky.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(rules, "rules_dir", lambda: str(tmp_path))
    with pytest.raises(rules.RulesError):
        rules.load_flaky_rules()


def test_write_generated_at_true_is_rejected(tmp_path, monkeypatch):
    """导出写生成时刻 = 破坏可重放，规则层直接拒绝（不是文档里的君子协定）。"""
    view = json.loads(
        open(
            os.path.join(rules.rules_dir(), "view.json"), encoding="utf-8"
        ).read()
    )
    view["export"]["write_generated_at"] = True
    (tmp_path / "view.json").write_text(json.dumps(view), encoding="utf-8")
    monkeypatch.setattr(rules, "rules_dir", lambda: str(tmp_path))
    with pytest.raises(rules.RulesError):
        rules.load_view_rules()
