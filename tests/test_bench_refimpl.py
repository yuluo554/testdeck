"""参照实现 `bench/refimpl.py` 的算术正确性 + 独立性守门。

守门必须能**证伪**：每个"能检出"的用例都从一个临时文件造违规样本再断言报红，
不依赖"仓库当前恰好干净"（那是"绿是装饰"）。
"""

import ast
import json
import os

# ── 分位数（线性插值）──────────────────────────────────────────────────


def test_percentile_constant_window(refimpl):
    assert refimpl.percentile([1000, 1000, 1000], "0.50") == 1000


def test_percentile_interpolates_between_neighbours(refimpl):
    """索引 (n-1)*p：n=2, p=0.5 -> idx=0.5 -> 取 0 与 10 的中点。"""
    assert refimpl.percentile([0, 10], "0.50") == 5


def test_percentile_p95_linear_interpolation(refimpl):
    """n=5, p=0.95 -> idx=3.8 -> v[3] + (v[4]-v[3])*0.8 = 3 + 0.8。"""
    from fractions import Fraction

    assert refimpl.percentile([0, 1, 2, 3, 4], "0.95") == Fraction(38, 10)


def test_percentile_single_sample_and_empty(refimpl):
    assert refimpl.percentile([7], "0.50") == 7
    assert refimpl.percentile([], "0.50") is None


def test_render_is_exact_not_float(refimpl):
    """1/3 这类不终止小数按 p/q 输出；1.2 这类终止小数按十进制输出。

    用 float 会让 fail_rate 的 5% / 95% 边界随机落侧——基准就成了掷硬币。
    """
    from fractions import Fraction

    assert refimpl.render(Fraction(1, 3)) == "1/3"
    assert refimpl.render(Fraction(6, 5)) == "1.2"
    assert refimpl.render(Fraction(1, 2)) == "0.5"
    assert refimpl.render(Fraction(0)) == "0"


# ── 分型 ───────────────────────────────────────────────────────────────


def _rules(refimpl):
    return {
        "min_fail_rate": "0.05",
        "max_fail_rate": "0.95",
        "min_transitions": 3,
        "min_runs_for_flaky": 2,
        "fallback_label": "watch",
        "labels": {"broken": "x", "stable": "x", "flaky": "x", "watch": "x"},
    }


def test_classify_broken_and_stable(refimpl):
    rules = _rules(refimpl)
    assert refimpl.compute_profile(["fail"] * 5, rules)["label"] == "broken"
    assert refimpl.compute_profile(["pass"] * 5, rules)["label"] == "stable"


def test_classify_flaky_needs_transitions_threshold(refimpl):
    rules = _rules(refimpl)
    # 交替 6 段 -> 5 次翻转，fail_rate 约 0.5 -> flaky
    history = ["pass", "fail", "pass", "fail", "pass", "fail"]
    profile = refimpl.compute_profile(history, rules)
    assert profile["transitions"] == 5
    assert profile["label"] == "flaky"


def test_classify_watch_when_transitions_below_threshold(refimpl):
    rules = _rules(refimpl)
    history = ["pass", "fail", "pass", "pass", "pass", "pass"]  # transitions = 2
    profile = refimpl.compute_profile(history, rules)
    assert profile["transitions"] == 2
    assert profile["label"] == "watch"


def test_skip_and_missing_do_not_count_or_create_transition(refimpl):
    """K4 口径：skip/missing 不进分母、不制造 transition。"""
    rules = _rules(refimpl)
    history = ["pass", "skip", "fail", "missing", "pass"]
    profile = refimpl.compute_profile(history, rules)
    assert profile["counted_runs"] == 3
    assert profile["passes"] == 2
    assert profile["fails"] == 1
    assert profile["fail_rate"] == "1/3"
    assert profile["transitions"] == 2  # pass->fail, fail->pass（跳过中间的 skip/missing）
    assert profile["flaky_score"] == "1"


def test_insufficient_history_falls_back_to_watch(refimpl):
    """窗口 run 数 < min_runs_for_flaky -> 一律 watch，不得输出 flaky。"""
    rules = _rules(refimpl)
    assert refimpl.compute_profile(["pass"], rules)["label"] == "watch"
    assert refimpl.compute_profile([], rules)["label"] == "watch"


def test_zero_counted_runs_is_watch_not_stable(refimpl):
    """全 skip/missing -> fail_rate 是 0/0、**无定义**（None）-> 必须落 watch。

    不得因为 `fails == 0` 就判成 `stable`：那会让 stable 计数虚高，
    把"这个用例根本没在跑"这类真问题藏起来。`fail_rate` 渲染成 `"0"` 同样有害
    ——它与"跑过且从没失败"撞车（K34）；此处钉住它必须是 ``None``。
    """
    rules = _rules(refimpl)
    profile = refimpl.compute_profile(["skip", "missing", "skip", "missing"], rules)
    assert profile["counted_runs"] == 0
    assert profile["label"] == "watch"
    assert profile["fail_rate"] is None, "零计数样本的 fail_rate 必须无定义，不是 0"


# ── 回归判定（边界计入）────────────────────────────────────────────────


def _slow_rules():
    return {"regression_ratio": "1.2", "regression_delta_ms": 200}


def test_regression_boundary_ratio_and_delta_exact(refimpl):
    """ratio 恰 1.2 且 delta 恰 200ms -> 判回归（两边界都是 >=）。"""
    hit, note = refimpl.regression(1000, 1200, _slow_rules())
    assert hit is True and ">=" in note


def test_regression_ratio_exact_but_delta_below(refimpl):
    hit, _ = refimpl.regression(900, 1080, _slow_rules())  # ratio 恰 1.2，delta 180ms
    assert hit is False


def test_regression_ratio_below_and_above(refimpl):
    assert refimpl.regression(1000, 1199, _slow_rules())[0] is False
    assert refimpl.regression(1000, 1201, _slow_rules())[0] is True


def test_regression_delta_exact_and_below_and_above(refimpl):
    assert refimpl.regression(500, 700, _slow_rules())[0] is True   # delta 恰 200
    assert refimpl.regression(500, 699, _slow_rules())[0] is False  # delta 199
    assert refimpl.regression(500, 701, _slow_rules())[0] is True   # delta 201


def test_regression_undefined_base_is_not_a_verdict(refimpl):
    """base_p50 == 0 -> 不判回归（返回 None），也不谎报"无回归"（False）。"""
    hit, note = refimpl.regression(0, 500, _slow_rules())
    assert hit is None and note == "undefined_base"
    assert refimpl.regression(None, 500, _slow_rules())[0] is None


# ── 真值台账自检能证伪 ─────────────────────────────────────────────────


def test_verify_ledger_detects_tampered_expectation(refimpl, repo_root):
    """把真值里的一条期望改错，复算必须报出来（防"绿是装饰"）。"""
    path = os.path.join(repo_root, "data", "synth", "expect.json")
    with open(path, "r", encoding="utf-8") as fh:
        ledger = json.load(fh)
    assert refimpl.verify_ledger(ledger) == [], "登记台账本身应自洽"

    tampered = json.loads(json.dumps(ledger))
    original = tampered["anchors"][0]["expected"]["label"]
    tampered["anchors"][0]["expected"]["label"] = "flaky" if original != "flaky" else "stable"
    problems = refimpl.verify_ledger(tampered)
    assert problems, "篡改期望后复算没有报红"
    assert any("label" in p for p in problems)


def test_find_observed_keys_catches_nested(refimpl):
    """真值不得存 `observed` 类字段——嵌套也要抓到。"""
    assert refimpl._find_observed_keys({"a": {"observed_label": 1}}) != []
    assert refimpl._find_observed_keys({"a": [{"observed": 1}]}) != []


def test_committed_ledger_has_no_observed_keys(refimpl, repo_root):
    path = os.path.join(repo_root, "data", "synth", "expect.json")
    with open(path, "r", encoding="utf-8") as fh:
        ledger = json.load(fh)
    assert refimpl._find_observed_keys(ledger) == []


# ── 独立性守门（AST + 变异验证）───────────────────────────────────────


def test_refimpl_has_no_production_import(run_all, repo_root):
    problems = run_all.no_production_import_problems(
        os.path.join(repo_root, "bench", "refimpl.py"))
    assert problems == [], "参照实现 import 了生产包：%s" % problems


def test_guard_detects_injected_production_import(run_all, tmp_path):
    """变异验证：临时造一个带违规导入的样本，守门必须报红。

    这段是"守门本身可证伪"的证据——不做它，上面那条 pass 可能只是因为
    守门永远返回 []。
    """
    target = tmp_path / "mutated.py"
    target.write_text("from testdeck import model\n", encoding="utf-8")
    problems = run_all.no_production_import_problems(str(target))
    assert problems, "注入违规导入后守门没有报红"


def test_guard_detects_all_import_forms(run_all, tmp_path):
    """四种写法都要抓到：import 包 / import 子模块 / from 包 / from 子模块。"""
    forms = {
        "a.py": "import testdeck\n",
        "b.py": "import testdeck.model\n",
        "c.py": "from testdeck import db\n",
        "d.py": "from testdeck.model import STATUS_PASS\n",
    }
    for name, source in forms.items():
        target = tmp_path / name
        target.write_text(source, encoding="utf-8")
        assert run_all.no_production_import_problems(str(target)), "漏检：%s" % source.strip()


def test_guard_detects_relative_import(run_all, tmp_path):
    target = tmp_path / "rel.py"
    target.write_text("from . import model\n", encoding="utf-8")
    assert run_all.no_production_import_problems(str(target))


def test_guard_detects_dynamic_import_of_production(run_all, tmp_path):
    target = tmp_path / "dyn.py"
    target.write_text(
        "import importlib\nimportlib.import_module('testdeck.model')\n", encoding="utf-8")
    assert run_all.no_production_import_problems(str(target))


def test_guard_is_green_on_clean_sample(run_all, tmp_path):
    target = tmp_path / "clean.py"
    target.write_text("import json\nfrom fractions import Fraction\n", encoding="utf-8")
    assert run_all.no_production_import_problems(str(target)) == []


def test_refimpl_guard_check_reports_ok(run_all):
    check = run_all.refimpl_guard_check()
    assert check["ok"] is True, check["detail"]


def test_refimpl_guard_probe_detects_injection(run_all):
    """探活在临时副本上注入，断言守门报出；且**不修改**真文件。"""
    check = run_all.refimpl_guard_check(fault="inject_production_import")
    assert check["ok"] is True, "注入违规导入后守门没有报出：%s" % check["detail"]
    # 真文件未被改动
    assert run_all.no_production_import_problems(run_all.REFIMPL_PATH) == []


def test_refimpl_parses_as_python(refimpl, repo_root):
    """参照实现本身必须是合法 Python（避免"守门扫了个坏文件"）。"""
    with open(os.path.join(repo_root, "bench", "refimpl.py"), "r", encoding="utf-8") as fh:
        ast.parse(fh.read())
