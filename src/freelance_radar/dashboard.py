"""Local HTML dashboard for reviewing filtered orders."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from .config import Config
from .storage import Storage


log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Single-file HTML template — keeps deployment trivial (no static assets).
# ----------------------------------------------------------------------
_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<title>freelance-radar · заказы</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  :root {
    --bg: #0f1115;
    --panel: #161a22;
    --panel2: #1d212b;
    --border: #262b37;
    --fg: #e7e9ee;
    --muted: #8e96a5;
    --accent: #5ea8ff;
    --warn: #ff7a59;
    --ok: #3ecf8e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.45;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    background: var(--panel); position: sticky; top: 0; z-index: 5;
  }
  header h1 {
    font-size: 18px; margin: 0; font-weight: 600;
  }
  header .stats { color: var(--muted); font-size: 13px; }
  main { padding: 20px 24px; max-width: 1100px; margin: 0 auto; }
  .filters {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px;
    padding: 12px 14px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px;
  }
  .filters label { display: flex; align-items: center; gap: 6px; color: var(--muted); }
  .filters select, .filters input[type=number] {
    background: var(--panel2); color: var(--fg); border: 1px solid var(--border);
    border-radius: 6px; padding: 5px 8px; font: inherit;
  }
  .filters button {
    background: var(--accent); color: #0a0d14; border: 0; border-radius: 6px;
    padding: 5px 14px; font: inherit; font-weight: 600; cursor: pointer;
  }
  .filters button:hover { filter: brightness(1.08); }
  .order {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;
  }
  .order .top {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; margin-bottom: 6px; flex-wrap: wrap;
  }
  .order .badge {
    font-size: 12px; padding: 2px 8px; border-radius: 999px;
    background: var(--panel2); border: 1px solid var(--border); color: var(--accent);
  }
  .order .budget { color: var(--ok); font-weight: 600; }
  .order .urgent { color: var(--warn); font-weight: 600; }
  .order .title { font-weight: 600; margin: 4px 0 8px 0; }
  .order .body {
    color: var(--fg); white-space: pre-wrap; font-size: 13.5px;
    max-height: 160px; overflow: hidden; position: relative;
  }
  .order .body.open { max-height: none; }
  .order .more {
    color: var(--accent); cursor: pointer; font-size: 12px; margin-top: 4px;
    display: inline-block;
  }
  .order .meta { margin-top: 8px; color: var(--muted); font-size: 12px; }
  .order .meta a { color: var(--accent); text-decoration: none; }
  .order .meta a:hover { text-decoration: underline; }
  .empty {
    text-align: center; color: var(--muted); padding: 40px; font-size: 15px;
  }
</style>
</head>
<body>
<header>
  <h1>📡 freelance-radar</h1>
  <div class="stats" id="stats">…</div>
</header>
<main>
  <div class="filters">
    <label>Категория
      <select id="f-category">
        <option value="all">все</option>
        <option value="bot">боты</option>
        <option value="parser">парсеры</option>
        <option value="automation">автоматизация</option>
        <option value="website">сайты</option>
        <option value="text">тексты</option>
        <option value="design">дизайн</option>
        <option value="other">другое</option>
      </select>
    </label>
    <label>Мин. бюджет ₽
      <input id="f-budget" type="number" min="0" step="500" value="0" />
    </label>
    <label><input id="f-urgent" type="checkbox" /> только срочные</label>
    <button id="f-apply">Обновить</button>
    <span style="flex: 1"></span>
    <label style="color: var(--muted)">Автообновление
      <select id="f-refresh">
        <option value="30">каждые 30с</option>
        <option value="60">каждую минуту</option>
        <option value="0">выкл</option>
      </select>
    </label>
  </div>
  <div id="list"></div>
</main>
<script>
  const CAT_LABEL = {
    bot: "🤖 BOT", parser: "🕸 PARSER", automation: "⚙ AUTO",
    website: "🌐 САЙТ", text: "✍ ТЕКСТ", design: "🎨 ДИЗАЙН", other: "📌 ДРУГОЕ"
  };

  function fmt(n) { return n.toLocaleString("ru-RU").replace(/,/g, " "); }
  function esc(s) {
    const d = document.createElement("div"); d.textContent = s; return d.innerHTML;
  }

  async function load() {
    const cat = document.getElementById("f-category").value;
    const budget = document.getElementById("f-budget").value || 0;
    const urgent = document.getElementById("f-urgent").checked ? 1 : 0;
    const r = await fetch(`/api/orders?category=${cat}&min_budget=${budget}&urgent=${urgent}&limit=100`);
    const data = await r.json();
    render(data);
  }

  function render(data) {
    const list = document.getElementById("list");
    document.getElementById("stats").textContent =
      `${data.count} заказов · обновлено ${new Date(data.now * 1000).toLocaleTimeString("ru-RU")}`;

    if (data.orders.length === 0) {
      list.innerHTML = `<div class="empty">Пока ничего подходящего.<br>
        Агент сохраняет сюда только отфильтрованные заказы.</div>`;
      return;
    }

    list.innerHTML = data.orders.map(o => {
      const budget = o.budget_rub ? `💰 ${fmt(o.budget_rub)}₽` : "💰 не указан";
      const urgent = o.urgency === "urgent" ? `<span class="urgent">⏱ СРОЧНО</span>` : "";
      const contact = o.contact ? `💬 ${esc(o.contact)} · ` : "";
      const age = timeAgo(o.seen_at);
      return `
        <div class="order">
          <div class="top">
            <span class="badge">${CAT_LABEL[o.category] || o.category}</span>
            <span class="budget">${budget}</span>
            ${urgent}
            <span style="flex:1"></span>
            <span style="color: var(--muted); font-size: 12px;">${age}</span>
          </div>
          <div class="title">${esc(o.title || "")}</div>
          <div class="body" id="body-${o.channel}-${o.message_id}">${esc(o.raw_text || "")}</div>
          ${o.raw_text && o.raw_text.length > 400
              ? `<span class="more" onclick="this.previousElementSibling.classList.toggle('open'); this.textContent = this.previousElementSibling.classList.contains('open') ? 'свернуть' : 'развернуть';">развернуть</span>`
              : ""}
          <div class="meta">
            ${contact}
            <a href="${esc(o.link)}" target="_blank">${esc(o.channel)}</a>
          </div>
        </div>
      `;
    }).join("");
  }

  function timeAgo(ts) {
    const d = Math.max(0, Date.now() / 1000 - ts);
    if (d < 60) return "только что";
    if (d < 3600) return Math.floor(d / 60) + " мин назад";
    if (d < 86400) return Math.floor(d / 3600) + " ч назад";
    return Math.floor(d / 86400) + " дн назад";
  }

  let timer = null;
  function scheduleRefresh() {
    if (timer) clearInterval(timer);
    const sec = parseInt(document.getElementById("f-refresh").value, 10);
    if (sec > 0) timer = setInterval(load, sec * 1000);
  }

  document.getElementById("f-apply").addEventListener("click", load);
  document.getElementById("f-refresh").addEventListener("change", scheduleRefresh);

  load();
  scheduleRefresh();
</script>
</body>
</html>
"""


def build_app(cfg: Config, storage: Storage) -> FastAPI:
    app = FastAPI(title="freelance-radar", openapi_url=None, docs_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_HTML)

    @app.get("/api/orders")
    def list_orders(
        category: str = Query("all"),
        min_budget: int = Query(0, ge=0),
        urgent: int = Query(0),
        limit: int = Query(100, ge=1, le=500),
    ) -> JSONResponse:
        rows = storage.list_orders(
            limit=limit,
            category=category,
            min_budget=min_budget or None,
            urgent_only=bool(urgent),
        )
        for r in rows:
            r.pop("cls_json", None)
        return JSONResponse(
            {
                "count": len(rows),
                "orders": rows,
                "now": int(datetime.now(tz=timezone.utc).timestamp()),
            }
        )

    @app.get("/api/stats")
    def stats() -> JSONResponse:
        return JSONResponse(storage.stats())

    return app


def run_dashboard(cfg: Config, storage: Storage) -> None:
    import uvicorn

    app = build_app(cfg, storage)
    log.info(
        "dashboard at http://%s:%d",
        cfg.dashboard.host,
        cfg.dashboard.port,
    )
    uvicorn.run(
        app,
        host=cfg.dashboard.host,
        port=cfg.dashboard.port,
        log_level=cfg.log_level.lower(),
    )
