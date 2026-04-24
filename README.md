# freelance-radar

Агент, который смотрит за Telegram-каналами с заказами на фриланс,
фильтрует их (код / сайты / тексты / дизайн / боты / парсеры) и шлёт
только подходящие тебе — в ЛС Telegram и/или в локальный дашборд.
Ты решаешь, что брать.

## Два режима

### 🟢 Режим `web` — без API_ID, без номера телефона (рекомендую)

Парсит публичные веб-страницы каналов `t.me/s/<name>`. Уведомления
присылает **твой собственный бот**, созданный у [@BotFather](https://t.me/BotFather)
за 30 секунд — никакого `my.telegram.org`, никакой регистрации приложения.

```
t.me/s/<channel>  ──►  HTTP-поллинг каждые ~2 мин
                              ↓
                     Классификатор (LLM/keywords)
                              ↓
                  ┌───────────┴───────────┐
                  ▼                       ▼
        Твой TG-бот (ЛС)         Локальный дашборд
        (@BotFather)             (localhost:8080)
```

### 🟡 Режим `telethon` — реалтайм, но нужен TG API_ID

Логинится под твоим TG-аккаунтом и читает каналы в реальном времени.
Нужны `API_ID`, `API_HASH`, номер телефона и SMS-код при первом запуске.
Подходит, если хочешь минимальную задержку и готов получить креды у
[my.telegram.org](https://my.telegram.org/auth).

## Что умеет

- Следит за любым количеством публичных каналов (список в `channels.yaml`).
- Определяет: это заказ или нет; извлекает категорию, бюджет, срочность,
  контакт клиента.
- Отфильтровывает нерелевантное (категории и минимальный бюджет — в `.env`).
- Шлёт красивую карточку в Telegram (через бота или через Telethon).
- Показывает все отфильтрованные заказы на локальном HTML-дашборде с
  фильтрами по категории / бюджету / срочности.
- Хранит историю в SQLite — одну задачу дважды не пришлёт.
- Работает с LLM (DeepSeek / OpenAI / любой OpenAI-совместимый) или без
  него (keyword-фильтр — запускается офлайн).

## Быстрый старт (режим web)

```bash
git clone <repo-url> freelance-radar
cd freelance-radar

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # Windows: copy .env.example .env
# теперь открой .env и заполни BOT_TOKEN и CHAT_ID (см. ниже)
```

### 1. Создай бота и получи `BOT_TOKEN`

1. Открой в Telegram → [@BotFather](https://t.me/BotFather)
2. Напиши `/newbot`
3. Придумай имя (например, `Мой фриланс-радар`) и username (должен
   заканчиваться на `bot`, например `stas_radar_bot`)
4. BotFather пришлёт строку вида `123456789:AAFxxxxxxxxxxxxxxxxxxxxxx` —
   это `BOT_TOKEN`. Вставь её в `.env`.

### 2. Получи свой `CHAT_ID`

Простейший способ: напиши любому из этих ботов — они сразу покажут твой id:

- [@userinfobot](https://t.me/userinfobot) → `/start`
- или [@getmyid_bot](https://t.me/getmyid_bot)

Скопируй число и вставь в `CHAT_ID` в `.env`.

### 3. Напиши `/start` своему собственному боту

Это обязательный шаг в Telegram: бот не может писать тебе первым, пока
ты не начнёшь с ним диалог.

### 4. Проверь, что всё настроено

```bash
python -m freelance_radar.main check-bot
```

Если всё ок — в Telegram прилетит тестовое сообщение. Если нет —
команда подскажет что именно сломано.

### 5. Запусти радар

```bash
python -m freelance_radar.main run
```

В логах увидишь `bot authorized as @stas_radar_bot; watching 11 channels…`.
Дальше карточки с новыми заказами будут прилетать тебе в ЛС к боту.

### 6. (Опция) Открой дашборд

В отдельном терминале:

```bash
python -m freelance_radar.main dashboard
```

Открой `http://localhost:8080` — увидишь историю всех подходящих заказов
с фильтрами и автообновлением.

## Команды CLI

```bash
python -m freelance_radar.main run               # запуск сбора (web/telethon)
python -m freelance_radar.main dashboard         # HTML-дашборд
python -m freelance_radar.main check-bot         # проверка BOT_TOKEN + CHAT_ID
python -m freelance_radar.main test-classify --text "Нужен бот ..."
python -m freelance_radar.main stats             # сводка по БД
```

## Настройка каналов

Правь `channels.yaml`. Дефолтный список — 11 активных русскоязычных
каналов с заказами/вакансиями по коду, текстам и дизайну. Формат:

```yaml
channels:
  - "@progjob"
  - "@pythonrabota"
  - "@writers_jobs"
  # ... добавляй свои
```

Проверить, что канал читается через веб-версию, просто: открой
`https://t.me/s/<name>` в браузере — если видишь посты, радар тоже видит.

## Настройка фильтра в `.env`

- `CATEGORIES=bot,parser,automation,website,text,design` — какие
  категории пропускать в уведомления. Убирай те, что не нужны.
- `MIN_BUDGET_RUB=0` — минимальный бюджет в ₽. Заказы ниже отфильтровываются.
- `WEB_POLL_SECONDS=120` — период опроса каналов. Меньше 60 не
  рекомендуется, можно словить rate-limit от Telegram.

## Режим telethon (опционально)

Если готов получить API_ID и хочешь работать в реальном времени:

1. `MODE=telethon` в `.env`
2. Получи `TG_API_ID` + `TG_API_HASH` на
   [my.telegram.org](https://my.telegram.org/auth) → API development tools
3. Заполни `TG_PHONE=+7XXXXXXXXXX` и `TG_NOTIFY_TARGET=me`
4. Первый запуск — попросит код из SMS, дальше всё автоматом

Файл `radar.session` появится после первой авторизации — он уже в
`.gitignore`, не коммитить.

## Постоянный запуск

### На своём ПК
`screen` / `tmux` — работает пока комп включён.

### systemd на Linux (Oracle Cloud Free Tier и т. п.)

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

Для дашборда заводится отдельный сервис `freelance-radar-dashboard.service`
с `ExecStart=… dashboard`.

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "freelance_radar.main", "run"]
```

## Безопасность

- `.env` и `*.session` — в `.gitignore`, никогда не коммить.
- В режиме `web` не используется твой личный TG-аккаунт, только бот.
- В режиме `telethon` риск бана при обычном использовании (только
  чтение каналов, без рассылки) — минимальный. Если страшно — возьми
  виртуальный номер (премиум-тариф у 5sim/sms-activate; дешёвые в бане).

## Лицензия

MIT
