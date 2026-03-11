"""
Database layer — SQLite via stdlib sqlite3.
Stores signals, weekly scores, alert history, and website hashes.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("database.db")

CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id          TEXT NOT NULL,
    firm_name        TEXT NOT NULL,
    signal_type      TEXT NOT NULL,
    title            TEXT NOT NULL,
    body             TEXT,
    url              TEXT,
    department       TEXT,
    department_score REAL,
    matched_keywords TEXT,
    location         TEXT,
    seniority        TEXT,
    source           TEXT,
    recruiter        TEXT,
    published_date   TEXT,
    signal_hash      TEXT UNIQUE,
    created_at       TEXT DEFAULT (datetime('now'))
);
"""

CREATE_WEEKLY_SCORES = """
CREATE TABLE IF NOT EXISTS weekly_scores (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start   TEXT NOT NULL,
    firm_id      TEXT NOT NULL,
    firm_name    TEXT NOT NULL,
    department   TEXT NOT NULL,
    location     TEXT,
    score        REAL,
    signal_count INTEGER,
    breakdown    TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);
"""

CREATE_ALERT_LOG = """
CREATE TABLE IF NOT EXISTS alert_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id    TEXT NOT NULL,
    department TEXT NOT NULL,
    score      REAL,
    sent_at    TEXT DEFAULT (datetime('now'))
);
"""

CREATE_WEBSITE_HASHES = """
CREATE TABLE IF NOT EXISTS website_hashes (
    firm_id    TEXT NOT NULL,
    url        TEXT NOT NULL,
    page_hash  TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (firm_id, url)
);
"""


class Database:
    def __init__(self, path: str = "me_legal_jobs.db"):
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"Database opened: {path}")

    def _init_schema(self):
        cur = self._conn.cursor()
        cur.executescript(
            CREATE_SIGNALS + CREATE_WEEKLY_SCORES + CREATE_ALERT_LOG + CREATE_WEBSITE_HASHES
        )
        self._conn.commit()

    # ── Signal storage ────────────────────────────────────────────────────

    def is_new_signal(self, signal: dict) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM signals WHERE signal_hash = ?", (signal["signal_hash"],)
        )
        return cur.fetchone() is None

    def save_signal(self, signal: dict):
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO signals
                  (firm_id, firm_name, signal_type, title, body, url,
                   department, department_score, matched_keywords,
                   location, seniority, source, recruiter,
                   published_date, signal_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    signal["firm_id"],
                    signal["firm_name"],
                    signal["signal_type"],
                    signal["title"],
                    signal.get("body", ""),
                    signal.get("url", ""),
                    signal.get("department", ""),
                    signal.get("department_score", 0.0),
                    json.dumps(signal.get("matched_keywords", [])),
                    signal.get("location", ""),
                    signal.get("seniority", ""),
                    signal.get("source", ""),
                    signal.get("recruiter", ""),
                    signal.get("published_date", datetime.now(timezone.utc).isoformat()),
                    signal["signal_hash"],
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_signals_this_week(self) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE created_at >= ? ORDER BY department_score DESC",
            (cutoff,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_signals(self, limit: int = 500) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

    def get_signals_for_firm(self, firm_id: str, days: int = 30) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE firm_id=? AND created_at>=? ORDER BY department_score DESC",
            (firm_id, cutoff),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Weekly scores ─────────────────────────────────────────────────────

    def save_weekly_score(
        self,
        firm_id: str,
        firm_name: str,
        department: str,
        location: str,
        score: float,
        signal_count: int,
        breakdown: dict,
    ):
        week_start = (datetime.now(timezone.utc) - timedelta(days=datetime.now().weekday())).date().isoformat()
        self._conn.execute(
            """
            INSERT INTO weekly_scores
              (week_start, firm_id, firm_name, department, location, score, signal_count, breakdown)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (week_start, firm_id, firm_name, department, location,
             score, signal_count, json.dumps(breakdown)),
        )
        self._conn.commit()

    # ── Alert dedup ───────────────────────────────────────────────────────

    def was_alert_sent(self, firm_id: str, department: str) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        cur = self._conn.execute(
            "SELECT 1 FROM alert_log WHERE firm_id=? AND department=? AND sent_at>=?",
            (firm_id, department, cutoff),
        )
        return cur.fetchone() is not None

    def mark_alert_sent(self, firm_id: str, department: str, score: float):
        self._conn.execute(
            "INSERT INTO alert_log (firm_id, department, score) VALUES (?,?,?)",
            (firm_id, department, score),
        )
        self._conn.commit()

    # ── Website hashes ────────────────────────────────────────────────────

    def get_website_hashes(self, firm_id: str) -> dict:
        cur = self._conn.execute(
            "SELECT url, page_hash FROM website_hashes WHERE firm_id=?", (firm_id,)
        )
        return {row["url"]: row["page_hash"] for row in cur.fetchall()}

    def save_website_hash(self, firm_id: str, url: str, page_hash: str):
        self._conn.execute(
            """
            INSERT INTO website_hashes (firm_id, url, page_hash)
            VALUES (?,?,?)
            ON CONFLICT(firm_id, url) DO UPDATE SET page_hash=excluded.page_hash, updated_at=datetime('now')
            """,
            (firm_id, url, page_hash),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()
        logger.info("Database closed")
