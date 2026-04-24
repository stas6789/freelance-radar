"""CLI entry point for freelance-radar."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .bot_notifier import BotNotifier
from .classifier import classify_keyword, make_classifier
from .config import MODE_TELETHON, MODE_WEB, load_config
from .storage import Storage


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(env_path=args.env, channels_path=args.channels)
    _setup_logging(cfg.log_level)

    storage = Storage(cfg.database_path)
    classifier = make_classifier(cfg.llm)

    if cfg.mode == MODE_WEB:
        from .web_watcher import WebWatcher

        assert cfg.web is not None
        notifier = BotNotifier(cfg.web.bot_token, cfg.web.chat_id)
        watcher = WebWatcher(cfg, classifier, storage, notifier)
        try:
            watcher.run()
        except KeyboardInterrupt:
            logging.getLogger(__name__).info("interrupted by user")
        finally:
            watcher.close()
        return 0

    if cfg.mode == MODE_TELETHON:
        from .watcher import Watcher

        watcher = Watcher(cfg, classifier, storage)
        asyncio.run(watcher.start())
        return 0

    raise RuntimeError(f"unknown mode: {cfg.mode}")


def cmd_dashboard(args: argparse.Namespace) -> int:
    cfg = load_config(env_path=args.env, channels_path=args.channels)
    _setup_logging(cfg.log_level)

    from .dashboard import run_dashboard

    storage = Storage(cfg.database_path)
    run_dashboard(cfg, storage)
    return 0


def cmd_test_classify(args: argparse.Namespace) -> int:
    _setup_logging("INFO")
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not text:
        print("provide text via --text or stdin", file=sys.stderr)
        return 2

    cls = classify_keyword(text)
    print("is_order  :", cls.is_order)
    print("category  :", cls.category)
    print("title     :", cls.title)
    print("budget_rub:", cls.budget_rub)
    print("urgency   :", cls.urgency)
    print("contact   :", cls.contact)
    print("confidence:", cls.confidence)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = load_config(env_path=args.env, channels_path=args.channels)
    _setup_logging(cfg.log_level)
    s = Storage(cfg.database_path).stats()
    print(f"total seen    : {s['total_seen']}")
    print(f"forwarded     : {s['forwarded']}")
    print(f"orders stored : {s['orders_stored']}")
    return 0


def cmd_check_bot(args: argparse.Namespace) -> int:
    """Sanity-check BOT_TOKEN and CHAT_ID by sending a test message."""
    cfg = load_config(env_path=args.env, channels_path=args.channels)
    _setup_logging(cfg.log_level)
    if cfg.web is None:
        print("MODE must be 'web' for this check", file=sys.stderr)
        return 2

    notifier = BotNotifier(cfg.web.bot_token, cfg.web.chat_id)
    me = notifier.whoami()
    if me is None:
        print("getMe failed — BOT_TOKEN is invalid", file=sys.stderr)
        return 1
    print(f"bot OK: @{me.get('username')} ({me.get('first_name')})")

    from .bot_notifier import Notification
    from .classifier import Classification

    demo_cls = Classification(
        is_order=True,
        category="bot",
        title="Тестовое сообщение от freelance-radar",
        budget_rub=1234,
        urgency="urgent",
        contact="@demo",
        confidence=1.0,
    )
    ok = notifier.send(
        Notification(
            source_channel="@freelance-radar",
            message_id=0,
            raw_text="Если ты видишь это — бот работает и CHAT_ID корректный.",
            link="https://t.me/",
            cls=demo_cls,
        )
    )
    notifier.close()
    if not ok:
        print("sendMessage failed — check CHAT_ID", file=sys.stderr)
        return 1
    print("sendMessage OK — проверь Telegram")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="freelance-radar")
    p.add_argument("--env", default=".env", help="path to .env file")
    p.add_argument(
        "--channels", default="channels.yaml", help="path to channels.yaml"
    )

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="start the watcher (mode=web|telethon)").set_defaults(
        func=cmd_run
    )
    sub.add_parser(
        "dashboard", help="run the HTML dashboard at DASHBOARD_HOST:PORT"
    ).set_defaults(func=cmd_dashboard)
    sub.add_parser(
        "check-bot", help="verify BOT_TOKEN and CHAT_ID by sending a test message"
    ).set_defaults(func=cmd_check_bot)

    tc = sub.add_parser(
        "test-classify",
        help="classify a text via keyword fallback (no Telegram)",
    )
    tc.add_argument("--text", default=None)
    tc.set_defaults(func=cmd_test_classify)

    sub.add_parser("stats", help="print DB stats").set_defaults(func=cmd_stats)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
