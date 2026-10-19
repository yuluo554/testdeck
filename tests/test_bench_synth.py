"""合成语料与真值台账：可重放、可证伪、模式覆盖、假数据白名单。

这些用例是 M1 DoD 里"生成器自证"那一行的机器化：
`--check` 位级一致、坏真值能报红、`expect.json` 不含 `observed`、四类分型 / missing /
skip / transitions 1..5 / 回归六边界**真的存在**（"我打算生成" != "生成出来了"）。
"""

import json
import os

SMALL = {"runs": 40, "cases": 600, "sample_size": 60}


def _committed_ledger(repo_root):
    path = os.path.join(repo_root, "data", "synth", "expect.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _committed_params(repo_root):
    """用**台账自己声明的参数**跑 --check，避免测试与生成参数各写一套。"""
    gen = _committed_ledger(repo_root)["generator"]
    return gen["seed"], gen["params"]


# ── 可重放 ─────────────────────────────────────────────────────────────


def test_same_seed_is_byte_identical(gen_runs, tmp_path):
    """同 seed 两次生成 -> 逐字节一致（两个独立进程之外，这里再验同进程序列化）。"""
    common = ["--seed", "7", "--runs", "20", "--cases", "120", "--sample-size", "20"]
    assert gen_runs.main(common + ["--ledger", str(tmp_path / "a.json")]) == 0
    assert gen_runs.main(common + ["--ledger", str(tmp_path / "b.json")]) == 0
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_different_seed_changes_output(gen_runs, tmp_path):
    """确定性不能退化成"永远输出同一份"——换 seed 必须换内容。"""
    for seed, name in (("7", "s7.json"), ("8", "s8.json")):
        assert gen_runs.main(["--seed", seed, "--runs", "20", "--cases", "120",
                              "--sample-size", "20", "--ledger", str(tmp_path / name)]) == 0
    assert (tmp_path / "s7.json").read_bytes() != (tmp_path / "s8.json").read_bytes()


def test_check_matches_committed_ledger_byte_for_byte(gen_runs, repo_root):
    seed, params = _committed_params(repo_root)
    argv = ["--seed", str(seed), "--runs", str(params["runs"]), "--cases", str(params["cases"]),
            "--sample-size", str(params["sample_size"]), "--check",
            "--ledger", os.path.join(repo_root, "data", "synth", "expect.json")]
    assert gen_runs.main(argv) == 0


def test_bare_check_works_with_defaults(gen_runs):
    """裸跑 `gen_runs.py --check`（命令速查里那条）必须通过。

    这钉住"**默认参数 == 入库台账参数**"。M1 实测踩过：`--sample-size` 默认写成
    200、入库台账却是用 50 生成的，裸命令于是假红——文档里的命令必须真能跑。
    """
    assert gen_runs.main(["--check"]) == 0


def test_check_does_not_write(gen_runs, tmp_path, repo_root):
    """`--check` 只校验不写盘：被检查的文件 mtime/内容都不动。"""
    target = tmp_path / "ledger.json"
    assert gen_runs.main(["--seed", "7", "--runs", "20", "--cases", "120",
                          "--sample-size", "20", "--ledger", str(target)]) == 0
    before = target.read_bytes()
    assert gen_runs.main(["--seed", "7", "--runs", "20", "--cases", "120",
                          "--sample-size", "20", "--check", "--ledger", str(target)]) == 0
    assert target.read_bytes() == before


def test_check_reports_red_on_bad_ledger(gen_runs, tmp_path, repo_root):
    """坏真值必须报红（DoD：`--check` 能对坏真值报红）。"""
    seed, params = _committed_params(repo_root)
    with open(os.path.join(repo_root, "data", "synth", "expect.json"), "r",
              encoding="utf-8") as fh:
        ledger = json.load(fh)
    ledger["anchors"][0]["expected"]["label"] = "definitely-not-a-label"
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    argv = ["--seed", str(seed), "--runs", str(params["runs"]), "--cases", str(params["cases"]),
            "--sample-size", str(params["sample_size"]), "--check", "--ledger", str(broken)]
    assert gen_runs.main(argv) == 1


def test_check_missing_ledger_is_red(gen_runs, tmp_path):
    argv = ["--seed", "7", "--runs", "20", "--cases", "120", "--sample-size", "20",
            "--check", "--ledger", str(tmp_path / "nope.json")]
    assert gen_runs.main(argv) == 1


# ── 真值纪律 ───────────────────────────────────────────────────────────


def test_committed_ledger_has_input_and_expected_sides(refimpl, repo_root):
    """真值必须同时带**输入侧**与**期望侧**，且能由输入侧独立复算。"""
    ledger = _committed_ledger(repo_root)
    assert ledger["anchors"] and ledger["samples"]
    for record in ledger["anchors"] + ledger["samples"]:
        case = record["case"]
        assert "history" in case and "timings_ms" in case, "缺输入侧"
        assert "label" in record["expected"], "缺期望侧"
    assert refimpl.verify_ledger(ledger) == []


def test_committed_ledger_has_no_observed_fields(refimpl, repo_root):
    assert refimpl._find_observed_keys(_committed_ledger(repo_root)) == []


def test_rules_snapshot_matches_production_rules(gen_runs, repo_root):
    """台账里的阈值快照必须与生产规则包一致（否则基准在跟另一套口径对账）。"""
    snapshot = _committed_ledger(repo_root)["rules_snapshot"]
    assert snapshot == gen_runs.load_rules_snapshot()


def test_ledger_totals_match_recomputation(gen_runs, refimpl, repo_root):
    """从头重建语料并用参照实现复算汇总，必须与登记值一致。"""
    seq, params = _committed_params(repo_root)
    ledger = gen_runs.build_ledger(seq, params["runs"], params["cases"], params["sample_size"])
    registered = _committed_ledger(repo_root)["expected_totals"]
    assert refimpl.recompute_totals(gen_runs.build_corpus(params["runs"], params["cases"], seq),
                                    ledger["rules_snapshot"]) == registered


# ── 模式覆盖（生成期断言真的在断言）──────────────────────────────────


def test_generation_assertions_pass(gen_runs):
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    assert gen_runs.run_generation_assertions(ledger) == []


def test_generation_assertions_are_not_vacuous(gen_runs):
    """把一条分型改错，断言必须报出来——证明这组断言不是恒真。"""
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    for record in ledger["anchors"]:
        record["expected"]["label"] = "stable"
    problems = gen_runs.run_generation_assertions(ledger)
    assert problems, "篡改后生成期断言没有报红"


def test_anchors_cover_four_labels(gen_runs):
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    labels = {r["expected"]["label"] for r in ledger["anchors"]}
    assert labels == {"stable", "flaky", "broken", "watch"}


def test_anchors_cover_transitions_gradient_1_to_5(gen_runs):
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    transitions = {r["expected"]["transitions"] for r in ledger["anchors"]}
    assert {1, 2, 3, 4, 5} <= transitions


def test_corpus_contains_missing_and_skip(gen_runs):
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    counts = ledger["expected_totals"]["status_counts"]
    assert counts["missing"] >= 1
    assert counts["skip"] >= 1


def test_corpus_contains_real_regressions_and_non_regressions(gen_runs, repo_root):
    """语料必须同时含"能检出"与"不误报"两侧，否则 M5 的基准半边是空的。"""
    totals = _committed_ledger(repo_root)["expected_totals"]
    assert totals["regression_true"] >= 1
    assert totals["regression_false"] >= 1


def test_regression_boundary_anchors_are_exact(gen_runs):
    """六边界锚点必须真的存在且判定正确（ratio/delta 恰好、略低、略高）。"""
    ledger = gen_runs.build_ledger(42, SMALL["runs"], SMALL["cases"], SMALL["sample_size"])
    by_name = {r["anchor"]: r["expected"] for r in ledger["anchors"]}
    expected = {
        "reg_ratio_exact_delta_exact": True,
        "reg_ratio_exact_delta_below": False,
        "reg_ratio_below": False,
        "reg_ratio_above": True,
        "reg_delta_exact_ratio_above": True,
        "reg_delta_below": False,
        "reg_delta_above": True,
        "reg_undefined_base": None,
    }
    for anchor, want in expected.items():
        assert anchor in by_name, "缺边界锚点 %s" % anchor
        assert by_name[anchor]["regression"] is want, anchor


def test_k_transitions_produces_exact_counts(gen_runs):
    """构造器自身：翻转数精确、块长和等于 n（含边界 n 恰好等于 k+1）。"""
    for n, k in ((12, 1), (12, 3), (12, 5), (6, 5), (200, 3), (200, 5)):
        seq = gen_runs.k_transitions(n, k)
        assert len(seq) == n
        assert sum(1 for a, b in zip(seq, seq[1:]) if a != b) == k
    # 装不下时必须报错，而不是悄悄给个错序列
    try:
        gen_runs.k_transitions(3, 5)
    except ValueError:
        pass
    else:  # pragma: no cover - 走到这里说明构造器在骗人
        raise AssertionError("k+1 > n 时应当报错")


def test_window_around_has_exact_median(gen_runs):
    """对称窗口的中位数必须恰为 center（回归边界要精确可控）。"""
    for length in (1, 2, 3, 4, 5, 100):
        window = gen_runs.window_around(length, 777)
        assert len(window) == length
        assert gen_runs.refimpl.percentile(window, "0.50") == 777


# ── 假数据白名单 ───────────────────────────────────────────────────────


def test_fake_data_whitelist(repo_root):
    """分支 / 仓库名 / commit / run id 全部落在白名单内，零真实标识。"""
    ledger = _committed_ledger(repo_root)
    assert ledger["runs"], "runs 为空（判据空转）"
    for run in ledger["runs"]:
        assert run["branch"] == "main" or run["branch"].startswith(("feature/synth-", "fix/synth-"))
        assert run["repo"] in ("demo-app", "demo-lib", "demo-web")
        assert len(run["commit_sha"]) == 40 and run["commit_sha"].isdigit()
        assert int(run["ci_run_id"]) >= 1000000000
        assert run["started_at"].startswith("20")


def test_ledger_has_no_local_paths(repo_root):
    """台账里不得出现本机绝对路径（AGENTS.md 入库纪律）。"""
    path = os.path.join(repo_root, "data", "synth", "expect.json")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert ":\\" not in text and ":/" not in text, "台账出现 Windows 盘符路径"
    assert "/home/" not in text and "/Users/" not in text
    assert repo_root not in text, "台账出现仓库绝对路径"


def test_big_xml_is_iterparse_friendly(gen_runs, tmp_path):
    """D6 大文件语料：多 suite、可被逐元素解析、计数等于请求数。"""
    target = tmp_path / "big.xml"
    written = gen_runs.write_big_xml(str(target), 300, suites=6)
    assert written == 300
    import xml.etree.ElementTree as ET

    root = ET.parse(str(target)).getroot()
    assert root.tag == "testsuites"
    assert len(root.findall("testsuite")) == 6
    assert sum(len(s.findall("testcase")) for s in root.findall("testsuite")) == 300
