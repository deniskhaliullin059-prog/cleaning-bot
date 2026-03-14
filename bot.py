import logging
import sqlite3
import asyncio
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq

import os
from dotenv import load_dotenv
load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-5109857763"))
MANAGER_ID = int(os.environ.get("MANAGER_ID", "0"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.db"))

SYSTEM_PROMPT = (
    "Ты оператор клининговой компании ООО ВИД — профессиональный клининг для бизнеса и предприятий в Перми. "
    "Мы обслуживаем коммерческие помещения: офисы, торговые площади, производственные комплексы, склады, медицинские учреждения и бизнес-центры. "
    "ПРАВИЛО №1 — АБСОЛЮТНОЕ: каждое слово в твоём ответе должно быть написано только русскими буквами. Перед отправкой ответа проверь — нет ли в нём латиницы, иероглифов или других нерусских символов. Если есть — замени на русский эквивалент. "
    "ПРАВИЛО №2 — ГРАММАТИКА: каждое предложение должно быть полным — с подлежащим, сказуемым и правильными падежными окончаниями. Перед отправкой проверь каждое предложение: есть ли в нём глагол? Правильны ли падежи? Не обрывается ли мысль на полуслове? Если предложение неполное — перепиши его. "
    "ПРАВИЛО №3 — АБСОЛЮТНОЕ: у ООО ВИД нет сайта, нет личного кабинета, нет электронной почты и нет телефона для клиентов. Всё общение — только через этот Telegram-бот. Никогда не упоминай сайт, личный кабинет, электронную почту или звонки. Если нарушишь это правило — ответ будет неверным. "
    "Пиши просто и коротко. Используй короткие предложения без сложных оборотов. "
    "Не угадывай — всегда уточняй у клиента. "

    "РАСЧЁТ СТОИМОСТИ КОМПЛЕКСНОЙ УБОРКИ КОММЕРЧЕСКИХ ПОМЕЩЕНИЙ: "
    "Цена = площадь * 45 руб/кв.м. Минимум 5000 руб. "
    "Когда клиент выбирает комплексную уборку — ОБЯЗАТЕЛЬНО спроси площадь помещения и назови точную стоимость. "
    "Пример: 100 кв.м * 45 = 4500 руб, но минимум 5000 руб, значит цена 5000 руб. "
    "Пример: 200 кв.м * 45 = 9000 руб. "

    "СКИДКА ДЛЯ ПОСТОЯННЫХ КЛИЕНТОВ: "
    "Если в системном сообщении указано ПОСТОЯННЫЙ_КЛИЕНТ=ДА — клиент постоянный, применяй скидку 10% к итоговой стоимости. "
    "Обязательно сообщи клиенту что он получает скидку 10% как постоянный клиент ООО ВИД. "
    "Если ПОСТОЯННЫЙ_КЛИЕНТ=НЕТ — скидки нет. "

    "УСЛУГИ И ЦЕНЫ: "
    "1. РЕГУЛЯРНАЯ УБОРКА ОФИСОВ И ПОМЕЩЕНИЙ — от 25 руб/кв.м, минимум 3000 руб. "
    "Ежедневная, еженедельная или по графику. Уборка рабочих зон, переговорных, санузлов, кухни, коридоров. "
    "Вынос мусора, протирка поверхностей, мытьё полов, сантехника. "
    "2. КОМПЛЕКСНАЯ УБОРКА КОММЕРЧЕСКИХ ПОМЕЩЕНИЙ — 45 руб/кв.м, минимум 5000 руб. "
    "Глубокая уборка: все поверхности на полную высоту, труднодоступные места, техника KARCHER. "
    "Офисы, торговые залы, склады, производственные помещения. Время: 4-12 часов. "
    "3. ГЕНЕРАЛЬНАЯ УБОРКА — от 7000 руб. "
    "Полная уборка помещения: потолки, стены, все поверхности, мебель, сантехника. "
    "Удаление стойких загрязнений, обеззараживание. Время: 6-14 часов. "
    "4. УБОРКА ПОСЛЕ РЕМОНТА — от 7000 руб. "
    "Удаление строительной пыли, следов штукатурки, клея, лака, монтажной пены. "
    "Скидка 50% на повторную уборку в течение 2 недель. "
    "5. МЫТЬЁ ОКОН И ФАСАДОВ — от 80 руб/кв.м окна, альпинисты для высотных зданий. "
    "Витринные окна, панорамные фасады, офисные стеклопакеты. Минимум 3000 руб. "
    "6. ХИМЧИСТКА МЯГКОЙ МЕБЕЛИ — диван от 2500 руб, кресло от 900 руб, стул от 400 руб. "
    "7. ДЕЗИНФЕКЦИЯ И ОБЕЗЗАРАЖИВАНИЕ ПОМЕЩЕНИЙ — от 15 руб/кв.м, минимум 5000 руб. "
    "Антибактериальная обработка, устранение запахов, обработка от вредителей. "
    "8. УБОРКА ПРОИЗВОДСТВЕННЫХ ПОМЕЩЕНИЙ И СКЛАДОВ — от 20 руб/кв.м. "
    "Промышленная уборка с использованием специализированного оборудования. "
    "ВАЖНО: выезд и транспорт входит в стоимость при заказе от 10000 руб., при меньшем заказе отдельно. "

    "ОБЯЗАТЕЛЬНЫЙ ПОРЯДОК ДИАЛОГА: "
    "Шаг 1 - спроси какая услуга нужна и тип помещения. "
    "Шаг 2 - уточни детали: площадь помещения, характер загрязнений, периодичность (для регулярной). Назови точную стоимость. Если клиент постоянный — примени скидку 10%. "
    "Шаг 3 - спроси адрес объекта. "
    "Шаг 4 - спроси удобную дату и время. "
    "Шаг 5 - спроси контактное лицо (имя и должность). "
    "Шаг 6 - спроси номер телефона. "
    "Шаг 7 - повтори заявку и сообщи что менеджер свяжется в течение 30 минут для подтверждения. "
    "В конце сообщения на отдельной строке добавь: ЗАЯВКА_ПРИНЯТА: имя=[имя], телефон=[телефон], услуга=[услуга], адрес=[адрес], дата=[дата], цена=[итоговая стоимость числом в рублях без знака рубля] "
    "КРИТИЧЕСКИ ВАЖНО: добавляй метку ЗАЯВКА_ПРИНЯТА ТОЛЬКО если у тебя есть ВСЕ данные: реальное имя, реальный номер телефона (цифры), адрес, услуга и дата. "
    "Если хотя бы одно поле не заполнено — НЕ добавляй метку ЗАЯВКА_ПРИНЯТА, а задай уточняющий вопрос. "
    "ВАЖНО: не пропускай шаги 5 и 6! Задавай строго по одному вопросу за раз. "

    "РЕФЕРАЛЬНАЯ ПРОГРАММА: "
    "Реферальную ссылку клиент получает командой /myref прямо в этом боте — больше никак. "
    "За каждого нового клиента по ссылке реферер получает скидку 5% на следующую уборку. "
    "Если клиент спрашивает про реферальную ссылку — ответь ТОЛЬКО: напишите команду /myref в этом боте и получите свою ссылку."
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=GROQ_API_KEY)
conversations = {}
night_notified = set()  # user_ids, получившие ночное уведомление в текущей сессии


def is_night_hours():
    hour = datetime.now().hour
    return hour >= 20 or hour < 9

def clean_text(text):
    # Убираем управляющие символы и нежелательные скрипты (CJK, арабский, хинди и др.)
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    result = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\u3040-\u30ff\uff00-\uffef'
                    r'\u0600-\u06ff\u0900-\u097f\u0e00-\u0e7f]', '', result)
    # Убираем слова из латинских букв (3+ символов) — LLM иногда вставляет иностранные слова
    result = re.sub(r'\b[a-zA-Z]{3,}\b', '', result)
    result = re.sub(r' +', ' ', result)
    return result.strip()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            phone TEXT,
            service TEXT,
            address TEXT,
            date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_sent INTEGER DEFAULT 0,
            admin_message_id INTEGER,
            rating INTEGER DEFAULT NULL,
            review_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            price REAL DEFAULT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            direction TEXT,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            notified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(referred_id)
        )
    """)
    # миграция существующих таблиц
    migrations = [
        "admin_message_id INTEGER",
        "rating INTEGER DEFAULT NULL",
        "review_sent INTEGER DEFAULT 0",
        "status TEXT DEFAULT 'new'",
        "price REAL DEFAULT NULL",
    ]
    for col in migrations:
        try:
            c.execute(f"ALTER TABLE orders ADD COLUMN {col}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def save_message(user_id, user_name, direction, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (user_id, user_name, direction, text) VALUES (?, ?, ?, ?)",
        (user_id, user_name, direction, text)
    )
    conn.commit()
    conn.close()

def save_order(user_id, name, phone, service, address, date, admin_message_id=None, price=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, name, phone, service, address, date, admin_message_id, status, price) VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)",
        (user_id, name, phone, service, address, date, admin_message_id, price)
    )
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Заявка сохранена: {name}, {phone}, {service}")
    return order_id

def get_order_by_message_id(message_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE admin_message_id=?", (message_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_rating(order_id, rating):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET rating=? WHERE id=?", (rating, order_id))
    conn.commit()
    conn.close()

def get_today_orders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "SELECT id, name, phone, service, address, date, rating FROM orders WHERE created_at >= ? ORDER BY id DESC",
        (today,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_client_order_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def is_loyal_client(user_id):
    return get_client_order_count(user_id) >= 3

def parse_order(text, user_id):
    if "ЗАЯВКА_ПРИНЯТА:" not in text:
        return None
    try:
        data = {}
        part = text.split("ЗАЯВКА_ПРИНЯТА:")[1].strip()
        part = part.split("\n")[0]
        for item in part.split(","):
            if "=" in item:
                key, val = item.strip().split("=", 1)
                val = val.strip()
                val = re.split(r'[.!]', val)[0].strip()
                data[key.strip()] = val
        data["user_id"] = user_id
        return data
    except Exception as e:
        logger.error(f"Ошибка парсинга заявки: {e}")
        return None

async def notify_admin(app, data, loyal=False):
    loyal_text = "⭐ ПОСТОЯННЫЙ КЛИЕНТ — скидка 10%\n" if loyal else ""
    price_val = data.get("цена", "")
    price_text = f"💰 Стоимость: {price_val} руб.\n" if price_val else ""
    text = (
        "🏢 НОВАЯ ЗАЯВКА — ООО ВИД\n\n"
        f"{loyal_text}"
        f"👤 Контактное лицо: {data.get('имя', '')}\n"
        f"📞 Телефон: {data.get('телефон', '')}\n"
        f"🏠 Адрес объекта: {data.get('адрес', '')}\n"
        f"🛠 Услуга: {data.get('услуга', '')}\n"
        f"📅 Дата и время: {data.get('дата', '')}\n"
        f"{price_text}\n"
        "⏰ Свяжитесь с клиентом в течение 30 минут!\n\n"
        "✅ /accept — принять заявку\n"
        "🏁 /done — работы выполнены"
    )
    try:
        msg = await app.bot.send_message(chat_id=ADMIN_GROUP_ID, text=text)
        if MANAGER_ID:
            short = (
                f"🆕 Новая заявка!\n"
                f"👤 {data.get('имя', '—')} · {data.get('телефон', '—')}\n"
                f"🛠 {data.get('услуга', '—')}\n"
                f"📅 {data.get('дата', '—')}"
            )
            try:
                await app.bot.send_message(chat_id=MANAGER_ID, text=short)
            except Exception as me:
                logger.error(f"Ошибка личного уведомления менеджера: {me}")
        return msg.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки в группу: {e}")
        return None

async def cmd_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение с заявкой командой /accept")
        return
    replied_id = update.message.reply_to_message.message_id
    order = get_order_by_message_id(replied_id)
    if not order:
        await update.message.reply_text("Заявка не найдена.")
        return
    user_id = order[1]
    name = order[2]
    service = order[4]
    date = order[6]
    # обновить статус
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET status='in_progress' WHERE admin_message_id=?", (replied_id,))
    conn.commit()
    conn.close()
    try:
        msg_text = (
            f"Здравствуйте, {name}! 🏢\n\n"
            f"Ваша заявка на {service} принята в работу!\n"
            f"Дата и время: {date}\n\n"
            "Наш менеджер скоро свяжется с вами для уточнения деталей.\n"
            "С уважением, ООО ВИД"
        )
        await context.bot.send_message(chat_id=user_id, text=msg_text)
        save_message(user_id, "ООО ВИД", "out", msg_text)
        await update.message.reply_text(f"Клиент {name} уведомлён о принятии заявки!")
    except Exception as e:
        logger.error(f"Ошибка уведомления клиента: {e}")
        await update.message.reply_text("Ошибка при отправке уведомления клиенту.")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение с заявкой командой /done")
        return
    replied_id = update.message.reply_to_message.message_id
    order = get_order_by_message_id(replied_id)
    if not order:
        await update.message.reply_text("Заявка не найдена.")
        return
    order_id = order[0]
    user_id = order[1]
    name = order[2]
    service = order[4]
    # обновить статус
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()

    async def send_review_request():
        await asyncio.sleep(3600)
        try:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐", callback_data=f"rate_{order_id}_1"),
                    InlineKeyboardButton("⭐⭐", callback_data=f"rate_{order_id}_2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate_{order_id}_3"),
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rate_{order_id}_4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate_{order_id}_5"),
                ]
            ])
            msg_text = (
                f"Здравствуйте, {name}! 😊\n\n"
                f"Рады сообщить, что работы по объекту ({service}) завершены!\n\n"
                "Пожалуйста, оцените качество наших услуг:"
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=msg_text,
                reply_markup=keyboard
            )
            save_message(user_id, "ООО ВИД", "out", msg_text)
        except Exception as e:
            logger.error(f"Ошибка отправки запроса оценки: {e}")

    asyncio.create_task(send_review_request())
    await update.message.reply_text(f"Работы для {name} отмечены как выполненные. Через час клиент получит запрос оценки!")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    orders = get_today_orders()
    if not orders:
        await update.message.reply_text("📋 Сегодня заявок нет.")
        return
    text = f"📋 ЗАЯВКИ ЗА СЕГОДНЯ ({datetime.now().strftime('%d.%m.%Y')})\n"
    text += f"Всего: {len(orders)}\n\n"
    for i, order in enumerate(orders, 1):
        order_id, name, phone, service, address, date, rating = order
        stars = f"⭐{rating}/5" if rating else "—"
        text += (
            f"{i}. #{order_id} {name}\n"
            f"   📞 {phone}\n"
            f"   🛠 {service}\n"
            f"   🏠 {address}\n"
            f"   📅 {date}\n"
            f"   ⭐ Оценка: {stars}\n\n"
        )
    await update.message.reply_text(text)

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    order_id = int(parts[1])
    rating = int(parts[2])
    save_rating(order_id, rating)
    stars = "⭐" * rating
    if rating >= 4:
        response = f"Спасибо за оценку {stars}!\n\nРады что вы довольны результатом! Будем рады видеть вас снова. С уважением, ООО ВИД 🏢"
    elif rating == 3:
        response = f"Спасибо за оценку {stars}!\n\nМы постоянно улучшаем качество услуг. Если есть пожелания — напишите нам!"
    else:
        response = f"Спасибо за оценку {stars}!\n\nПриносим извинения за неудобства. Пожалуйста, опишите ситуацию — мы разберёмся и исправим!"
    await query.edit_message_text(response)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"⭐ Новая оценка!\nЗаявка #{order_id}\nОценка: {stars} ({rating}/5)"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки оценки в группу: {e}")

async def send_reminders(app):
    while True:
        await asyncio.sleep(3600)
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            reminder_from = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")
            reminder_to = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
            # Одно напоминание на клиента: только по его последней заявке
            c.execute("""
                SELECT id, user_id, name, service, created_at
                FROM orders
                WHERE reminder_sent = 0
                  AND created_at BETWEEN ? AND ?
                  AND id IN (SELECT MAX(id) FROM orders GROUP BY user_id)
            """, (reminder_from, reminder_to))
            rows = c.fetchall()
            for row in rows:
                order_id, user_id, name, service, _ = row
                # Все даты заказов клиента
                c.execute("SELECT created_at FROM orders WHERE user_id=? ORDER BY id ASC", (user_id,))
                all_dates_raw = [r[0] for r in c.fetchall()]
                order_count = len(all_dates_raw)
                try:
                    if order_count >= 3:
                        # Вычислить средний интервал между заказами
                        dates = []
                        for d in all_dates_raw:
                            try:
                                dates.append(datetime.fromisoformat(str(d)[:10]))
                            except Exception:
                                pass
                        if len(dates) >= 2:
                            intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                            avg_days = max(7, sum(intervals) // len(intervals))
                            next_date = dates[-1] + timedelta(days=avg_days)
                            next_date_str = next_date.strftime("%d.%m.%Y")
                            date_line = f"Судя по вашему графику, следующая уборка — около {next_date_str}.\n"
                        else:
                            date_line = f"Прошёл месяц с последней уборки ({service}).\n"
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ Записаться", callback_data="book_new")
                        ]])
                        msg_text = (
                            f"Здравствуйте, {name}! 👋\n\n"
                            f"Вы уже {order_count} раз доверяли нам уборку — спасибо за доверие! ⭐\n\n"
                            f"{date_line}"
                            "Забронировать заранее?\n\n"
                            "С уважением, ООО ВИД 🏢"
                        )
                        await app.bot.send_message(chat_id=user_id, text=msg_text, reply_markup=keyboard)
                    else:
                        msg_text = (
                            f"Здравствуйте, {name}! 👋\n\n"
                            f"Прошёл месяц с момента последней уборки ({service}).\n"
                            "Пора поддержать чистоту на объекте? 😊\n\n"
                            "Напишите нам — подберём удобное время и выгодные условия!\n"
                            "С уважением, ООО ВИД"
                        )
                        await app.bot.send_message(chat_id=user_id, text=msg_text)
                    save_message(user_id, "ООО ВИД", "out", msg_text)
                    c.execute("UPDATE orders SET reminder_sent=1 WHERE id=?", (order_id,))
                    conn.commit()
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания: {e}")
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка проверки напоминаний: {e}")

async def handle_book_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    conversations[user_id] = []
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=user_id,
        text="Отлично! Давайте оформим заявку. 🏢\nКакая услуга вас интересует на этот раз?"
    )


async def post_init(app):
    asyncio.create_task(send_reminders(app))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []

    # Обработка реферальной ссылки
    args = context.args
    if args and args[0].startswith('ref_'):
        try:
            referrer_id = int(args[0][4:])
            if referrer_id != user_id:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute(
                    "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                    (referrer_id, user_id)
                )
                conn.commit()
                conn.close()
        except (ValueError, Exception):
            pass

    bot_me = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{user_id}"

    await update.message.reply_text(
        "Добро пожаловать в ООО ВИД!\n"
        "Профессиональный клининг для бизнеса и предприятий 🏢\n\n"
        "Мы предлагаем:\n"
        "• Регулярная уборка офисов — от 25 руб/кв.м\n"
        "• Комплексная уборка помещений — от 45 руб/кв.м\n"
        "• Генеральная уборка — от 7000 руб.\n"
        "• Уборка после ремонта — от 7000 руб.\n"
        "• Мытьё окон и фасадов — от 80 руб/кв.м\n"
        "• Дезинфекция помещений — от 15 руб/кв.м\n"
        "• Уборка производств и складов — от 20 руб/кв.м\n"
        "• Химчистка мягкой мебели — от 400 руб\n\n"
        "Какая услуга вас интересует?\n\n"
        f"🎁 Ваша реферальная ссылка:\n{ref_link}\n"
        "Поделитесь с партнёрами — получите скидку 5% за каждого нового клиента."
    )

async def myref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_me = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{user_id}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"🔗 Ваша реферальная ссылка:\n{ref_link}\n\n"
        f"Приглашено клиентов: {count}\n"
        "За каждого нового клиента по вашей ссылке — скидка 5% на следующий заказ.\n"
        "Сообщите об этом менеджеру при оформлении заявки."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or str(user_id)
    user_text = update.message.text
    if user_id not in conversations:
        # Восстанавливаем историю из БД (последние 20 сообщений)
        conversations[user_id] = []
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT direction, text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (user_id,)
        )
        rows = c.fetchall()
        conn.close()
        for direction, text in reversed(rows):
            role = "user" if direction == "in" else "assistant"
            conversations[user_id].append({"role": role, "content": text})

    # сохранить входящее сообщение
    save_message(user_id, user_name, "in", user_text)

    loyal = is_loyal_client(user_id)
    loyal_system = "ПОСТОЯННЫЙ_КЛИЕНТ=ДА — применяй скидку 10% и сообщи об этом клиенту." if loyal else "ПОСТОЯННЫЙ_КЛИЕНТ=НЕТ"

    conversations[user_id].append({"role": "user", "content": user_text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + f"\n\nСТАТУС КЛИЕНТА: {loyal_system}"}
        ] + conversations[user_id]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1024
        )
        reply = response.choices[0].message.content
        conversations[user_id].append({"role": "assistant", "content": reply})
        data = parse_order(reply, user_id)

        # Резервное извлечение: если ответ похож на подтверждение, но маркер отсутствует
        confirmation_keywords = (
            "перезвонит", "заказ", "заявка принята", "подтвердим", "ждите",
            "менеджер свяжется", "свяжемся", "принята", "оформлена", "оформили",
            "получили", "зарегистрирована", "в течение 30", "подтверждаем",
            "в работу", "принято", "записали", "зафиксировали"
        )
        long_conversation = len(conversations.get(user_id, [])) >= 10
        if data is None and (long_conversation or any(kw in reply.lower() for kw in confirmation_keywords)):
            try:
                extract_messages = messages + [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": (
                        "Извлеки из нашего разговора данные и выдай ТОЛЬКО одну строку строго в формате:\n"
                        "ЗАЯВКА_ПРИНЯТА: имя=[имя], телефон=[телефон], услуга=[услуга], адрес=[адрес], дата=[дата]\n"
                        "Никакого другого текста."
                    )}
                ]
                extract_resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=extract_messages,
                    max_tokens=150
                )
                extract_text = extract_resp.choices[0].message.content
                data = parse_order(extract_text, user_id)
                if data:
                    logger.info("Заявка извлечена резервным методом")
            except Exception as ex:
                logger.error(f"Ошибка резервного извлечения: {ex}")

        # Сохранять заявку только если есть реальные имя и телефон (телефон должен содержать цифры)
        phone_val = data.get("телефон", "") if data else ""
        phone_has_digits = bool(re.search(r'\d{5,}', str(phone_val)))
        name_val = data.get("имя", "") if data else ""
        name_ok = bool(name_val) and name_val not in ("None", "", "[не указан]", "не указан")
        if data and name_ok and phone_has_digits:
            # Извлечь цену из данных заявки
            price_val = None
            price_str = data.get("цена", "")
            if price_str:
                m = re.search(r'\d[\d\s]*', str(price_str))
                if m:
                    try:
                        price_val = float(m.group().replace(" ", ""))
                    except ValueError:
                        pass
            admin_msg_id = await notify_admin(context.application, data, loyal=loyal)
            save_order(
                user_id,
                data.get("имя", ""),
                data.get("телефон", ""),
                data.get("услуга", ""),
                data.get("адрес", ""),
                data.get("дата", ""),
                admin_msg_id,
                price_val,
            )
            # Уведомить реферера при первом заказе реферала
            ref_conn = sqlite3.connect(DB_PATH)
            ref_c = ref_conn.cursor()
            ref_c.execute(
                "SELECT referrer_id FROM referrals WHERE referred_id = ? AND notified = 0",
                (user_id,)
            )
            ref_row = ref_c.fetchone()
            if ref_row:
                referrer_id = ref_row[0]
                ref_c.execute("UPDATE referrals SET notified = 1 WHERE referred_id = ?", (user_id,))
                ref_conn.commit()
                ref_conn.close()
                referred_name = data.get("имя", "Новый клиент")
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"По вашей реферальной ссылке оформил заявку клиент {referred_name}!\n\n"
                            "Вы получаете скидку 5% на следующую уборку.\n"
                            "Сообщите об этом менеджеру при следующем заказе."
                        )
                    )
                except Exception as ref_err:
                    logger.error(f"Ошибка уведомления реферера: {ref_err}")
            else:
                ref_conn.close()
        clean_reply = reply.split("ЗАЯВКА_ПРИНЯТА:")[0].strip()
        clean_reply = clean_text(clean_reply)
        # Фильтр галлюцинаций: если LLM упомянул несуществующий сайт/кабинет — вырезаем предложения
        hallucination_markers = (
            "наш сайт", "нашем сайте", "на сайте", "на нашем сайт",
            "личный кабинет", "личном кабинете", "в личном кабинет",
            "зарегистрируйтесь", "авторизуйтесь", "войдите на сайт",
            "электронную почту", "электронной почте", "по электронной",
            "позвоните нам", "наш номер телефона", "по телефону",
        )
        if any(m in clean_reply.lower() for m in hallucination_markers):
            sentences = re.split(r'(?<=[.!?])\s+', clean_reply)
            clean_sentences = [s for s in sentences if not any(m in s.lower() for m in hallucination_markers)]
            clean_reply = " ".join(clean_sentences).strip()
            if not clean_reply:
                clean_reply = "Для оформления заявки или получения информации — напишите мне здесь, в боте."
        # Перехват на ответ: если LLM отказался отвечать про реферальную программу или запутался
        referral_denial = (
            "нет информации о реферальн", "не знаю о реферальн",
            "не могу предоставить информацию о реферальн",
            "не является одной из наших услуг",
            "моя основная функция", "моя основная задача",
            "не входит в мои функции", "не могу помочь с реферальн",
        )
        if any(m in clean_reply.lower() for m in referral_denial):
            bot_me = await context.bot.get_me()
            ref_link_hint = f"https://t.me/{bot_me.username}?start=ref_{user_id}"
            clean_reply = (
                "Реферальная программа работает прямо здесь, в боте.\n\n"
                "Напишите команду /myref — и получите вашу персональную ссылку.\n\n"
                f"Или вот она прямо сейчас:\n{ref_link_hint}\n\n"
                "За каждого нового клиента по вашей ссылке — скидка 5% на следующую уборку."
            )
        # Ночное уведомление — только первый раз за сессию
        if is_night_hours() and user_id not in night_notified:
            clean_reply += "\n\n🌙 Ваш запрос принят. Менеджер ответит с 9:00."
            night_notified.add(user_id)
        # сохранить исходящее сообщение
        save_message(user_id, "ООО ВИД", "out", clean_reply)
        await update.message.reply_text(clean_reply)
    except Exception as e:
        logger.error(f"Oshibka: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")

async def handle_photo(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or str(user_id)
    photo = update.message.photo[-1]  # наибольшее разрешение
    file_id = photo.file_id
    caption = update.message.caption or ""
    save_message(user_id, user_name, "in", f"[photo:{file_id}]")
    if caption:
        save_message(user_id, user_name, "in", caption)
    reply = "Фото получено! 📸 Менеджер рассмотрит объект и свяжется с вами."
    save_message(user_id, "ООО ВИД", "out", reply)
    await update.message.reply_text(reply)


async def handle_referral_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or str(user_id)
    user_text = update.message.text or ""
    save_message(user_id, user_name, "in", user_text)
    bot_me = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{user_id}"
    reply = (
        "Реферальная программа работает прямо здесь, в боте.\n\n"
        f"Ваша реферальная ссылка:\n{ref_link}\n\n"
        "За каждого нового клиента по вашей ссылке — скидка 5% на следующую уборку.\n"
        "Или напишите /myref в любой момент, чтобы получить ссылку снова."
    )
    if user_id not in conversations:
        conversations[user_id] = []
    conversations[user_id].append({"role": "user", "content": user_text})
    conversations[user_id].append({"role": "assistant", "content": reply})
    save_message(user_id, "ООО ВИД", "out", reply)
    await update.message.reply_text(reply)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("Диалог сброшен. Какая услуга вас интересует?")

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("myref", myref))
    app.add_handler(CommandHandler("accept", cmd_accept))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CallbackQueryHandler(handle_book_new, pattern=r"^book_new$"))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'(?i)реферал'),
        handle_referral_question
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("ООО ВИД бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
