"""Configuration loader for freelance-radar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


DEFAULT_CATEGORIES = ("bot", "parser", "automation", "website", "text", "design")

MODE_WEB = "web"
MODE_TELETHON = "telethon"
VALID_MODES = (MODE_WEB, MODE_TELETHON)


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
class TelethonConfig:
    api_id: int
    api_hash: str
    phone: str
    notify_target: str
    session_name: str


@dataclass
class WebConfig:
    bot_token: str
    chat_id: str
    poll_seconds: int


@dataclass
class DashboardConfig:
    host: str
    port: int


@dataclass
class Config:
    mode: str
    categories: tuple[str, ...]
    min_budget_rub: int

    database_path: Path
    log_level: str

    llm: LLMConfig
    telethon: TelethonConfig | None
    web: WebConfig | None
    dashboard: DashboardConfig

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

    mode = _env("MODE", MODE_WEB).lower()
    if mode not in VALID_MODES:
        raise RuntimeError(
            f"Invalid MODE={mode!r}. Expected one of: {', '.join(VALID_MODES)}"
        )

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

    telethon_cfg: TelethonConfig | None = None
    if mode == MODE_TELETHON:
        telethon_cfg = TelethonConfig(
            api_id=int(_env("TG_API_ID", required=True)),
            api_hash=_env("TG_API_HASH", required=True),
            phone=_env("TG_PHONE", required=True),
            notify_target=_env("TG_NOTIFY_TARGET", "me"),
            session_name=_env("SESSION_NAME", "radar"),
        )

    web_cfg: WebConfig | None = None
    if mode == MODE_WEB:
        web_cfg = WebConfig(
            bot_token=_env("BOT_TOKEN", required=True),
            chat_id=_env("CHAT_ID", required=True),
            poll_seconds=max(60, int(_env("WEB_POLL_SECONDS", "120"))),
        )

    dashboard = DashboardConfig(
        host=_env("DASHBOARD_HOST", "127.0.0.1"),
        port=int(_env("DASHBOARD_PORT", "8080")),
    )

    return Config(
        mode=mode,
        categories=categories,
        min_budget_rub=int(_env("MIN_BUDGET_RUB", "0")),
        database_path=Path(_env("DATABASE_PATH", "radar.db")),
        log_level=_env("LOG_LEVEL", "INFO"),
        llm=llm,
        telethon=telethon_cfg,
        web=web_cfg,
        dashboard=dashboard,
        channels=_load_channels(Path(channels_path)),
    )
