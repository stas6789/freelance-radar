"""Configuration loader for freelance-radar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


DEFAULT_CATEGORIES = ("bot", "parser", "automation", "website", "text", "design")


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


@dataclass
class Config:
    api_id: int
    api_hash: str
    phone: str
    notify_target: str

    categories: tuple[str, ...]
    min_budget_rub: int

    database_path: Path
    session_name: str
    log_level: str

    llm: LLMConfig
    channels: list[str] = field(default_factory=list)


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {key}")
    return value or ""


def _load_channels(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"channels file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("channels") or []
    result: list[str] = []
    for item in raw:
        name = str(item).strip()
        if not name:
            continue
        # Normalise: drop t.me/ prefix, keep leading @.
        name = name.replace("https://t.me/", "").replace("t.me/", "")
        if not name.startswith("@"):
            name = "@" + name
        result.append(name)
    return result


def load_config(
    env_path: str | Path = ".env",
    channels_path: str | Path = "channels.yaml",
) -> Config:
    load_dotenv(env_path)

    categories_raw = _env("CATEGORIES", ",".join(DEFAULT_CATEGORIES))
    categories = tuple(
        c.strip().lower() for c in categories_raw.split(",") if c.strip()
    )

    llm = LLMConfig(
        provider=_env("LLM_PROVIDER", "deepseek"),
        api_key=_env("LLM_API_KEY", ""),
        model=_env("LLM_MODEL", "deepseek-chat"),
        base_url=_env("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    )

    return Config(
        api_id=int(_env("TG_API_ID", required=True)),
        api_hash=_env("TG_API_HASH", required=True),
        phone=_env("TG_PHONE", required=True),
        notify_target=_env("TG_NOTIFY_TARGET", "me"),
        categories=categories,
        min_budget_rub=int(_env("MIN_BUDGET_RUB", "0")),
        database_path=Path(_env("DATABASE_PATH", "radar.db")),
        session_name=_env("SESSION_NAME", "radar"),
        log_level=_env("LOG_LEVEL", "INFO"),
        llm=llm,
        channels=_load_channels(Path(channels_path)),
    )
