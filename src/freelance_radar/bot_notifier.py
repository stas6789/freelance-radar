"""Telegram Bot API notifier via HTTP — no Telethon, no api_id.

Only needs a bot token from @BotFather and a chat_id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

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

    body = n.raw_text.strip()
    if len(body) > 600:
        body = body[:600].rstrip() + "…"

    contact_line = f"\n💬 контакт: {_esc(cls.contact)}" if cls.contact else ""

    return (
        f"{emoji} {label}\n"
        f"{budget}\n"
        f"{urgency}"
        f"\n<b>{_esc(title)}</b>\n"
        f"\n{_esc(body)}\n"
        f"\n🔗 <a href=\"{n.link}\">{_esc(n.source_channel)}</a>"
        f"{contact_line}"
    )


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _diagnose(description: str) -> str:
    """Map common Telegram error strings to actionable hints (RU)."""
    d = (description or "").lower()
    if "chat not found" in d:
        return (
            "CHAT_ID неверный ИЛИ ты не написал /start своему боту. "
            "Открой бота в Telegram и напиши ему любое сообщение."
        )
    if "bot was blocked" in d:
        return (
            "Ты заблокировал своего же бота. Разблокируй его в Telegram "
            "(открой диалог → меню → Разблокировать / Restart)."
        )
    if "chat_id is empty" in d or "chat_id" in d and "empty" in d:
        return "CHAT_ID пустой — проверь .env (переменная CHAT_ID)."
    if "bot can't initiate conversation" in d:
        return (
            "Бот не может писать первым. Напиши своему боту /start "
            "в Telegram."
        )
    if "parse" in d:
        return "Проблема с форматированием HTML — сообщи разработчику."
    return "См. описание выше."


class BotNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout: float = 15.0):
        self.token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            base_url=f"https://api.telegram.org/bot{bot_token}",
        )

    def send(self, note: Notification) -> bool:
        text = format_notification(note)
        try:
            r = self._client.post(
                "/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            # Parse response before raise_for_status so we can surface
            # Telegram's own "description" field — raise_for_status only
            # gives "400 Bad Request" without the actual reason.
            try:
                data = r.json()
            except ValueError:
                data = None
            if r.status_code >= 400:
                reason = (data or {}).get("description", r.text[:300])
                log.error(
                    "Telegram sendMessage %d: %s | %s",
                    r.status_code,
                    reason,
                    _diagnose(reason),
                )
                return False
            if not data or not data.get("ok"):
                log.warning("Bot API sendMessage failed: %s", data)
                return False
            log.info(
                "forwarded %s/%s via bot", note.source_channel, note.message_id
            )
            return True
        except httpx.HTTPError as e:
            log.exception("sendMessage HTTP error: %s", e)
            return False

    def whoami(self) -> dict | None:
        """Call getMe — used at startup to verify the token."""
        try:
            r = self._client.get("/getMe")
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                return None
            return data.get("result")
        except httpx.HTTPError:
            return None

    def close(self) -> None:
        self._client.close()
