"""`ingest` 编排：四表落库、upsert 幂等、摘要格式、`--db` 回显、dry-run 零副作用。

设备件的用法统一为"真跑产物 + 临时库"，不碰用户的默认库（`XDG_DATA_HOME` 被改写）。
"""

import os
import re
import shutil
import sqlite3

import pytest

from testdeck import cli, db, exit_codes, ingest

FIXTURE_FILES = (
    os.path.join("bench", "fixtures", "pytest", "junit.xml"),
    os.path.join("bench", "fixtures", "gotestsum", "gotestsum.xml"),
    os.path.join("bench", "fixtures", "playwright", "playwright.xml"),
)

#: 三份真跑产物：6 + 5 + 7 = 18 条用例、3 个 suite、1 个"未标注 run"
EXPECTED_SUMMARY = ("ingest: files=3 runs=1 cases=18 occurrences=18 skipped=0 "
                    "framework=gotestsum,playwright,pytest")


def _fixture_paths(repo_root):
    return [os.path.join(repo_root, rel) for rel in FIXTURE_FILES]


def _counts(db_path):
    conn = db.connect(db_path)
    try:
        return db.table_counts(conn)
    finally:
        conn.close()


# ── 四表落库 + upsert 幂等（DoD）──────────────────────────────────────


def test_three_fixtures_fill_four_tables(repo_root, tmp_path):
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", *_fixture_paths(repo_root), "--db", db_path]) == exit_codes.OK
    conn = db.connect(db_path)
    try:
        assert db.table_counts(conn) == {"runs": 1, "suites": 3, "cases": 18,
                                        "occurrences": 18}
        run = dict(conn.execute("SELECT * FROM runs").fetchone())
        # 身份三元组来自 XML 声明值；三份产物都没声明 -> 空串（K1/K26）
        assert (run["branch"], run["commit_sha"], run["ci_run_id"]) == ("", "", "")
        assert run["framework"] == "gotestsum,playwright,pytest"
        assert run["source_path"] == "bench/fixtures/gotestsum/gotestsum.xml"
        assert run["started_at"]  # 来自 XML 的 timestamp，缺失才写空串
        suites = {row["name"]: dict(row) for row in conn.execute("SELECT * FROM suites")}
        assert set(suites) == {"pytest", "demo-lib", "todo.spec.js"}
        assert suites["pytest"]["tests"] == 6 and suites["pytest"]["failures"] == 1
        assert suites["pytest"]["time_ms"] == 105
        # 实测：Playwright 的 suite name 是**测试文件名**（不是 "playwright"）
        assert suites["todo.spec.js"]["skipped"] == 1
        assert suites["todo.spec.js"]["time_ms"] == 6616
        # occurrences 的状态/耗时/stack 首行都落了盘
        row = conn.execute(
            "SELECT o.* FROM occurrences o JOIN cases c ON c.case_id = o.case_id "
            "WHERE c.name = 'test_deliberate_failure_fixture'"
        ).fetchone()
        assert row["status"] == "fail"
        assert row["stack_first_line"] == "def test_deliberate_failure_fixture():"
        assert row["failure_message"].startswith("AssertionError")
    finally:
        conn.close()


def test_repeat_ingest_keeps_row_counts(repo_root, tmp_path):
    """DoD：重复 ingest 四表行数不变（upsert 生效，不产生重复 run/occurrence）。"""
    db_path = str(tmp_path / "store.db")
    paths = _fixture_paths(repo_root)
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    before = _counts(db_path)
    assert cli.main(["ingest", *paths, "--db", db_path]) == exit_codes.OK
    assert _counts(db_path) == before


def test_identity_declared_in_xml_splits_runs(repo_root, tmp_path):
    """XML 里声明了身份 -> 按三元组分组；两份不同身份 = 两个 run（K26）。"""
    good = _fixture_paths(repo_root)[0]
    first = tmp_path / "r1" / "junit.xml"
    second = tmp_path / "r2" / "junit.xml"
    for target, run_id in ((first, "1001"), (second, "1002")):
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(good, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace('<testsuite name="pytest"',
                            '<testsuite name="pytest" branch="main" commit="%s" '
                            'ci_run_id="%s"' % ("b" * 40, run_id), 1)
        target.write_text(text, encoding="utf-8")
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(first), str(second), "--db", db_path]) == exit_codes.OK
    conn = db.connect(db_path)
    try:
        runs = [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY run_id")]
        assert [r["ci_run_id"] for r in runs] == ["1001", "1002"]
        assert {r["branch"] for r in runs} == {"main"}
        assert db.table_counts(conn)["occurrences"] == 12  # 6 条用例 × 2 个 run
    finally:
        conn.close()


def test_parameterized_names_survive_to_db(tmp_path):
    xml = tmp_path / "junit-param.xml"
    xml.write_text(
        '<?xml version="1.0"?><testsuite name="s">'
        '<testcase classname="c" name="test_x[1-2]" time="1.5"/>'
        '<testcase classname="c" name="test_x[3-4]" time="2.5"/>'
        "</testsuite>", encoding="utf-8")
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(xml), "--db", db_path]) == exit_codes.OK
    conn = db.connect(db_path)
    try:
        names = [row[0] for row in conn.execute("SELECT name FROM cases ORDER BY name")]
        assert names == ["test_x[1-2]", "test_x[3-4]"]
        times = [row[0] for row in conn.execute("SELECT time_ms FROM occurrences ORDER BY time_ms")]
        assert times == [1500, 2500]
    finally:
        conn.close()


# ── 摘要（机读行 + 人读行）────────────────────────────────────────────


def test_summary_is_machine_readable_and_echoes_db(repo_root, tmp_path, capsys):
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", *_fixture_paths(repo_root), "--db", db_path]) == exit_codes.OK
    out = capsys.readouterr().out.splitlines()
    assert out[0] == EXPECTED_SUMMARY
    assert re.fullmatch(r"ingest: files=\d+ runs=\d+ cases=\d+ occurrences=\d+ "
                        r"skipped=\d+ framework=[a-z,]*", out[0])
    assert out[-1] == "db: %s" % db_path


def test_summary_reports_skipped_file_with_reason(repo_root, tmp_path, capsys):
    good = tmp_path / "good" / "junit.xml"
    good.parent.mkdir()
    shutil.copy(_fixture_paths(repo_root)[0], good)
    bad = tmp_path / "bad" / "junit-broken.xml"
    bad.parent.mkdir()
    bad.write_text('<?xml version="1.0"?><testsuites><testsuite><testcase ', encoding="utf-8")
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(tmp_path), "--db", db_path]) == exit_codes.OK
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("ingest: files=2 runs=1 cases=6 occurrences=6 skipped=1 ")
    # 坏文件不中断整批：好文件照样入库
    assert _counts(db_path) == {"runs": 1, "suites": 1, "cases": 6, "occurrences": 6}
    assert any(line.startswith("skipped: bad_xml=1 (") and "junit-broken.xml" in line
               for line in out), out


def test_all_three_skip_reasons_are_reported_in_one_batch(repo_root, tmp_path, capsys):
    """DoD「坏文件记 `skipped:<reason>`，三种各一条实测」的 CLI 级证据。"""
    root = tmp_path / "mixed"
    root.mkdir()
    shutil.copy(_fixture_paths(repo_root)[0], root / "junit-ok.xml")
    (root / "junit-struct.xml").write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="s"><testcase name="t"',
        encoding="utf-8")
    (root / "junit-enc.xml").write_bytes(
        b'<?xml version="1.0" encoding="utf-8"?><testsuite name="s">\xff\xfe</testsuite>')
    (root / "junit-foreign.xml").write_text(
        '<?xml version="1.0"?><report><case/></report>', encoding="utf-8")

    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(root), "--db", db_path]) == exit_codes.OK
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("ingest: files=4 runs=1 cases=6 occurrences=6 skipped=3 ")
    reasons = {line.split()[1].split("=")[0]: line for line in out if line.startswith("skipped: ")}
    assert set(reasons) == {"bad_encoding", "bad_xml", "no_testsuite"}
    assert "bad_xml=1" in reasons["bad_xml"] and "junit-struct.xml" in reasons["bad_xml"]
    assert "junit-enc.xml" in reasons["bad_encoding"]
    assert "junit-foreign.xml" in reasons["no_testsuite"]
    assert _counts(db_path)["cases"] == 6  # 好文件照样入库


def test_unknown_framework_is_reported_as_unknown(tmp_path, capsys):
    xml = tmp_path / "report.xml"
    xml.write_text('<?xml version="1.0"?><testsuite name="pkg">'
                   '<testcase classname="pkg" name="t"/></testsuite>', encoding="utf-8")
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(xml), "--db", db_path]) == exit_codes.OK
    assert "framework=unknown" in capsys.readouterr().out.splitlines()[0]


def test_directory_scan_honours_glob_option(repo_root, tmp_path, capsys):
    """默认 glob 是 `**/junit*.xml`（+ surefire/gradle 路径）；其他名字要显式给模式。"""
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", os.path.join(repo_root, "bench", "fixtures"),
                     "--glob", "**/*.xml", "--db", db_path]) == exit_codes.OK
    assert capsys.readouterr().out.splitlines()[0].startswith("ingest: files=3 ")
    assert _counts(db_path)["cases"] == 18


def test_zero_matches_is_not_an_error(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(empty), "--db", db_path]) == exit_codes.OK
    out = capsys.readouterr().out
    assert "files=0 runs=0 cases=0" in out and "未发现匹配的产物文件" in out


# ── dry-run 与失败路径：零副作用 ──────────────────────────────────────

_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", "build"}


def _snapshot(root):
    items = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            items[os.path.relpath(path, root)] = (stat.st_size, stat.st_mtime_ns)
    return items


def test_dry_run_leaves_repo_and_default_db_untouched(repo_root, tmp_path,
                                                      monkeypatch, capsys):
    """`--dry-run`：全仓快照差集为空 + 默认库路径上什么都没建出来。"""
    data_home = tmp_path / "datahome"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    before = _snapshot(repo_root)
    rc = cli.main(["ingest", os.path.join(repo_root, "bench", "fixtures"),
                   "--glob", "**/*.xml", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == exit_codes.OK
    assert out.splitlines()[0].startswith("ingest: files=3 runs=1 cases=18 ")
    assert "dry-run: 未写库（零副作用）" in out
    assert _snapshot(repo_root) == before
    assert not data_home.exists(), "dry-run 不该建默认库目录"


def test_missing_path_is_a_usage_error_and_writes_nothing(tmp_path):
    db_path = str(tmp_path / "store.db")
    assert cli.main(["ingest", str(tmp_path / "nope"), "--db", db_path]) == exit_codes.USAGE
    assert not os.path.exists(db_path)


def test_unwritable_db_path_is_dependency_error(repo_root, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    db_path = os.path.join(str(blocker), "sub", "store.db")
    assert cli.main(["ingest", _fixture_paths(repo_root)[0], "--db", db_path]) == \
        exit_codes.DEPENDENCY


def test_db_is_validated_even_when_nothing_parses(tmp_path):
    """库不可用是**依赖问题**，不该被"这一批恰好没解析出东西"掩盖。"""
    bad = tmp_path / "junit-bad.xml"
    bad.write_text('<?xml version="1.0"?><testsuites><testsuite><testcase ', encoding="utf-8")
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    db_path = os.path.join(str(blocker), "sub", "store.db")
    assert cli.main(["ingest", str(bad), "--db", db_path]) == exit_codes.DEPENDENCY


def test_old_schema_version_is_refused_not_silently_reused(repo_root, tmp_path):
    """旧版本库（schema 1）不得被静默复用：直接报错（退出码 3）。"""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                       "INSERT INTO meta(key, value) VALUES('schema_version','1');")
    conn.commit()
    conn.close()
    assert cli.main(["ingest", _fixture_paths(repo_root)[0], "--db", db_path]) == \
        exit_codes.DEPENDENCY


# ── discover（扫描面）──────────────────────────────────────────────────


def test_discover_is_sorted_and_deduplicated(repo_root, tmp_path):
    fixtures = os.path.join(repo_root, "bench", "fixtures")
    first = ingest.discover([fixtures, os.path.join(fixtures, "pytest", "junit.xml")],
                            globs=["**/*.xml"])
    entries, missing = first
    assert missing == []
    displays = [display for _abs, display in entries]
    assert displays == sorted(displays)
    assert len(displays) == len(set(displays)) == 3


def test_discover_reports_missing_paths():
    entries, missing = ingest.discover(["definitely/not/here.xml"])
    assert entries == [] and missing == ["definitely/not/here.xml"]


def test_summary_lines_reason_order_is_fixed():
    """摘要里原因码按单点顺序输出（不随发现顺序漂移）。"""
    report = ingest.IngestReport(files=2, skipped=2, frameworks=("unknown",))
    report.skipped_reasons = {"no_testsuite": ["b.xml"], "bad_xml": ["a.xml"]}
    lines = ingest.summary_lines(report)
    assert lines[1] == "skipped: bad_xml=1 (a.xml)"
    assert lines[2] == "skipped: no_testsuite=1 (b.xml)"


@pytest.mark.parametrize("reason", ["bad_time", "missing_name"])
def test_degraded_reasons_are_printed_once_per_reason(tmp_path, reason):
    report = ingest.IngestReport(files=1, frameworks=("unknown",))
    report.degraded_counts[reason] = 2
    report.degraded_paths[reason] = ["a.xml"]
    lines = ingest.summary_lines(report)
    assert "degraded: %s=2 (a.xml)" % reason in lines


def test_report_ok_tracks_exit_code():
    assert ingest.IngestReport(exit_code=exit_codes.OK).ok
    assert not ingest.IngestReport(exit_code=exit_codes.DEPENDENCY).ok
