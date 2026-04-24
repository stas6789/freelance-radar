"""Classify Telegram messages as freelance orders.

Two backends:
  - LLM-based (preferred if LLM_API_KEY is set): asks an LLM to return
    structured JSON.
  - Keyword-based (fallback): simple heuristics, works offline.

Both return a ``Classification`` dataclass so the rest of the code is agnostic
to the backend.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Any

import httpx

from .config import LLMConfig


log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------
CATEGORIES = (
    "bot",         # Telegram/Discord-боты, чат-боты
    "parser",      # парсинг сайтов, scraping
    "automation",  # скрипты, обработка данных, excel
    "website",     # лендинги, WordPress, Tilda, вёрстка
    "text",        # копирайт, переводы, SEO
    "design",      # логотипы, баннеры, презентации
    "other",       # всё остальное
)


@dataclass
class Classification:
    is_order: bool
    category: str           # one of CATEGORIES
    title: str              # one-line summary (max ~120 chars)
    budget_rub: int | None  # parsed rub budget if mentioned
    urgency: str | None     # "urgent" | "normal" | None
    contact: str | None     # @username or phone if mentioned
    confidence: float       # 0..1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------
# Keyword / regex fallback
# ------------------------------------------------------------------
_ORDER_HINTS = re.compile(
    r"(ищу|ищем|ищутся|нужен|нужна|нужно|нужны|требуется|требуются|"
    r"заказ|оплата|бюджет|оплач|готов\s+оплатить|"
    r"вакансия|вакансии|наймём|наем|в\s+команду|в\s+штат|"
    r"зарплата|зп|з/п|remote|удал[её]нк|фриланс)",
    re.IGNORECASE,
)

# Russian word boundaries: we allow suffix letters so "бот", "бота", "ботом"
# all match. Use \b only at the start of each stem.
_CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "bot",
        re.compile(
            r"(\bбот[а-я]{0,5}\b|\bботов\b|\bботам[и]?\b|"
            r"\bchatbot\b|\bchat-bot\b|\baiogram\b|"
            r"\btelegram\s*bot\b|\btg\s*bot\b|\bwhatsapp\s*bot\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "parser",
        re.compile(
            r"(\bпарсер[а-я]*\b|\bпарсинг[а-я]*\b|\bparser\b|"
            r"\bscraping\b|\bscrape[dr]?\b|"
            r"\bсобрать\s+данн[а-я]+|\bвыгрузить\s+с\s+сайт|"
            r"\bвыгрузк[а-я]*\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "website",
        re.compile(
            r"(\bсайт[а-я]*\b|\bлендинг[а-я]*\b|\blanding\b|"
            r"\bwordpress\b|\btilda\b|\bbitrix\b|"
            r"\bверстк[а-я]*\b|\bвёрстк[а-я]*\b|\bверстальщик[а-я]*\b|"
            r"\bhtml\b|\bcss\b|\breact\b|\bvue\b|\bnext\.?js\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "text",
        re.compile(
            r"(\bтекст[а-я]*\b|\bкопирайт[а-я]*\b|\bстать[а-я]+\b|"
            r"\bseo\b|\bпереводчик[а-я]*\b|\bперевод\s+с\b|"
            r"\bрерайт[а-я]*\b|\bописани[а-я]+\s+товаров\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "design",
        re.compile(
            r"(\bдизайн[а-я]*\b|\bлоготип[а-я]*\b|\bбаннер[а-я]*\b|"
            r"\bпрезентац[а-я]*\b|\bfigma\b|\bphotoshop\b|"
            r"\bиллюстрац[а-я]*\b|\bобложк[а-я]*\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "automation",
        re.compile(
            r"(\bавтоматиз[а-я]*\b|\bскрипт[а-я]*\b|\bpython\b|"
            r"\bexcel\b|\bgoogle\s*sheets\b|"
            r"\bобработ[а-я]+\s+данн[а-я]+|\bмакрос[а-я]*\b|\bvba\b)",
            re.IGNORECASE,
        ),
    ),
)

# Budget patterns: require separator in the grouped form, otherwise fall
# through to \d+ so "7000" is parsed as 7000, not 700.
_BUDGET_PATTERNS = (
    re.compile(
        r"(?:бюджет|оплата|стоимост|цена|за\s+работу)[^\d]{0,15}"
        r"(\d{1,3}(?:[\s.,]\d{3})+|\d+)\s*([ткмКkM])?\s*(₽|руб|rub)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3}(?:[\s.,]\d{3})+|\d+)\s*([ткмКkM])?\s*(₽|руб\.?|rub)",
        re.IGNORECASE,
    ),
)

_URGENT_RE = re.compile(
    r"\b(срочно|asap|сегодня|до\s+вечера|на\s+сегодня|урочно)\b",
    re.IGNORECASE,
)

_CONTACT_RE = re.compile(r"(@[A-Za-z0-9_]{4,})")


def _parse_budget(text: str) -> int | None:
    for pat in _BUDGET_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(1).replace(" ", "").replace(".", "").replace(",", "")
        try:
            n = int(raw)
        except ValueError:
            continue
        mult_group = m.group(2) or ""
        mult = 1
        if mult_group.lower() in ("т", "k", "к"):
            mult = 1_000
        elif mult_group.lower() in ("м", "m"):
            mult = 1_000_000
        value = n * mult
        # Sanity: freelance orders are typically 300–1_000_000₽.
        if 100 <= value <= 5_000_000:
            return value
    return None


def classify_keyword(text: str) -> Classification:
    """Heuristic fallback classifier — no network calls."""
    is_order = bool(_ORDER_HINTS.search(text))

    category = "other"
    for name, pat in _CATEGORY_RULES:
        if pat.search(text):
            category = name
            break

    # If we found a category but not an "order" hint, still treat as order
    # when budget is present — short posts often skip "ищу" wording.
    budget = _parse_budget(text)
    if not is_order and (category != "other" or budget is not None):
        is_order = category != "other" and budget is not None

    urgency = "urgent" if _URGENT_RE.search(text) else None

    contacts = _CONTACT_RE.findall(text)
    # Filter out channel self-references by taking the last contact (usually the client).
    contact = contacts[-1] if contacts else None

    title = text.strip().splitlines()[0][:120] if text.strip() else ""

    return Classification(
        is_order=is_order,
        category=category,
        title=title,
        budget_rub=budget,
        urgency=urgency,
        contact=contact,
        confidence=0.55 if is_order else 0.3,
    )


# ------------------------------------------------------------------
# LLM backend
# ------------------------------------------------------------------
_LLM_SYSTEM = (
    "Ты классифицируешь сообщения из Telegram-каналов о фрилансе. "
    "Определи, является ли сообщение заказом/предложением работы от клиента, "
    "и извлеки структурированные поля. Отвечай СТРОГО одним JSON-объектом, "
    "без пояснений и markdown-оборачивания."
)

_LLM_USER_TEMPLATE = """Сообщение из Telegram-канала:
\"\"\"
{text}
\"\"\"

Верни JSON со следующими полями:
- is_order (bool): это заказ/вакансия от клиента (не обсуждение, не мем, не реклама обучения)?
- category (str): одна из [bot, parser, automation, website, text, design, other]
- title (str): краткое описание задачи, одна строка до 120 символов
- budget_rub (int or null): бюджет в рублях, если указан; null если не указан
- urgency (str or null): "urgent" если срочно, иначе null
- contact (str or null): @username или телефон клиента, если есть; иначе null
- confidence (float): 0..1 — насколько уверен в классификации

Только JSON."""


class LLMClassifier:
    def __init__(self, cfg: LLMConfig, timeout: float = 20.0):
        self.cfg = cfg
        self.timeout = timeout

    def classify(self, text: str) -> Classification:
        try:
            payload = {
                "model": self.cfg.model,
                "messages": [
                    {"role": "system", "content": _LLM_SYSTEM},
                    {
                        "role": "user",
                        "content": _LLM_USER_TEMPLATE.format(text=text[:4000]),
                    },
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }
            headers = {
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            }
            url = self.cfg.base_url.rstrip("/") + "/chat/completions"
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
            content = data["choices"][0]["message"]["content"]
            obj = json.loads(content)
            return Classification(
                is_order=bool(obj.get("is_order", False)),
                category=str(obj.get("category") or "other").lower(),
                title=str(obj.get("title") or "")[:160],
                budget_rub=_coerce_int(obj.get("budget_rub")),
                urgency=_coerce_str(obj.get("urgency")),
                contact=_coerce_str(obj.get("contact")),
                confidence=float(obj.get("confidence") or 0.7),
            )
        except Exception as e:
            log.warning("LLM classify failed (%s); falling back to keywords", e)
            return classify_keyword(text)


def _coerce_int(v: Any) -> int | None:
    if v is None or v == "" or v is False:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------
def make_classifier(cfg: LLMConfig):
    if cfg.enabled:
        log.info("Using LLM classifier: %s / %s", cfg.provider, cfg.model)
        llm = LLMClassifier(cfg)
        return llm.classify
    log.info("LLM_API_KEY not set — using keyword fallback classifier")
    return classify_keyword
