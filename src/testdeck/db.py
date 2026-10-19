"""SQLite schema 与连接（M0 只落 DDL；M2 落四表 upsert）。

三条持久层纪律（写进 DDL，不靠约定）：
  1. **唯一键列全部 NOT NULL**；未知值写**有值空串**而不是 NULL
     （NULL 在唯一索引里彼此不等，会绕过 upsert 的幂等）。
  2. 外键 ``ON DELETE CASCADE`` + ``PRAGMA foreign_keys = ON``（每次连接都开）。
  3. 时间列只存 ISO 字符串；``ingested_at`` 是元数据，**不进入任何导出或 diff**。

**"缺失"与"0"要分开**（K24）：耗时列（`occurrences.time_ms` / `suites.time_ms`）
可空——XML 没写 `time` 时存 NULL，不存 0。计数字段没有这个问题：它们记的是
**元素重数**（文件里确实有几条），定义上总有值。

**SCHEMA_VERSION 2（M2）**：`suites.time_ms` 由 `NOT NULL DEFAULT 0` 改为可空
（同 `occurrences.time_ms` 的理由）。连接时若发现已存在的库版本不同，**直接报错
而不是静默复用**：旧库的 `NOT NULL` 约束会让"缺失耗时"写不进去，晚一点炸不如早说。
"""

from __future__ import annotations

import os
import sqlite3

SCHEMA_VERSION = 2

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
  time_ms     INTEGER,
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

#: 库口令（无时表示"表还没建过"）
_PENDING_VERSION_QUERY = "SELECT value FROM meta WHERE key='schema_version'"


class DbError(RuntimeError):
    """库不可读 / 不可写 / 版本不符（对应退出码 3）。"""


def _existing_version(conn):
    """已存在的库里登记的 schema 版本；没有 meta 表/没登记则 ``None``。"""
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if has_meta is None:
        return None
    row = conn.execute(_PENDING_VERSION_QUERY).fetchone()
    return None if row is None else row[0]


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
        existing = _existing_version(conn)
        if existing is not None and existing != str(SCHEMA_VERSION):
            raise DbError(
                "库 schema 版本不符：库是 %s，本版本要求 %s（删掉重建：%s）"
                % (existing, SCHEMA_VERSION, db_path)
            )
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    except DbError:
        conn.close()
        raise
    except sqlite3.Error as exc:
        conn.close()
        raise DbError("初始化数据库失败 %s：%s" % (db_path, exc))
    return conn


def open_existing(db_path):
    """以**只读意图**打开一个**已存在**的库（TUI / 导出用；不建目录、不建表、不写 meta）。

    "库不存在"对 `tui` / `export` 是**依赖缺失**（退出码 3），不是"空库 = 没有失败"
    （`plan/03` 模块⑤ 降级条）。所以这里与 `connect` 分开：`connect` 是 ingest 的
    "确保 schema"，`open_existing` 是读取方的"库得先在那儿"。
    """
    path = str(db_path)
    if not os.path.isfile(path):
        raise DbError(
            "库不存在：%s（先跑 `testdeck ingest <产物...>` 把 run 落库）" % path
        )
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error as exc:
        raise DbError("无法打开数据库 %s：%s" % (path, exc))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        existing = _existing_version(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise DbError("库不可读 %s：%s" % (path, exc))
    if existing is None:
        conn.close()
        raise DbError("库 %s 里没有 schema 登记（不是本工具建的库？）" % path)
    if existing != str(SCHEMA_VERSION):
        conn.close()
        raise DbError(
            "库 schema 版本不符：库是 %s，本版本要求 %s（删掉重建：%s）"
            % (existing, SCHEMA_VERSION, path)
        )
    return conn


def table_counts(conn):
    """四表行数（selftest / 幂等测试用；空库返回全 0，不是报错）。"""
    counts = {}
    for table in ("runs", "suites", "cases", "occurrences"):
        counts[table] = conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    return counts


# ── 四表 upsert（M2）───────────────────────────────────────────────────
#
# 全部 `INSERT ... ON CONFLICT DO UPDATE`：重复 ingest 同一份产物时**行数不变**，
# 只覆盖字段值（DoD：「重复 ingest 四表行数不变」）。
# 不用 `RETURNING`（需要 SQLite >= 3.35），改为 upsert 后 SELECT 拿主键——
# 本项目的 Python 下限是 3.9，不想把 sqlite3 的版本当成隐含依赖。


def upsert_run(conn, identity, started_at="", source_path="", framework="unknown",
               ingested_at=""):
    """按 `(branch, commit_sha, ci_run_id)` upsert 一条 run，返回 ``run_id``。"""
    conn.execute(
        "INSERT INTO runs(branch, commit_sha, ci_run_id, started_at, source_path, "
        "framework, ingested_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(branch, commit_sha, ci_run_id) DO UPDATE SET "
        "started_at = excluded.started_at, source_path = excluded.source_path, "
        "framework = excluded.framework, ingested_at = excluded.ingested_at",
        (identity.branch, identity.commit_sha, identity.ci_run_id, started_at,
         source_path, framework, ingested_at),
    )
    row = conn.execute(
        "SELECT run_id FROM runs WHERE branch=? AND commit_sha=? AND ci_run_id=?",
        identity.key,
    ).fetchone()
    return row[0]


def upsert_suite(conn, run_id, name, tests=0, failures=0, errors=0, skipped=0,
                 time_ms=None, source_path=""):
    """按 `(run_id, name, source_path)` upsert 一条 suite，返回 ``suite_id``。"""
    conn.execute(
        "INSERT INTO suites(run_id, name, tests, failures, errors, skipped, time_ms, "
        "source_path) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(run_id, name, source_path) DO UPDATE SET "
        "tests = excluded.tests, failures = excluded.failures, errors = excluded.errors, "
        "skipped = excluded.skipped, time_ms = excluded.time_ms",
        (run_id, name, tests, failures, errors, skipped, time_ms, source_path),
    )
    row = conn.execute(
        "SELECT suite_id FROM suites WHERE run_id=? AND name=? AND source_path=?",
        (run_id, name, source_path),
    ).fetchone()
    return row[0]


def upsert_case(conn, identity):
    """按 `(suite_name, classname, name)` upsert 一条用例身份，返回 ``case_id``。"""
    conn.execute(
        "INSERT INTO cases(suite_name, classname, name) VALUES(?,?,?) "
        "ON CONFLICT(suite_name, classname, name) DO NOTHING",
        identity.key,
    )
    row = conn.execute(
        "SELECT case_id FROM cases WHERE suite_name=? AND classname=? AND name=?",
        identity.key,
    ).fetchone()
    return row[0]


def upsert_occurrence(conn, run_id, case_id, status, time_ms=None,
                      failure_type="", failure_message="", stack_first_line=""):
    """按 `(run_id, case_id)` upsert 一条 occurrence（同 run 内覆盖，不新增行）。"""
    conn.execute(
        "INSERT INTO occurrences(run_id, case_id, status, time_ms, failure_type, "
        "failure_message, stack_first_line) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(run_id, case_id) DO UPDATE SET status = excluded.status, "
        "time_ms = excluded.time_ms, failure_type = excluded.failure_type, "
        "failure_message = excluded.failure_message, "
        "stack_first_line = excluded.stack_first_line",
        (run_id, case_id, status, time_ms, failure_type, failure_message,
         stack_first_line),
    )

