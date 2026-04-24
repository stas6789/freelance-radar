"""Tests for SQLite storage layer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freelance_radar.storage import Storage  # noqa: E402


def test_dedup(tmp_path):
    s = Storage(tmp_path / "t.db")
    assert s.is_seen("@ch", 1) is False
    s.record("@ch", 1, category="bot", budget_rub=1000, forwarded=True)
    assert s.is_seen("@ch", 1) is True


def test_save_and_list_orders(tmp_path):
    s = Storage(tmp_path / "t.db")
    s.save_order(
        channel="@webjobs",
        message_id=1,
        link="https://t.me/webjobs/1",
        title="Нужен бот",
        raw_text="Нужен бот для записи клиентов. Бюджет 10000 руб.",
        category="bot",
        budget_rub=10_000,
        urgency=None,
        contact="@client1",
        confidence=0.9,
        cls_dict={"x": 1},
    )
    s.save_order(
        channel="@webjobs",
        message_id=2,
        link="https://t.me/webjobs/2",
        title="Сайт на Tilda",
        raw_text="Нужен сайт на Tilda. Бюджет 3000 руб.",
        category="website",
        budget_rub=3_000,
        urgency="urgent",
        contact=None,
        confidence=0.8,
        cls_dict={},
    )

    all_orders = s.list_orders()
    assert len(all_orders) == 2

    bots = s.list_orders(category="bot")
    assert len(bots) == 1
    assert bots[0]["category"] == "bot"

    high_budget = s.list_orders(min_budget=5_000)
    assert len(high_budget) == 1
    assert high_budget[0]["budget_rub"] == 10_000

    urgent = s.list_orders(urgent_only=True)
    assert len(urgent) == 1
    assert urgent[0]["urgency"] == "urgent"


def test_stats(tmp_path):
    s = Storage(tmp_path / "t.db")
    s.record("@ch", 1, "bot", 1000, forwarded=True)
    s.record("@ch", 2, "text", None, forwarded=False)
    s.save_order(
        channel="@ch",
        message_id=1,
        link="",
        title="",
        raw_text="",
        category="bot",
        budget_rub=1000,
        urgency=None,
        contact=None,
        confidence=0.5,
        cls_dict={},
    )
    st = s.stats()
    assert st["total_seen"] == 2
    assert st["forwarded"] == 1
    assert st["orders_stored"] == 1
