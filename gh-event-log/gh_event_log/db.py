from __future__ import annotations

import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    ts           TEXT NOT NULL,
    observed_at  TEXT NOT NULL,
    repo         TEXT,
    number       INTEGER,
    pr_title     TEXT,
    kind         TEXT NOT NULL,
    actor        TEXT,
    body         TEXT,
    url          TEXT,
    my_relation  TEXT,
    source       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_pr ON events(repo, number);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);

CREATE TABLE IF NOT EXISTS prs (
    repo                TEXT NOT NULL,
    number              INTEGER NOT NULL,
    title               TEXT,
    url                 TEXT,
    state               TEXT,
    is_draft            INTEGER,
    author              TEXT,
    created_at          TEXT,
    updated_at          TEXT,
    merged_at           TEXT,
    closed_at           TEXT,
    head_ref            TEXT,
    base_ref            TEXT,
    head_sha            TEXT,
    head_committed_at   TEXT,
    review_decision     TEXT,
    mergeable           TEXT,
    requested_reviewers TEXT,
    latest_reviews      TEXT,
    ci_state            TEXT,
    ci_checks           TEXT,
    relation            TEXT,
    relations           TEXT,
    notif_reasons       TEXT,
    last_fetched_at     TEXT,
    PRIMARY KEY (repo, number)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

PR_JSON_COLS = ("requested_reviewers", "latest_reviews", "ci_checks")


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


def connect_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


def set_meta(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def insert_events(conn, events: list) -> int:
    events = sorted(events, key=lambda e: (e["ts"] or "", e["id"]))
    cur = conn.cursor()
    added = 0
    for e in events:
        if cur.execute("SELECT 1 FROM events WHERE id=?", (e["id"],)).fetchone():
            continue
        cur.execute(
            "INSERT OR IGNORE INTO events(id, ts, observed_at, repo, number, pr_title, kind, actor,"
            " body, url, my_relation, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                e["id"], e["ts"], e["observed_at"], e.get("repo"), e.get("number"),
                e.get("pr_title"), e["kind"], e.get("actor"), e.get("body"), e.get("url"),
                e.get("my_relation"), e["source"],
            ),
        )
        added += cur.rowcount
    return added


def get_pr(conn, repo: str, number: int):
    return conn.execute("SELECT * FROM prs WHERE repo=? AND number=?", (repo, number)).fetchone()


def upsert_pr(conn, pr: dict) -> None:
    row = dict(pr)
    for c in PR_JSON_COLS:
        if c in row and not isinstance(row[c], str) and row[c] is not None:
            row[c] = json.dumps(row[c])
    cols = list(row)
    conn.execute(
        f"INSERT INTO prs({','.join(cols)}) VALUES({','.join('?' for _ in cols)}) "
        f"ON CONFLICT(repo, number) DO UPDATE SET "
        + ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("repo", "number")),
        [row[c] for c in cols],
    )


def pr_row_to_dict(row) -> dict:
    d = dict(row)
    for c in PR_JSON_COLS:
        if d.get(c):
            d[c] = json.loads(d[c])
    for c in ("relations", "notif_reasons"):
        d[c] = [x for x in (d.get(c) or "").split(",") if x]
    d["is_draft"] = bool(d.get("is_draft"))
    return d
