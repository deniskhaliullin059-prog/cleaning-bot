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
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.db"))

SYSTEM_PROMPT = (
    "Ты оператор клининговой компании ООО ВИД — профессиональный клининг для бизнеса и предприятий в Перми. "
    "Мы обслуживаем коммерческие помещения: офисы, торговые площади, производственные комплексы, склады, медицинские учреждения и бизнес-центры. "
    "ПРАВИЛО №1 — АБСОЛЮТНОЕ: каждое слово в твоём ответе должно быть написано только русскими буквами. Перед отправкой ответа проверь — нет ли в нём латиницы, иероглифов или других нерусских символов. Если есть — замени на русский эквивалент. "
    "ПРАВИЛО №2 — ГРАММАТИКА: каждое предложение должно быть полным — с подлежащим, сказуемым и правильными падежными окончаниями. Перед отправкой проверь каждое предложение: есть ли в нём глагол? Правильны ли падежи? Не обрывается ли мысль на полуслове? Если предложение неполное — перепиши его. "
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
    "В конце сообщения на отдельной строке добавь: ЗАЯВКА_ПРИНЯТА: имя=[имя], телефон=[телефон], услуга=[услуга], адрес=[адрес], дата=[дата] "
    "ВАЖНО: в метке ЗАЯВКА_ПРИНЯТА пиши только данные без лишних слов! "
    "ВАЖНО: не пропускай шаги 5 и 6! Задавай строго по одному вопросу за раз."
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=GROQ_API_KEY)
conversations = {}

def clean_text(text):
    # Убираем только управляющие символы (кроме \n и \t), нормализуем пробелы
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
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
            status TEXT DEFAULT 'new'
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
    # миграция существующих таблиц
    migrations = [
        "admin_message_id INTEGER",
        "rating INTEGER DEFAULT NULL",
        "review_sent INTEGER DEFAULT 0",
        "status TEXT DEFAULT 'new'"
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

def save_order(user_id, name, phone, service, address, date, admin_message_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (user_id, name, phone, service, address, date, admin_message_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'new')",
        (user_id, name, phone, service, address, date, admin_message_id)
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
    text = (
        "🏢 НОВАЯ ЗАЯВКА — ООО ВИД\n\n"
        f"{loyal_text}"
        f"👤 Контактное лицо: {data.get('имя', '')}\n"
        f"📞 Телефон: {data.get('телефон', '')}\n"
        f"🏠 Адрес объекта: {data.get('адрес', '')}\n"
        f"🛠 Услуга: {data.get('услуга', '')}\n"
        f"📅 Дата и время: {data.get('дата', '')}\n\n"
        "⏰ Свяжитесь с клиентом в течение 30 минут!\n\n"
        "✅ /accept — принять заявку\n"
        "🏁 /done — работы выполнены"
    )
    try:
        msg = await app.bot.send_message(chat_id=ADMIN_GROUP_ID, text=text)
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
            reminder_date = datetime.now() - timedelta(days=30)
            c.execute(
                "SELECT id, user_id, name, service FROM orders WHERE reminder_sent=0 AND created_at <= ?",
                (reminder_date,)
            )
            rows = c.fetchall()
            for row in rows:
                order_id, user_id, name, service = row
                try:
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

async def post_init(app):
    asyncio.create_task(send_reminders(app))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
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
        "Какая услуга вас интересует?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        return
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or str(user_id)
    user_text = update.message.text
    if user_id not in conversations:
        conversations[user_id] = []

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
            model="mixtral-8x7b-32768",
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
                    model="mixtral-8x7b-32768",
                    messages=extract_messages,
                    max_tokens=150
                )
                extract_text = extract_resp.choices[0].message.content
                data = parse_order(extract_text, user_id)
                if data:
                    logger.info("Заявка извлечена резервным методом")
            except Exception as ex:
                logger.error(f"Ошибка резервного извлечения: {ex}")

        # Сохранять заявку только если есть хотя бы имя и телефон
        if data and data.get("имя") and data.get("телефон") and data.get("имя") != "None" and data.get("телефон") != "None":
            admin_msg_id = await notify_admin(context.application, data, loyal=loyal)
            save_order(
                user_id,
                data.get("имя", ""),
                data.get("телефон", ""),
                data.get("услуга", ""),
                data.get("адрес", ""),
                data.get("дата", ""),
                admin_msg_id
            )
        clean_reply = reply.split("ЗАЯВКА_ПРИНЯТА:")[0].strip()
        clean_reply = clean_text(clean_reply)
        # сохранить исходящее сообщение
        save_message(user_id, "ООО ВИД", "out", clean_reply)
        await update.message.reply_text(clean_reply)
    except Exception as e:
        logger.error(f"Oshibka: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте ещё раз.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("Диалог сброшен. Какая услуга вас интересует?")

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("accept", cmd_accept))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("ООО ВИД бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
