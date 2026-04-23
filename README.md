# freelance-radar

Агент, который смотрит за Telegram-каналами с заказами на фриланс, фильтрует
их (код / сайты / тексты / дизайн / боты / парсеры) и шлёт только подходящие
тебе в личку. Ты решаешь, что брать.

```
TG-каналы ─► Telethon ─► Классификатор (LLM+keywords) ─► Твой Telegram
```

## Что умеет

- Подписывается на любое количество публичных каналов с заказами.
- Определяет, это заказ или нет; извлекает категорию, бюджет, срочность,
  контакт клиента.
- Отфильтровывает нерелевантное (категории задаются в `.env`).
- Шлёт красивую карточку в твой TG — в «Избранное» или другому юзеру.
- Хранит историю в SQLite, чтобы не присылать одну и ту же задачу дважды.
- Работает с LLM (DeepSeek / OpenAI / любой OpenAI-совместимый) или без него
  (keyword-фильтр).

## Установка

```bash
git clone <repo-url> freelance-radar
cd freelance-radar

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
# или: pip install -e .
```

## Получить Telegram API_ID / API_HASH

1. Открой https://my.telegram.org/auth
2. Войди по своему номеру, введи код из TG.
3. «API development tools» → создай приложение:
   - App title: `freelance-radar`
   - Short name: `freelance_radar`
   - Platform: `Desktop`
4. Скопируй `api_id` (число) и `api_hash` (строка).

## Настройка

```bash
cp .env.example .env
# Заполни TG_API_ID, TG_API_HASH, TG_PHONE, TG_NOTIFY_TARGET.
# Опционально: LLM_API_KEY (DeepSeek / OpenAI).
```

### Куда шлём уведомления: `TG_NOTIFY_TARGET`

- `me` — в «Избранное» (Saved Messages). **Рекомендую для старта.**
- `@username` — личка другому аккаунту.
- Числовой `user_id` — тоже работает.

### Каналы

Правь `channels.yaml`. Стартовый список покрывает боты / парсинг / сайты /
тексты / дизайн.

## Запуск

```bash
# тест классификатора (без Telegram)
python -m freelance_radar.main test-classify --text "Нужен бот для записи клиентов в парикмахерскую. Бюджет 15000 руб. Срочно. @ivan"

# первый запуск — попросит ввести код из SMS
python -m freelance_radar.main run

# статистика
python -m freelance_radar.main stats
```

После первого запуска рядом появится файл `radar.session` — держи его рядом,
это авторизация. Не коммить его в git (он уже в `.gitignore`).

## Как оставить работать постоянно

### Вариант 1. На своём ПК
Запусти в `screen` / `tmux` — работает пока комп включён.

### Вариант 2. systemd на Linux-сервере (напр. Oracle Cloud Free Tier)

`/etc/systemd/system/freelance-radar.service`:

```ini
[Unit]
Description=freelance-radar
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/freelance-radar
ExecStart=/home/ubuntu/freelance-radar/.venv/bin/python -m freelance_radar.main run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now freelance-radar
journalctl -u freelance-radar -f
```

### Вариант 3. Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "freelance_radar.main", "run"]
```

## Безопасность и риски

- Telethon логинится **под твоим Telegram-аккаунтом** — это нужно для чтения
  каналов (обычные боты так не могут).
- Риск бана при обычном использовании (только чтение, без рассылки) —
  минимальный.
- Никогда не коммить `.env` и `*.session` файлы. Оба уже в `.gitignore`.
- Если используешь виртуальный номер — бери премиум-тариф у провайдера
  (5sim/sms-activate), дешёвые часто в бане.

## Лицензия

MIT
