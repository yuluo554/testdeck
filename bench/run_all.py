#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基准统一入口：跑套件、汇总、给退出码。

**退出码三语义**（`plan/04-数据计划.md` §五 末段）：

| 码 | 含义 |
| --- | --- |
| 0 | 全部达标（所选套件都跑到且都过） |
| 1 | 有未达标，**或**有套件未就绪（`not_enabled`——不冒充通过） |
| 2 | 用法错误 / 未知名错误 |

**"未就绪"不等于"通过"**：M3 只实装了 `ingest`；`flaky`（M4）/ `slow`（M5）/
`export`（M5）依赖的生产模块尚未落地。它们被登记为 `not_enabled=true` + `notes`，
并且**计入退出码 1**——否则 `run_all` 会在"四套件只跑了一套"时报告成功，
那正是 plan/04 要禁掉的"数据缺失冒充通过"。

**M5 起四套件全部就绪**（`CURRENT_MILESTONE = 5`），`not_enabled` 不再出现；
未就绪这条判据仍由 `tests/test_bench_suites.py` 用 `monkeypatch` 把里程碑调回 0
来验证——"绿是装饰"的形态在测试里保留着。

想只跑部分套件：显式选择，如 `--suites ingest`。

用法：

    py -3.12 bench/run_all.py                    # 跑全部登记套件
    py -3.12 bench/run_all.py --suites ingest    # 只跑 ingest
    py -3.12 bench/run_all.py --no-perf-gate     # 性能只报告不判红
    py -3.12 bench/run_all.py --probe            # 探活：注入缺陷，断言判定能报出差异
    py -3.12 bench/run_all.py --list             # 列出套件与所属里程碑
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 当前里程碑。后面每完成一棒把它 +1，新套件就自动"就绪"。
#: M3 起调到 3；M4 调到 4（`flaky` 上线）；**M5 起调到 5**（`slow`/`export` 上线）——
#: 四套件全部就绪，不再有 `not_enabled`。
CURRENT_MILESTONE = 5

#: 登记的四套基准（plan/00 §四 提交材料实物表）
SUITES = (
    {"name": "ingest", "module": "bench_ingest", "since": 1,
     "note": "三框架产物逐项对账 + 大文件 iterparse 计时"},
    {"name": "flaky", "module": "bench_flaky", "since": 4,
     "note": "分型 / flaky_score 与参照实现逐值对账"},
    {"name": "slow", "module": "bench_slow", "since": 5,
     "note": "p50/p95 与回归判定对账"},
    {"name": "export", "module": "bench_export", "since": 5,
     "note": "md/json 字段一致 + --fail-on 退出码"},
)

#: 参照实现的 AST 守门目标
REFIMPL_PATH = os.path.join(HERE, "refimpl.py")
FORBIDDEN_ROOT = "testdeck"


# ── 参照实现独立性守门（AST）────────────────────────────────────────────


def no_production_import_problems(path):
    """AST 扫描：``path`` 是否 import 了生产包。返回问题清单（空 = 干净）。

    覆盖四种写法：``import testdeck.x`` / ``from testdeck import x`` /
    ``from testdeck.x import y`` / 相对导入。另外堵上明显的动态导入口子
    （``importlib.import_module("testdeck…")``）。

    **已知边界**：把模块名拆开拼串（``getattr(__import__("test" + "deck"))``）
    能绕过 AST。本守门不假装覆盖它——真正的兜底是"参照实现与生产实现分两个目录、
    且由人工评审 diff"，这里挡的是"顺手写个 import"这类真实失误。
    """
    problems = []
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FORBIDDEN_ROOT or alias.name.startswith(FORBIDDEN_ROOT + "."):
                    problems.append("第 %d 行：import %s" % (node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append("第 %d 行：相对导入（参照实现不得依赖包内结构）" % node.lineno)
            elif node.module and (node.module == FORBIDDEN_ROOT
                                  or node.module.startswith(FORBIDDEN_ROOT + ".")):
                imported = ", ".join(a.name for a in node.names)
                problems.append("第 %d 行：from %s import %s" % (node.lineno, node.module, imported))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and arg.value.startswith(FORBIDDEN_ROOT):
                        problems.append("第 %d 行：import_module(%r)" % (node.lineno, arg.value))
    return problems


def refimpl_guard_check(fault=None):
    """预检：`bench/refimpl.py` 不得 import `testdeck.*`。"""
    if fault == "inject_production_import":
        # 探活注入点：在**临时副本**上加一行违规导入，断言守门能报红。
        # 不动真文件——探活不能有副作用。
        import tempfile
        with open(REFIMPL_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        mutated = source + "\nfrom testdeck import model  # probe injection\n"
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "refimpl_mutated.py")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(mutated)
            problems = no_production_import_problems(target)
        return {
            "name": "precheck/refimpl_independence",
            "ok": bool(problems),
            "detail": ("注入违规 import 后守门报出：%s" % problems[0]) if problems
                      else "注入违规 import 后守门**没有**报出（守门失效）",
        }

    problems = no_production_import_problems(REFIMPL_PATH)
    return {
        "name": "precheck/refimpl_independence",
        "ok": not problems,
        "detail": ("；".join(problems) if problems
                   else "bench/refimpl.py 未 import testdeck.*"),
    }


# ── 套件装载 ───────────────────────────────────────────────────────────


def _load_suite_module(module_name):
    path = os.path.join(HERE, module_name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("testdeck_" + module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_suites(selected, perf_gate=True, fault=None):
    """跑所选套件，返回 ``(results, problems)``。"""
    results = []
    problems = []
    for entry in SUITES:
        if entry["name"] not in selected:
            continue
        if entry["since"] > CURRENT_MILESTONE:
            results.append({
                "suite": entry["name"],
                "enabled": False,
                "not_enabled": True,
                "ok": False,
                "checks": [],
                "notes": ["待 M%d 实装：%s" % (entry["since"], entry["note"])],
            })
            continue
        module = _load_suite_module(entry["module"])
        if module is None:
            results.append({
                "suite": entry["name"],
                "enabled": False,
                "not_enabled": True,
                "ok": False,
                "checks": [],
                "notes": ["套件脚本缺失：bench/%s.py" % entry["module"]],
            })
            continue
        kwargs = {"fault": fault}
        if entry["name"] == "ingest":
            kwargs["perf_gate"] = perf_gate
        try:
            result = module.run(**kwargs)
        except TypeError:
            # 套件不认识 fault 形参：去掉再试一次（新套件按需支持探活）
            kwargs.pop("fault", None)
            result = module.run(**kwargs)
        result.setdefault("not_enabled", False)
        results.append(result)
    return results, problems


def _print(results, prechecks):
    print("== bench/run_all.py（当前里程碑 M%d）==" % CURRENT_MILESTONE)
    for check in prechecks:
        print("%s  %-38s %s" % ("PASS" if check["ok"] else "FAIL", check["name"], check["detail"]))
    for result in results:
        if result.get("not_enabled"):
            print("NOT_ENABLED  suite %-6s %s" % (result["suite"], result["notes"][0]))
            continue
        for check in result["checks"]:
            print("%s  %-38s %s" % ("PASS" if check["ok"] else "FAIL", check["name"], check["detail"]))
        for note in result["notes"]:
            print("NOTE  %s" % note)

    ok = [r for r in results if not r.get("not_enabled") and r["ok"]]
    failed = [r for r in results if not r.get("not_enabled") and not r["ok"]]
    pending = [r for r in results if r.get("not_enabled")]
    total_checks = sum(len(r["checks"]) for r in results) + len(prechecks)
    print("=" * 64)
    print("汇总：达标套件 %d / 未达标套件 %d / 未就绪套件 %d（检查项 %d）"
          % (len(ok), len(failed), len(pending), total_checks))
    if pending:
        print("未就绪明细：%s" % "；".join("%s(%s)" % (r["suite"], r["notes"][0]) for r in pending))
    bad_prechecks = [c for c in prechecks if not c["ok"]]
    if failed or pending or bad_prechecks:
        print("结论：未全绿 → exit 1（未就绪不冒充通过）")
        return 1
    print("结论：全部达标 → exit 0")
    return 0


def _probe(selected, perf_gate):
    """探活：每条 check 都要能被注入的缺陷报出来。

    **每个已就绪且被选中的套件**都跑自己的 `_probe`（M4 起含 `flaky`）——
    只探 `ingest` 会让新套件的探活"看起来跑过"。套件没实现 `_probe` 时跳过
    （不冒充"探过"）。
    """
    print("== 探活（--probe）==")
    problems = []
    for check in (refimpl_guard_check(fault="inject_production_import"),):
        if check["ok"]:
            print("PASS  %-38s %s" % (check["name"], check["detail"]))
        else:
            print("FAIL  %-38s %s" % (check["name"], check["detail"]))
            problems.append(check["name"])

    for entry in SUITES:
        if entry["name"] not in selected or entry["since"] > CURRENT_MILESTONE:
            continue
        module = _load_suite_module(entry["module"])
        if module is None or not hasattr(module, "_probe"):
            continue
        if entry["name"] == "ingest":
            args = argparse.Namespace(perf_gate=perf_gate, big_cases=50000, big_file=None)
        elif entry["name"] == "export":
            # `bench_export` 不读台账（导出面全是纯函数，见其模块 docstring）
            args = argparse.Namespace(perf_gate=perf_gate)
        else:
            args = argparse.Namespace(perf_gate=perf_gate, ledger=None)
        rc = module._probe(args)
        if rc != 0:
            problems.append("%s 探活" % entry["name"])
    print("=" * 64)
    print("探活结论：%s" % ("全部能被检出" if not problems else "未检出：%s" % ",".join(problems)))
    return 0 if not problems else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="run_all", description="基准统一入口")
    parser.add_argument("--suites", default=None,
                        help="逗号分隔的套件名（默认全部登记套件）")
    parser.add_argument("--no-perf-gate", dest="perf_gate", action="store_false", default=True)
    parser.add_argument("--probe", action="store_true", help="探活：注入缺陷并断言能被报出")
    parser.add_argument("--list", action="store_true", help="列出套件与所属里程碑")
    parser.add_argument("--skip-prechecks", action="store_true",
                        help="跳过参照实现独立性预检（不建议）")
    args = parser.parse_args(argv)

    known = {entry["name"] for entry in SUITES}
    if args.list:
        for entry in SUITES:
            state = "就绪" if entry["since"] <= CURRENT_MILESTONE else "待 M%d" % entry["since"]
            print("%-8s %-8s %s" % (entry["name"], state, entry["note"]))
        return 0

    if args.suites is None:
        selected = known
    else:
        selected = {name.strip() for name in args.suites.split(",") if name.strip()}
        unknown = selected - known
        if unknown:
            print("用法错误：未知套件 %s（可选：%s）"
                  % (sorted(unknown), ", ".join(sorted(known))), file=sys.stderr)
            return 2
        if not selected:
            print("用法错误：--suites 不能为空", file=sys.stderr)
            return 2

    if args.probe:
        return _probe(selected, args.perf_gate)

    prechecks = [] if args.skip_prechecks else [refimpl_guard_check()]
    results, _ = run_suites(selected, perf_gate=args.perf_gate)
    return _print(results, prechecks)


if __name__ == "__main__":
    sys.exit(main())
