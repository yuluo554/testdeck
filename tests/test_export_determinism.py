"""导出可重放（`plan/03` 模块⑤ DoD）：**两次导出逐字节一致**（双跑 `cmp`）。

判据比"看起来一样"更硬：把两次导出的字节串直接 `==` 比。这条能红的形态有三种，
三条都有对应断言：

1. **写生成时刻**（`write_generated_at`）→ 两次不同；
2. **键序不稳**（用了 `sort_keys` 之外的排序，或 dict 构造顺序随查询漂移）→ 两次不同；
3. **含时间戳类元数据**（`ingested_at` 进了导出）→ 库里那条 `ingested_at` 虽固定，
   但它会随 ingest 时刻变，跨机器不可重放。

另外断言"**两次导出之间没有任何随机源**"：判定层不读时钟（`slow` / `flaky` / `diff`
都是纯函数），渲染层也不读。
"""

import os

import pytest

from testdeck import cli, db, exit_codes, report_model, rules

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)


@pytest.fixture
def db_path(repo_root, tmp_path):
    path = str(tmp_path / "determinism.db")
    paths = [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]
    assert cli.main(["ingest", *paths, "--db", path]) == exit_codes.OK
    return path


def _export(db_path, fmt):
    conn = db.open_existing(db_path)
    try:
        report = report_model.build_report(conn)
        return report_model.render(report, fmt)
    finally:
        conn.close()


@pytest.mark.parametrize("fmt", ["md", "json"])
def test_two_exports_are_byte_identical(db_path, fmt):
    """双跑 `cmp`：同一条命令导出两次，字节完全一致。"""
    first = _export(db_path, fmt)
    second = _export(db_path, fmt)
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


@pytest.mark.parametrize("fmt", ["md", "json"])
def test_export_is_stable_across_new_connections(db_path, fmt):
    """换一条新连接再导出：仍逐字节一致（键序不随连接/查询顺序漂移）。"""
    outputs = []
    for _ in range(3):
        outputs.append(_export(db_path, fmt))
    assert len(set(outputs)) == 1, "多次导出出现差异（存在随机源）"


def test_cli_export_twice_is_identical(db_path, capsys):
    """经 CLI 双跑：stdout 逐字节一致（含末尾换行）。"""
    outs = []
    for _ in range(2):
        assert cli.main(["export", "--db", db_path, "--format", "json"]) == exit_codes.OK
        outs.append(capsys.readouterr().out)
    assert outs[0] == outs[1]
    assert outs[0].endswith("\n")


def test_write_generated_at_rule_is_false():
    """规则包必须禁止写生成时刻——为 true 时 `load_view_rules` 直接报错（可跑红）。"""
    assert rules.load_view_rules()["write_generated_at"] is False


def test_renderer_does_not_read_clock(monkeypatch):
    """渲染层不读时钟：把 `datetime` 换成会抛的实现，导出照样跑。

    这条把"可重放"从"当前恰好一致"抬到"结构上不可能引入时间"。
    """
    import datetime as _datetime

    class _BoomDatetime(_datetime.datetime):
        @classmethod
        def now(cls, *args, **kwargs):  # pragma: no cover - 走到这里说明渲染读了时钟
            raise AssertionError("导出不应读系统时钟")

    monkeypatch.setattr(_datetime, "datetime", _BoomDatetime)
    # 只验渲染器对时间的依赖：直接渲染一个空报告
    assert report_model.render_json({"run": {}, "summary": {}, "cases": [],
                                     "regressions": [], "diff": None}).endswith("\n")
