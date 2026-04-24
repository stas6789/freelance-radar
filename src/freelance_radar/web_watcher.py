"""Polling-based watcher that uses the public t.me/s/<channel> pages."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Callable

import httpx

from .bot_notifier import BotNotifier, Notification
from .classifier import Classification
from .config import Config
from .storage import Storage
from .web_scraper import ScrapedPost, fetch_and_parse


log = logging.getLogger(__name__)


class WebWatcher:
    def __init__(
        self,
        cfg: Config,
        classifier: Callable[[str], Classification],
        storage: Storage,
        notifier: BotNotifier,
    ):
        assert cfg.web is not None, "WebWatcher requires WebConfig"
        self.cfg = cfg
        self.classify = classifier
        self.storage = storage
        self.notifier = notifier
        self._client = httpx.Client(timeout=15.0)

    def run(self) -> None:
        me = self.notifier.whoami()
        if me is None:
            raise RuntimeError(
                "Bot token seems invalid (getMe failed). "
                "Recreate the bot via @BotFather and update BOT_TOKEN."
            )
        log.info(
            "bot authorized as @%s (%s); watching %d channels every %ds",
            me.get("username"),
            me.get("first_name"),
            len(self.cfg.channels),
            self.cfg.web.poll_seconds,
        )

        # On first run, seed the dedup table with all current posts so we
        # don't dump the last ~20 historic posts per channel into the user's
        # chat at startup. Only post-startup messages should be forwarded.
        self._seed_existing()

        while True:
            started = time.time()
            try:
                self._poll_all()
            except Exception as e:
                log.exception("poll iteration failed: %s", e)
            elapsed = time.time() - started
            sleep_for = max(5.0, self.cfg.web.poll_seconds - elapsed)
            log.debug("sleeping %.1fs until next poll", sleep_for)
            time.sleep(sleep_for)

    def _seed_existing(self) -> None:
        """Initial pass: classify recent posts and populate the dashboard,
        but do NOT forward anything to the bot. This way the user sees data
        immediately on first run, while the chat with the bot stays clean
        and only receives genuinely new posts after startup.
        """
        log.info(
            "seeding: classifying recent posts (visible on dashboard, "
            "not sent to bot)"
        )
        total_seen = 0
        total_orders = 0
        for ch in self.cfg.channels:
            posts = fetch_and_parse(ch, client=self._client)
            for p in posts:
                if self.storage.is_seen(p.channel, p.message_id):
                    continue
                total_seen += 1
                if self._process(p, forward_to_bot=False):
                    total_orders += 1
            log.debug("seeded %s: %d posts", ch, len(posts))
        log.info(
            "seeding done: %d posts processed, %d saved to dashboard",
            total_seen,
            total_orders,
        )

    def _poll_all(self) -> None:
        total_new = 0
        forwarded = 0
        for ch in self.cfg.channels:
            posts = fetch_and_parse(ch, client=self._client)
            new = [p for p in posts if not self.storage.is_seen(p.channel, p.message_id)]
            total_new += len(new)
            for post in new:
                if self._process(post, forward_to_bot=True):
                    forwarded += 1
        if total_new:
            log.info("poll: %d new posts, %d forwarded", total_new, forwarded)

    def _process(self, post: ScrapedPost, forward_to_bot: bool = True) -> bool:
        text = (post.text or "").strip()
        if not text or len(text) < 30:
            self.storage.record(
                channel=post.channel,
                message_id=post.message_id,
                category=None,
                budget_rub=None,
                forwarded=False,
            )
            return False

        try:
            cls = self.classify(text)
        except Exception as e:
            log.exception("classifier error: %s", e)
            self.storage.record(
                channel=post.channel,
                message_id=post.message_id,
                category=None,
                budget_rub=None,
                forwarded=False,
            )
            return False

        passes_filter = self._should_forward(cls)

        if passes_filter:
            # Always save to dashboard, even during seeding.
            self.storage.save_order(
                channel=post.channel,
                message_id=post.message_id,
                link=post.link,
                title=cls.title or text[:120],
                raw_text=text,
                category=cls.category,
                budget_rub=cls.budget_rub,
                urgency=cls.urgency,
                contact=cls.contact,
                confidence=cls.confidence,
                cls_dict=asdict(cls),
            )
            sent = False
            if forward_to_bot:
                note = Notification(
                    source_channel=post.channel,
                    message_id=post.message_id,
                    raw_text=text,
                    link=post.link,
                    cls=cls,
                )
                sent = self.notifier.send(note)
            self.storage.record(
                channel=post.channel,
                message_id=post.message_id,
                category=cls.category,
                budget_rub=cls.budget_rub,
                forwarded=sent,
            )
            return True

        self.storage.record(
            channel=post.channel,
            message_id=post.message_id,
            category=cls.category,
            budget_rub=cls.budget_rub,
            forwarded=False,
        )
        return False

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

    def close(self) -> None:
        self._client.close()
        self.notifier.close()
