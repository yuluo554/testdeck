"""持久层：schema 幂等、唯一键防 NULL、外键级联、不可写路径给 DbError。"""

import os
import sqlite3

import pytest

from testdeck import db


def test_connect_creates_schema(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        counts = db.table_counts(conn)
        assert counts == {"runs": 0, "suites": 0, "cases": 0, "occurrences": 0}
        version = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert version == str(db.SCHEMA_VERSION)
    finally:
        conn.close()


def test_connect_is_idempotent(tmp_path):
    path = str(tmp_path / "t.db")
    for _ in range(3):
        conn = db.connect(path)
        conn.close()
    conn = db.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"runs", "suites", "cases", "occurrences", "meta"} <= tables
    finally:
        conn.close()


def test_foreign_keys_are_on(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_run_unique_key_is_enforced(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        sql = (
            "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
            "VALUES(?,?,?,?,?)"
        )
        conn.execute(sql, ("main", "0" * 40, "1", "a.xml", "2026-10-18T00:00:00"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("main", "0" * 40, "1", "b.xml", "2026-10-18T00:00:00"))
    finally:
        conn.close()


def test_unknown_value_must_be_empty_string_not_null(tmp_path):
    """唯一键列 NOT NULL：NULL 在唯一索引里彼此不等，会绕过幂等。"""
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
                "VALUES(?,?,?,?,?)",
                (None, "0" * 40, "1", "a.xml", "2026-10-18T00:00:00"),
            )
        # 空串合法且可重复命中唯一键
        conn.execute(
            "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
            "VALUES('', '', '', 'a.xml', '2026-10-18T00:00:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
                "VALUES('', '', '', 'b.xml', '2026-10-18T00:00:00')"
            )
    finally:
        conn.close()


def test_status_check_constraint(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        conn.execute(
            "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
            "VALUES('main','%s','1','a.xml','2026-10-18T00:00:00')" % ("0" * 40)
        )
        conn.execute("INSERT INTO cases(suite_name, classname, name) VALUES('s','c','t')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO occurrences(run_id, case_id, status) VALUES(1, 1, 'error')"
            )
    finally:
        conn.close()


def test_cascade_delete_removes_children(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    try:
        conn.execute(
            "INSERT INTO runs(branch, commit_sha, ci_run_id, source_path, ingested_at) "
            "VALUES('main','%s','1','a.xml','2026-10-18T00:00:00')" % ("0" * 40)
        )
        conn.execute("INSERT INTO cases(suite_name, classname, name) VALUES('s','c','t')")
        conn.execute(
            "INSERT INTO occurrences(run_id, case_id, status) VALUES(1, 1, 'pass')"
        )
        conn.execute("DELETE FROM runs WHERE run_id=1")
        assert conn.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0] == 0
    finally:
        conn.close()


def test_unwritable_path_raises_db_error(tmp_path):
    """把库路径指向一个**已存在的文件**的下一层 -> 目录无法创建 -> DbError（退出码 3）。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    target = os.path.join(str(blocker), "sub", "t.db")
    with pytest.raises(db.DbError):
        db.connect(target)
