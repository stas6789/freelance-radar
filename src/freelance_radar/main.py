"""CLI entry point for freelance-radar."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .classifier import classify_keyword, make_classifier
from .config import load_config
from .storage import Storage
from .watcher import Watcher


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

    watcher = Watcher(cfg, classifier, storage)
    asyncio.run(watcher.start())
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
    print(f"total seen : {s['total_seen']}")
    print(f"forwarded  : {s['forwarded']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="freelance-radar")
    p.add_argument("--env", default=".env", help="path to .env file")
    p.add_argument(
        "--channels", default="channels.yaml", help="path to channels.yaml"
    )

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="start the watcher").set_defaults(func=cmd_run)

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
