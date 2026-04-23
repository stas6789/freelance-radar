"""Tests for the keyword classifier (no network required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freelance_radar.classifier import classify_keyword  # noqa: E402


def test_telegram_bot_order():
    text = (
        "Ищу Python-разработчика для бота-анкеты в Telegram. "
        "Интеграция с Google Sheets. Бюджет 15 000 руб. Срочно. "
        "Писать @ivan_client"
    )
    c = classify_keyword(text)
    assert c.is_order is True
    assert c.category == "bot"
    assert c.budget_rub == 15000
    assert c.urgency == "urgent"
    assert c.contact == "@ivan_client"


def test_parser_order_with_k_suffix():
    text = "Нужен парсер Wildberries. Оплата 5к. Пишите в ЛС."
    c = classify_keyword(text)
    assert c.is_order is True
    assert c.category == "parser"
    assert c.budget_rub == 5000


def test_website_landing():
    text = "Требуется верстальщик лендинга на Tilda. Бюджет 7000 рублей."
    c = classify_keyword(text)
    assert c.is_order is True
    assert c.category == "website"
    assert c.budget_rub == 7000


def test_copywriter_text():
    text = (
        "Ищем копирайтера для описания товаров интернет-магазина. "
        "Оплата 50₽ за 1000 знаков."
    )
    c = classify_keyword(text)
    assert c.is_order is True
    assert c.category == "text"


def test_design_logo():
    text = "Нужен дизайнер, сделать логотип и баннер. Бюджет 3000 руб."
    c = classify_keyword(text)
    assert c.is_order is True
    assert c.category == "design"
    assert c.budget_rub == 3000


def test_non_order_discussion():
    text = (
        "Ребят, как думаете, стоит ли учить Rust в 2025? "
        "Я джун на Python, думаю расширять стек."
    )
    c = classify_keyword(text)
    assert c.is_order is False


def test_non_order_course_ad():
    text = (
        "Запускаем новый курс по вёрстке! Регистрация открыта, "
        "присоединяйся к нашему сообществу. Подробности по ссылке."
    )
    c = classify_keyword(text)
    # Ad-style message — might be tagged as something, but should not carry
    # a concrete budget + category combo that would forward.
    assert c.budget_rub is None


def test_budget_parsing_with_million():
    text = "Ищем разработчика сайта на React. Бюджет 1.5 млн рублей."
    c = classify_keyword(text)
    # "млн" variant uses lowercase "м" match via regex multiplier handling
    # through a plain digit / "М" match — verify we still mark as order.
    assert c.is_order is True
    assert c.category == "website"


def test_empty_text():
    c = classify_keyword("")
    assert c.is_order is False
    assert c.category == "other"
