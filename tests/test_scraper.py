"""Tests for the t.me/s/<channel> HTML parser (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freelance_radar.web_scraper import parse_posts  # noqa: E402


FIXTURE = """
<html><body>
<div class="tgme_widget_message" data-post="webjobs/1001">
  <div class="tgme_widget_message_text">
    Ищу Python-разработчика для Telegram-бота.<br>
    Бюджет 15 000 руб. Срочно! Писать @ivan_client
  </div>
  <time datetime="2026-04-23T12:00:00+00:00"></time>
</div>
<div class="tgme_widget_message" data-post="webjobs/1002">
  <div class="tgme_widget_message_text">
    Нужен копирайтер для описания товаров. Оплата 50₽ за 1000 знаков.
  </div>
  <time datetime="2026-04-23T12:30:00+00:00"></time>
</div>
<!-- a foreign post from a different channel should be ignored -->
<div class="tgme_widget_message" data-post="othername/42">
  <div class="tgme_widget_message_text">this should be skipped</div>
</div>
<!-- malformed, no text div -->
<div class="tgme_widget_message" data-post="webjobs/1003"></div>
</body></html>
"""


def test_parse_filters_to_requested_channel():
    posts = parse_posts(FIXTURE, "@webjobs")
    assert len(posts) == 3  # 1001, 1002, 1003 (1003 has empty text)
    ids = [p.message_id for p in posts]
    assert ids == [1001, 1002, 1003]


def test_extracts_text_with_linebreaks():
    posts = parse_posts(FIXTURE, "@webjobs")
    first = posts[0]
    assert "Python-разработчика" in first.text
    assert "Бюджет 15 000 руб" in first.text
    assert "@ivan_client" in first.text
    assert "\n" in first.text  # <br> preserved


def test_builds_correct_link():
    posts = parse_posts(FIXTURE, "@webjobs")
    assert posts[0].link == "https://t.me/webjobs/1001"
    assert posts[0].channel == "@webjobs"


def test_parses_timestamp():
    posts = parse_posts(FIXTURE, "@webjobs")
    assert posts[0].posted_at is not None
    assert posts[0].posted_at.year == 2026


def test_malformed_post_yields_empty_text():
    posts = parse_posts(FIXTURE, "@webjobs")
    malformed = next(p for p in posts if p.message_id == 1003)
    assert malformed.text == ""


def test_channel_matching_is_case_insensitive():
    posts = parse_posts(FIXTURE, "@WebJobs")
    assert len(posts) == 3


def test_empty_html():
    assert parse_posts("", "@anything") == []
