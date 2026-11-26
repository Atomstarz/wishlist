#!/usr/bin/env python3
"""Вишлист: сайт на чистом Python (без внешних зависимостей).

Запуск:  python3 app.py
Сайт доступен всем устройствам в локальной сети (адрес покажется в консоли).

Настройки через переменные окружения:
    PORT=8080                  другой порт
    HOST=127.0.0.1             только этот компьютер
    EDIT_PASSWORD=секрет       смотреть могут все, а менять список -
                               только тот, кто знает пароль
"""
import hmac
import json
import os
import re
import socket
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
EDIT_PASSWORD = os.environ.get("EDIT_PASSWORD", "")
DB_PATH = Path(__file__).with_name("wishlist.db")


def lan_ip():
    """IP этого компьютера в локальной сети (без отправки данных наружу)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                price REAL,
                note TEXT NOT NULL DEFAULT '',
                priority INTEGER NOT NULL DEFAULT 2,
                done INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вишлист</title>
<style>
  :root {
    color-scheme: dark;
    --paper: #0c090e;
    --card: #17111c;
    --field: #0c090e;
    --ink: #f8eef4;
    --muted: #a58fa8;
    --line: #2f2336;
    --ribbon: #ff2e93;
    --done: #ffb3d9;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  main { max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }
  h1 {
    font: 700 clamp(2.2rem, 7vw, 3.4rem)/1.05 Georgia, "Iowan Old Style", serif;
    margin: 0 0 6px; letter-spacing: -0.02em; color: var(--ribbon);
    text-shadow: 0 0 28px rgba(255, 46, 147, .45);
  }
  .sub { color: var(--muted); margin: 0 0 28px; }
  .stats { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 20px; }
  .stats b { font: 700 1.4rem Georgia, serif; display: block; }
  .stats span { color: var(--muted); font-size: .9rem; }

  form {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 16px; display: grid; gap: 10px; grid-template-columns: 1fr 1fr;
    margin-bottom: 28px;
  }
  form .wide { grid-column: 1 / -1; }
  input, select, button { font: inherit; color: inherit; }
  input, select {
    width: 100%; padding: 10px 12px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--field);
  }
  input:focus-visible, select:focus-visible, button:focus-visible, a:focus-visible {
    outline: 2px solid var(--ribbon); outline-offset: 2px;
  }
  .primary {
    background: var(--ribbon); color: #0c090e; border: 0; border-radius: 8px;
    padding: 11px 16px; font-weight: 600; cursor: pointer;
  }

  .filters { display: flex; gap: 8px; margin-bottom: 14px; }
  .filters button {
    background: none; border: 1px solid var(--line); border-radius: 999px;
    padding: 5px 14px; cursor: pointer; color: var(--muted);
  }
  .filters button[aria-pressed="true"] {
    background: var(--ribbon); color: #0c090e; border-color: var(--ribbon);
  }

  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
  li {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 16px 18px 16px 22px; position: relative;
    display: grid; grid-template-columns: 1fr auto; gap: 4px 16px;
  }
  /* цветная лента слева = приоритет */
  li::before {
    content: ""; position: absolute; left: 0; top: 14px; bottom: 14px; width: 5px;
    border-radius: 0 4px 4px 0; background: var(--line);
  }
  li[data-p="3"]::before { background: var(--ribbon); }
  li[data-p="2"]::before { background: #8a4a6b; }
  li h2 { font: 600 1.15rem/1.3 system-ui, sans-serif; margin: 0; }
  li.done h2 { text-decoration: line-through; color: var(--muted); }
  li:not(.done)[data-p="3"] { border-color: #5a1f40; }
  li.done::before { background: var(--done); }
  .price { font: 700 1.1rem Georgia, serif; white-space: nowrap; text-align: right; }
  .note { grid-column: 1 / -1; color: var(--muted); margin: 0; }
  .actions { grid-column: 1 / -1; display: flex; gap: 14px; align-items: center; margin-top: 6px; }
  .actions a, .actions button {
    background: none; border: 0; padding: 0; cursor: pointer;
    color: var(--ink); text-decoration: underline; text-underline-offset: 3px; font-size: .92rem;
  }
  .actions .del { color: var(--muted); margin-left: auto; }
  .empty { text-align: center; color: var(--muted); padding: 40px 0; }
  @media (max-width: 520px) { form { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
  <h1>Мой вишлист</h1>
  <p class="sub">Всё, что хочется получить. Отмечайте то, что уже подарили или купили.</p>

  <div class="stats">
    <div><b id="s-count">0</b><span>желаний</span></div>
    <div><b id="s-done">0</b><span>исполнено</span></div>
    <div><b id="s-sum">0 ₽</b><span>осталось на сумму</span></div>
  </div>

  <form id="add">
    <input class="wide" name="title" placeholder="Что хочется?" required maxlength="200">
    <input name="url" type="url" placeholder="Ссылка на товар">
    <input name="price" type="number" min="0" step="any" placeholder="Цена, ₽">
    <input class="wide" name="note" placeholder="Заметка: размер, цвет, где искать" maxlength="500">
    <select name="priority" aria-label="Приоритет">
      <option value="3">Очень хочу</option>
      <option value="2" selected>Было бы здорово</option>
      <option value="1">Когда-нибудь</option>
    </select>
    <button class="primary" type="submit">Добавить в список</button>
  </form>

  <div class="filters" role="group" aria-label="Фильтр">
    <button data-f="all" aria-pressed="true">Все</button>
    <button data-f="open" aria-pressed="false">Ждут</button>
    <button data-f="done" aria-pressed="false">Исполнены</button>
  </div>

  <ul id="list"></ul>
</main>

<script>
const $ = (s) => document.querySelector(s);
let items = [];
let filter = "all";
const fmt = new Intl.NumberFormat("ru-RU");

async function api(path, opts = {}) {
  const write = opts.method && opts.method !== "GET";
  for (let attempt = 0; attempt < 2; attempt++) {
    const headers = {...(opts.headers || {})};
    const pw = localStorage.getItem("editPassword");
    if (write && pw) headers["X-Edit-Password"] = pw;
    const r = await fetch(path, {...opts, headers});
    if (r.status === 401) {
      const entered = prompt("Менять список можно только с паролем. Введите пароль:");
      if (entered === null) throw new Error("отменено");
      localStorage.setItem("editPassword", entered);
      continue;
    }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  localStorage.removeItem("editPassword");
  alert("Неверный пароль");
  throw new Error("неверный пароль");
}

async function load() {
  items = await api("/api/items");
  render();
}

function safeUrl(u) {
  try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : ""; }
  catch { return ""; }
}

function render() {
  const open = items.filter((i) => !i.done);
  $("#s-count").textContent = items.length;
  $("#s-done").textContent = items.length - open.length;
  $("#s-sum").textContent = fmt.format(open.reduce((a, i) => a + (i.price || 0), 0)) + " ₽";

  const shown = items.filter((i) =>
    filter === "all" ? true : filter === "open" ? !i.done : !!i.done);
  const ul = $("#list");
  ul.replaceChildren();

  if (!shown.length) {
    const e = document.createElement("li");
    e.className = "empty";
    e.style.display = "block";
    e.textContent = items.length ? "В этом разделе пока пусто." : "Список пуст. Добавьте первое желание выше.";
    ul.append(e);
    return;
  }

  for (const it of shown) {
    const li = document.createElement("li");
    li.dataset.p = it.priority;
    if (it.done) li.className = "done";

    const h = document.createElement("h2");
    h.textContent = it.title;
    li.append(h);

    const p = document.createElement("div");
    p.className = "price";
    p.textContent = it.price != null ? fmt.format(it.price) + " ₽" : "";
    li.append(p);

    if (it.note) {
      const n = document.createElement("p");
      n.className = "note";
      n.textContent = it.note;
      li.append(n);
    }

    const act = document.createElement("div");
    act.className = "actions";
    const href = safeUrl(it.url);
    if (href) {
      const a = document.createElement("a");
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.textContent = "Открыть ссылку";
      act.append(a);
    }
    const t = document.createElement("button");
    t.textContent = it.done ? "Вернуть в список" : "Отметить исполненным";
    t.onclick = async () => {
      await api("/api/items/" + it.id, {
        method: "PATCH", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({done: it.done ? 0 : 1}),
      });
      load();
    };
    const d = document.createElement("button");
    d.className = "del";
    d.textContent = "Удалить";
    d.onclick = async () => {
      if (!confirm("Удалить «" + it.title + "»?")) return;
      await api("/api/items/" + it.id, {method: "DELETE"});
      load();
    };
    act.append(t, d);
    li.append(act);
    ul.append(li);
  }
}

$("#add").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  await api("/api/items", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(Object.fromEntries(f)),
  });
  e.target.reset();
  load();
});

document.querySelectorAll(".filters button").forEach((b) => {
  b.onclick = () => {
    filter = b.dataset.f;
    document.querySelectorAll(".filters button")
      .forEach((x) => x.setAttribute("aria-pressed", x === b));
    render();
  };
});

load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "Wishlist/1.0"

    # ---- helpers ----
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100_000:
            raise ValueError("слишком большой запрос")
        return json.loads(self.rfile.read(length) or b"{}")

    def authorized(self):
        """Если пароль задан, изменения разрешены только с верным паролем."""
        if not EDIT_PASSWORD:
            return True
        given = self.headers.get("X-Edit-Password", "")
        if hmac.compare_digest(given.encode(), EDIT_PASSWORD.encode()):
            return True
        self.send_json({"error": "нужен пароль"}, 401)
        return False

    def item_id(self):
        m = re.fullmatch(r"/api/items/(\d+)", self.path)
        return int(m.group(1)) if m else None

    # ---- routes ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/items":
            with db() as c:
                rows = c.execute(
                    "SELECT * FROM items ORDER BY done, priority DESC, id DESC"
                ).fetchall()
            self.send_json([dict(r) for r in rows])
        else:
            self.send_json({"error": "не найдено"}, 404)

    def do_POST(self):
        if self.path != "/api/items":
            return self.send_json({"error": "не найдено"}, 404)
        if not self.authorized():
            return
        try:
            d = self.read_json()
            title = str(d.get("title", "")).strip()[:200]
            if not title:
                raise ValueError("нужно название")
            url = str(d.get("url", "")).strip()
            if url and not re.match(r"https?://", url, re.I):
                raise ValueError("ссылка должна начинаться с http:// или https://")
            price = d.get("price")
            price = float(price) if price not in (None, "") else None
            priority = int(d.get("priority", 2))
            if priority not in (1, 2, 3):
                priority = 2
            note = str(d.get("note", "")).strip()[:500]
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return self.send_json({"error": str(e)}, 400)
        with db() as c:
            cur = c.execute(
                "INSERT INTO items (title, url, price, note, priority) VALUES (?,?,?,?,?)",
                (title, url, price, note, priority),
            )
        self.send_json({"id": cur.lastrowid}, 201)

    def do_PATCH(self):
        if not self.authorized():
            return
        iid = self.item_id()
        if iid is None:
            return self.send_json({"error": "не найдено"}, 404)
        try:
            done = 1 if self.read_json().get("done") else 0
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_json({"error": str(e)}, 400)
        with db() as c:
            c.execute("UPDATE items SET done=? WHERE id=?", (done, iid))
        self.send_json({"ok": True})

    def do_DELETE(self):
        if not self.authorized():
            return
        iid = self.item_id()
        if iid is None:
            return self.send_json({"error": "не найдено"}, 404)
        with db() as c:
            c.execute("DELETE FROM items WHERE id=?", (iid,))
        self.send_json({"ok": True})


if __name__ == "__main__":
    init_db()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Вишлист запущен. Остановить: Ctrl+C")
    print(f"  на этом компьютере:  http://127.0.0.1:{PORT}")
    if HOST in ("0.0.0.0", ""):
        print(f"  в локальной сети:    http://{lan_ip()}:{PORT}")
    print("  режим: " + ("смотреть всем, менять по паролю" if EDIT_PASSWORD
                         else "менять может любой в сети (задайте EDIT_PASSWORD)"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
