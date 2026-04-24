"""Public t.me/s/<channel> scraper — no Telegram API required.

Telegram exposes every public channel at https://t.me/s/<username> as plain
HTML. Posts live inside <div class="tgme_widget_message" data-post="name/id">
with the text inside a <div class="tgme_widget_message_text"> descendant.

This module fetches the page and yields `ScrapedPost` objects.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup


log = logging.getLogger(__name__)


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class ScrapedPost:
    channel: str         # @username
    message_id: int
    text: str
    link: str            # https://t.me/<channel>/<id>
    posted_at: datetime | None


def _channel_slug(channel: str) -> str:
    return channel.lstrip("@").strip()


def _build_url(channel: str) -> str:
    return f"https://t.me/s/{_channel_slug(channel)}"


def fetch_channel_html(
    channel: str,
    client: httpx.Client | None = None,
    timeout: float = 15.0,
) -> str:
    url = _build_url(channel)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"}
    if client is None:
        with httpx.Client(timeout=timeout, headers=headers) as c:
            r = c.get(url, follow_redirects=True)
    else:
        r = client.get(url, headers=headers, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse_posts(html: str, channel: str) -> list[ScrapedPost]:
    """Extract posts from a t.me/s/<channel> HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    slug = _channel_slug(channel).lower()

    posts: list[ScrapedPost] = []
    for div in soup.select("div.tgme_widget_message"):
        data_post = div.get("data-post") or ""
        # data-post looks like "channelname/12345"
        m = re.match(r"^([^/]+)/(\d+)$", data_post)
        if not m:
            continue
        post_channel, post_id = m.group(1), int(m.group(2))
        if post_channel.lower() != slug:
            continue

        text_el = div.select_one(".tgme_widget_message_text")
        text = _extract_text(text_el) if text_el else ""

        time_el = div.select_one("time")
        posted_at = _parse_iso(time_el.get("datetime")) if time_el else None

        posts.append(
            ScrapedPost(
                channel="@" + slug,
                message_id=post_id,
                text=text,
                link=f"https://t.me/{slug}/{post_id}",
                posted_at=posted_at,
            )
        )

    return posts


def _extract_text(el) -> str:
    # Preserve line breaks from <br> elements.
    for br in el.find_all("br"):
        br.replace_with("\n")
    return el.get_text(separator="", strip=False).strip()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def fetch_and_parse(channel: str, client: httpx.Client | None = None) -> list[ScrapedPost]:
    try:
        html = fetch_channel_html(channel, client=client)
    except httpx.HTTPError as e:
        log.warning("fetch failed for %s: %s", channel, e)
        return []
    return parse_posts(html, channel)
