"""SQLite dedup + audit log + dashboard queries for freelance-radar."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_messages (
    channel      TEXT    NOT NULL,
    message_id   INTEGER NOT NULL,
    seen_at      INTEGER NOT NULL,
    category     TEXT,
    budget_rub   INTEGER,
    forwarded    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (channel, message_id)
);

CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_messages(seen_at);

CREATE TABLE IF NOT EXISTS orders (
    channel      TEXT    NOT NULL,
    message_id   INTEGER NOT NULL,
    seen_at      INTEGER NOT NULL,
    link         TEXT,
    title        TEXT,
    raw_text     TEXT,
    category     TEXT,
    budget_rub   INTEGER,
    urgency      TEXT,
    contact      TEXT,
    confidence   REAL,
    cls_json     TEXT,
    PRIMARY KEY (channel, message_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_seen ON orders(seen_at DESC);
"""


class Storage:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._init()

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- dedup -----------------------------------------------------
    def is_seen(self, channel: str, message_id: int) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM seen_messages WHERE channel=? AND message_id=?",
                (channel, message_id),
            ).fetchone()
            return row is not None

    def record(
        self,
        channel: str,
        message_id: int,
        category: str | None,
        budget_rub: int | None,
        forwarded: bool,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO seen_messages
                    (channel, message_id, seen_at, category, budget_rub, forwarded)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    channel,
                    message_id,
                    int(time.time()),
                    category,
                    budget_rub,
                    1 if forwarded else 0,
                ),
            )

    # --- orders (used for the dashboard) ---------------------------
    def save_order(
        self,
        channel: str,
        message_id: int,
        link: str,
        title: str,
        raw_text: str,
        category: str,
        budget_rub: int | None,
        urgency: str | None,
        contact: str | None,
        confidence: float,
        cls_dict: dict,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO orders
                    (channel, message_id, seen_at, link, title, raw_text,
                     category, budget_rub, urgency, contact, confidence, cls_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel,
                    message_id,
                    int(time.time()),
                    link,
                    title,
                    raw_text,
                    category,
                    budget_rub,
                    urgency,
                    contact,
                    confidence,
                    json.dumps(cls_dict, ensure_ascii=False),
                ),
            )

    def list_orders(
        self,
        limit: int = 100,
        category: str | None = None,
        min_budget: int | None = None,
        urgent_only: bool = False,
    ) -> list[dict]:
        sql = "SELECT * FROM orders WHERE 1=1"
        params: list = []
        if category and category != "all":
            sql += " AND category = ?"
            params.append(category)
        if min_budget:
            sql += " AND budget_rub >= ?"
            params.append(min_budget)
        if urgent_only:
            sql += " AND urgency = 'urgent'"
        sql += " ORDER BY seen_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # --- stats -----------------------------------------------------
    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM seen_messages").fetchone()[0]
            forwarded = c.execute(
                "SELECT COUNT(*) FROM seen_messages WHERE forwarded=1"
            ).fetchone()[0]
            orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return {
            "total_seen": total,
            "forwarded": forwarded,
            "orders_stored": orders,
        }
