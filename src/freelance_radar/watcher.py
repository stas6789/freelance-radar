"""Telethon-based watcher that listens to freelance channels."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Callable

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Message

from .classifier import Classification
from .config import Config
from .notifier import Notification, send as send_notification
from .storage import Storage


log = logging.getLogger(__name__)


class Watcher:
    def __init__(
        self,
        cfg: Config,
        classifier: Callable[[str], Classification],
        storage: Storage,
    ):
        assert cfg.telethon is not None, "Watcher requires TelethonConfig"
        self.cfg = cfg
        self.tcfg = cfg.telethon
        self.classify = classifier
        self.storage = storage
        self.client = TelegramClient(
            self.tcfg.session_name, self.tcfg.api_id, self.tcfg.api_hash
        )

    async def start(self) -> None:
        log.info("starting Telethon client (phone=%s)", self.tcfg.phone)
        await self.client.start(phone=self.tcfg.phone)
        me = await self.client.get_me()
        log.info("authorized as @%s (id=%s)", me.username, me.id)

        entities = []
        for ch in self.cfg.channels:
            try:
                ent = await self.client.get_entity(ch)
                entities.append(ent)
                log.info("subscribed: %s (id=%s)", ch, getattr(ent, "id", "?"))
            except Exception as e:
                log.warning("cannot resolve channel %s: %s", ch, e)

        if not entities:
            raise RuntimeError("no channels could be resolved — aborting")

        @self.client.on(events.NewMessage(chats=entities))
        async def on_message(event: events.NewMessage.Event) -> None:
            await self._handle(event.message)

        log.info(
            "watching %d channel(s); categories=%s; min_budget=%d",
            len(entities),
            ",".join(self.cfg.categories),
            self.cfg.min_budget_rub,
        )
        await self.client.run_until_disconnected()

    async def _handle(self, msg: Message) -> None:
        text = (msg.message or "").strip()
        if not text or len(text) < 30:
            return

        channel_title = _channel_title(msg)
        channel_key = _channel_key(msg)
        if self.storage.is_seen(channel_key, msg.id):
            return

        try:
            cls = await asyncio.to_thread(self.classify, text)
        except Exception as e:
            log.exception("classifier error: %s", e)
            return

        forwarded = False
        if self._should_forward(cls):
            link = _message_link(msg, channel_title)
            self.storage.save_order(
                channel=channel_key,
                message_id=msg.id,
                link=link,
                title=cls.title or text[:120],
                raw_text=text,
                category=cls.category,
                budget_rub=cls.budget_rub,
                urgency=cls.urgency,
                contact=cls.contact,
                confidence=cls.confidence,
                cls_dict=asdict(cls),
            )
            note = Notification(
                source_channel=channel_title,
                message_id=msg.id,
                raw_text=text,
                link=link,
                cls=cls,
            )
            await send_notification(self.client, self.tcfg.notify_target, note)
            forwarded = True
        else:
            log.debug(
                "skip %s/%s (is_order=%s, cat=%s, budget=%s)",
                channel_key,
                msg.id,
                cls.is_order,
                cls.category,
                cls.budget_rub,
            )

        self.storage.record(
            channel=channel_key,
            message_id=msg.id,
            category=cls.category,
            budget_rub=cls.budget_rub,
            forwarded=forwarded,
        )

    def _should_forward(self, cls: Classification) -> bool:
        if not cls.is_order:
            return False
        if cls.category not in self.cfg.categories:
            return False
        if (
            self.cfg.min_budget_rub > 0
            and cls.budget_rub is not None
            and cls.budget_rub < self.cfg.min_budget_rub
        ):
            return False
        return True


def _channel_key(msg: Message) -> str:
    chat = msg.chat
    if isinstance(chat, Channel) and chat.username:
        return "@" + chat.username
    return str(getattr(chat, "id", "unknown"))


def _channel_title(msg: Message) -> str:
    chat = msg.chat
    if isinstance(chat, Channel) and chat.username:
        return "@" + chat.username
    return getattr(chat, "title", "unknown")


def _message_link(msg: Message, channel_title: str) -> str:
    if channel_title.startswith("@"):
        return f"https://t.me/{channel_title[1:]}/{msg.id}"
    chat = msg.chat
    if isinstance(chat, Channel) and chat.username:
        return f"https://t.me/{chat.username}/{msg.id}"
    return ""
