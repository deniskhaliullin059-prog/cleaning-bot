import sqlite3
import json
import requests
import os
import subprocess
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response, stream_with_context, session, redirect, url_for
import queue
import threading
import functools

from dotenv import load_dotenv
load_dotenv()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# Инициализируем БД при старте (нужно и под gunicorn)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, name TEXT, phone TEXT, service TEXT,
            address TEXT, date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_sent INTEGER DEFAULT 0,
            admin_message_id INTEGER,
            rating INTEGER DEFAULT NULL,
            review_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, user_name TEXT, direction TEXT,
            text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col in ["admin_message_id INTEGER", "rating INTEGER DEFAULT NULL",
                "review_sent INTEGER DEFAULT 0", "status TEXT DEFAULT 'new'"]:
        try:
            c.execute(f"ALTER TABLE orders ADD COLUMN {col}")
        except Exception:
            pass
    conn.commit()
    conn.close()

init_db()

# Запускаем бота как фоновый процесс с авто-перезапуском
def _start_bot():
    import time
    bot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
    while True:
        subprocess.run([sys.executable, bot_path])
        time.sleep(10)  # пауза перед перезапуском (даёт время старому контейнеру остановиться)

threading.Thread(target=_start_bot, daemon=True).start()

# SSE очередь для уведомлений
sse_clients = []
sse_lock = threading.Lock()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, name TEXT, phone TEXT, service TEXT,
            address TEXT, date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_sent INTEGER DEFAULT 0,
            admin_message_id INTEGER,
            rating INTEGER DEFAULT NULL,
            review_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, user_name TEXT, direction TEXT,
            text TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col in ["admin_message_id INTEGER", "rating INTEGER DEFAULT NULL",
                "review_sent INTEGER DEFAULT 0", "status TEXT DEFAULT 'new'"]:
        try:
            c.execute(f"ALTER TABLE orders ADD COLUMN {col}")
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def push_sse_event(data):
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


# ─── Авторизация ──────────────────────────────────────────────────────────────

@app.route("/debug-env-keys")
def debug_env_keys():
    keys = sorted(os.environ.keys())
    return jsonify({
        "env_keys": keys,
        "crm_password_set": "CRM_PASSWORD" in os.environ,
        "crm_pass_set": "CRM_PASS" in os.environ,
    })


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        crm_password = os.environ.get("CRM_PASS") or os.environ.get("CRM_PASSWORD") or "vid2026"
        if request.form.get("password") == crm_password:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Неверный пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Страницы ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/chats")
@login_required
def chats():
    return render_template("chats.html")


@app.route("/kanban")
@login_required
def kanban():
    return render_template("kanban.html")


# ─── API: Статистика ──────────────────────────────────────────────────────────

@app.route("/api/stats")
@login_required
def api_stats():
    conn = get_db()
    c = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Заявки сегодня
    c.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (today,))
    today_count = c.fetchone()[0]

    # Заявки за неделю
    c.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (week_ago,))
    week_count = c.fetchone()[0]

    # Всего заявок
    c.execute("SELECT COUNT(*) FROM orders")
    total_count = c.fetchone()[0]

    # Уникальные клиенты
    c.execute("SELECT COUNT(DISTINCT user_id) FROM orders")
    clients_count = c.fetchone()[0]

    # Средний рейтинг
    c.execute("SELECT AVG(rating) FROM orders WHERE rating IS NOT NULL")
    avg_rating = c.fetchone()[0]
    avg_rating = round(avg_rating, 1) if avg_rating else 0

    # Заявки по дням (последние 14 дней)
    c.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM orders
        WHERE created_at >= DATE('now', '-14 days')
        GROUP BY DATE(created_at)
        ORDER BY day
    """)
    days_data = [{"day": r["day"], "count": r["cnt"]} for r in c.fetchall()]

    # Заявки по услугам
    c.execute("""
        SELECT service, COUNT(*) as cnt
        FROM orders
        GROUP BY service
        ORDER BY cnt DESC
        LIMIT 8
    """)
    services_data = [{"service": r["service"] or "Не указано", "count": r["cnt"]} for r in c.fetchall()]

    # По статусам
    c.execute("""
        SELECT status, COUNT(*) as cnt FROM orders GROUP BY status
    """)
    statuses = {r["status"]: r["cnt"] for r in c.fetchall()}

    # Последние 10 заявок
    c.execute("""
        SELECT id, name, phone, service, address, date, status, rating, created_at
        FROM orders ORDER BY id DESC LIMIT 10
    """)
    recent = []
    for r in c.fetchall():
        recent.append({
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],
            "service": r["service"],
            "address": r["address"],
            "date": r["date"],
            "status": r["status"] or "new",
            "rating": r["rating"],
            "created_at": r["created_at"],
        })

    conn.close()
    return jsonify({
        "today_count": today_count,
        "week_count": week_count,
        "total_count": total_count,
        "clients_count": clients_count,
        "avg_rating": avg_rating,
        "days_data": days_data,
        "services_data": services_data,
        "statuses": statuses,
        "recent": recent,
    })


# ─── API: Чаты ────────────────────────────────────────────────────────────────

@app.route("/api/clients")
@login_required
def api_clients():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT m.user_id,
               m.user_name,
               MAX(m.timestamp) as last_time,
               (SELECT text FROM messages m2 WHERE m2.user_id = m.user_id ORDER BY m2.id DESC LIMIT 1) as last_msg,
               COUNT(CASE WHEN m.direction='in' THEN 1 END) as in_count
        FROM messages m
        GROUP BY m.user_id
        ORDER BY last_time DESC
    """)
    clients = []
    for r in c.fetchall():
        clients.append({
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "last_time": r["last_time"],
            "last_msg": r["last_msg"],
            "in_count": r["in_count"],
        })
    conn.close()
    return jsonify(clients)


@app.route("/api/messages/<int:user_id>")
@login_required
def api_messages(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, user_name, direction, text, timestamp
        FROM messages WHERE user_id=?
        ORDER BY id ASC
    """, (user_id,))
    msgs = []
    for r in c.fetchall():
        msgs.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "direction": r["direction"],
            "text": r["text"],
            "timestamp": r["timestamp"],
        })
    conn.close()
    return jsonify(msgs)


@app.route("/api/send/<int:user_id>", methods=["POST"])
@login_required
def api_send(user_id):
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Пустое сообщение"}), 400

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": user_id, "text": text})
    if not resp.ok:
        return jsonify({"ok": False, "error": resp.text}), 500

    # сохранить в БД
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (user_id, user_name, direction, text) VALUES (?, ?, ?, ?)",
        (user_id, "ООО ВИД", "out", text)
    )
    conn.commit()
    msg_id = c.lastrowid
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.close()

    push_sse_event(json.dumps({
        "type": "message",
        "user_id": user_id,
        "direction": "out",
        "text": text,
        "timestamp": ts,
    }))

    return jsonify({"ok": True, "id": msg_id, "timestamp": ts})


# ─── API: Канбан ──────────────────────────────────────────────────────────────

@app.route("/api/orders")
@login_required
def api_orders():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, name, phone, service, address, date, status, rating, created_at
        FROM orders ORDER BY id DESC
    """)
    orders = []
    for r in c.fetchall():
        orders.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "name": r["name"],
            "phone": r["phone"],
            "service": r["service"],
            "address": r["address"],
            "date": r["date"],
            "status": r["status"] or "new",
            "rating": r["rating"],
            "created_at": r["created_at"],
        })
    conn.close()
    return jsonify(orders)


@app.route("/api/orders/<int:order_id>/status", methods=["PATCH"])
@login_required
def api_update_status(order_id):
    data = request.get_json()
    new_status = data.get("status")
    allowed = ("new", "in_progress", "done", "cancelled")
    if new_status not in allowed:
        return jsonify({"ok": False, "error": "Неверный статус"}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ─── SSE: Уведомления ─────────────────────────────────────────────────────────

@app.route("/api/events")
@login_required
def api_events():
    q = queue.Queue(maxsize=50)
    with sse_lock:
        sse_clients.append(q)

    def generate():
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                try:
                    msg = q.get(timeout=20)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
