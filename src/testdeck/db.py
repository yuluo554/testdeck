"""SQLite schema 与连接（M0：只落 DDL 与建库；ingest 在 M2 实装）。

三条持久层纪律（写进 DDL，不靠约定）：
  1. **唯一键列全部 NOT NULL**；未知值写**有值空串**而不是 NULL
     （NULL 在唯一索引里彼此不等，会绕过 upsert 的幂等）。
  2. 外键 ``ON DELETE CASCADE`` + ``PRAGMA foreign_keys = ON``（每次连接都开）。
  3. 时间列只存 ISO 字符串；``ingested_at`` 是元数据，**不进入任何导出或 diff**。
"""

from __future__ import annotations

import os
import sqlite3

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id      INTEGER PRIMARY KEY,
  branch      TEXT NOT NULL,
  commit_sha  TEXT NOT NULL,
  ci_run_id   TEXT NOT NULL,
  started_at  TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL,
  framework   TEXT NOT NULL DEFAULT 'unknown',
  ingested_at TEXT NOT NULL,
  UNIQUE (branch, commit_sha, ci_run_id)
);

CREATE TABLE IF NOT EXISTS suites (
  suite_id    INTEGER PRIMARY KEY,
  run_id      INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  tests       INTEGER NOT NULL DEFAULT 0,
  failures    INTEGER NOT NULL DEFAULT 0,
  errors      INTEGER NOT NULL DEFAULT 0,
  skipped     INTEGER NOT NULL DEFAULT 0,
  time_ms     INTEGER NOT NULL DEFAULT 0,
  source_path TEXT NOT NULL DEFAULT '',
  UNIQUE (run_id, name, source_path)
);

CREATE TABLE IF NOT EXISTS cases (
  case_id    INTEGER PRIMARY KEY,
  suite_name TEXT NOT NULL,
  classname  TEXT NOT NULL,
  name       TEXT NOT NULL,
  UNIQUE (suite_name, classname, name)
);

CREATE TABLE IF NOT EXISTS occurrences (
  run_id           INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  case_id          INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  status           TEXT NOT NULL CHECK (status IN ('pass','fail','skip','missing')),
  time_ms          INTEGER,
  failure_message  TEXT NOT NULL DEFAULT '',
  failure_type     TEXT NOT NULL DEFAULT '',
  stack_first_line TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_occurrences_case ON occurrences(case_id);
CREATE INDEX IF NOT EXISTS idx_suites_run ON suites(run_id);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class DbError(RuntimeError):
    """库不可读 / 不可写（对应退出码 3）。"""


def connect(db_path):
    """打开连接并确保 schema。目录不存在时创建（父目录可写才可能成功）。"""
    directory = os.path.dirname(os.path.abspath(db_path))
    try:
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(db_path)
    except (OSError, sqlite3.Error) as exc:
        raise DbError("无法打开数据库 %s：%s" % (db_path, exc))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.close()
        raise DbError("初始化数据库失败 %s：%s" % (db_path, exc))
    return conn


def table_counts(conn):
    """四表行数（selftest / 幂等测试用；空库返回全 0，不是报错）。"""
    counts = {}
    for table in ("runs", "suites", "cases", "occurrences"):
        counts[table] = conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    return counts
