"""Format and send filtered orders to the user's Telegram chat."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telethon import TelegramClient

from .classifier import Classification


log = logging.getLogger(__name__)


_CATEGORY_EMOJI = {
    "bot": "🤖",
    "parser": "🕸",
    "automation": "⚙️",
    "website": "🌐",
    "text": "✍️",
    "design": "🎨",
    "other": "📌",
}

_CATEGORY_LABEL = {
    "bot": "BOT",
    "parser": "PARSER",
    "automation": "АВТОМАТИЗАЦИЯ",
    "website": "САЙТ",
    "text": "ТЕКСТ",
    "design": "ДИЗАЙН",
    "other": "ДРУГОЕ",
}


@dataclass
class Notification:
    source_channel: str
    message_id: int
    raw_text: str
    link: str
    cls: Classification


def format_notification(n: Notification) -> str:
    cls = n.cls
    emoji = _CATEGORY_EMOJI.get(cls.category, "📌")
    label = _CATEGORY_LABEL.get(cls.category, cls.category.upper())

    budget = (
        f"💰 {cls.budget_rub:,}₽".replace(",", " ")
        if cls.budget_rub
        else "💰 бюджет не указан"
    )
    urgency = "⏱ СРОЧНО\n" if cls.urgency == "urgent" else ""

    title = cls.title or n.raw_text.strip().splitlines()[0][:120]

    # Preview of the body (up to ~600 chars) so user can decide without opening.
    body = n.raw_text.strip()
    if len(body) > 600:
        body = body[:600].rstrip() + "…"

    contact_line = f"\n💬 контакт: {cls.contact}" if cls.contact else ""

    return (
        f"{emoji} {label}\n"
        f"{budget}\n"
        f"{urgency}"
        f"\n<b>{_escape(title)}</b>\n"
        f"\n{_escape(body)}\n"
        f"\n🔗 <a href=\"{n.link}\">{_escape(n.source_channel)}</a>"
        f"{_escape(contact_line)}"
    )


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send(client: TelegramClient, target: str | int, n: Notification) -> None:
    text = format_notification(n)
    try:
        await client.send_message(
            entity=_resolve_target(target),
            message=text,
            parse_mode="html",
            link_preview=False,
        )
        log.info("forwarded %s/%s → %s", n.source_channel, n.message_id, target)
    except Exception as e:
        log.exception("failed to send notification: %s", e)


def _resolve_target(target: str | int) -> str | int:
    if isinstance(target, int):
        return target
    t = str(target).strip()
    if t.lower() == "me":
        return "me"
    if t.lstrip("-").isdigit():
        return int(t)
    return t  # @username
