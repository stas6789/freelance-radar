"""SQLite dedup + audit log for freelance-radar."""

from __future__ import annotations

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
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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

    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM seen_messages").fetchone()[0]
            forwarded = c.execute(
                "SELECT COUNT(*) FROM seen_messages WHERE forwarded=1"
            ).fetchone()[0]
        return {"total_seen": total, "forwarded": forwarded}
