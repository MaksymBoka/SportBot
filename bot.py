import logging
import sqlite3
import os
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# TOKEN береться з системних змінних — не вписуй його в код!
TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# Стани розмови
CHOOSING_SPORT, CHOOSING_GOAL, LOGGING_WORKOUT = range(3)

SPORTS = ["Біг", "Тренажерний зал", "Плавання", "Велосипед", "Йога", "Футбол"]
GOALS = ["Схуднути", "Набрати масу", "Витривалість", "Гнучкість", "Загальна форма"]

MOTIVATION = [
    "Кожне тренування — крок до кращої версії себе!",
    "Не зупиняйся. Біль тимчасовий, результат — назавжди.",
    "Сьогодні важко — завтра легше. Вперед!",
    "Твоє тіло може більше, ніж ти думаєш.",
    "Маленькі кроки щодня — великий результат за рік.",
    "Ти вже кращий за того, ким був вчора.",
    "Відпочинок — частина прогресу. Але сьогодні — час діяти!",
]

# ── База даних ──────────────────────────────────

def init_db():
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            sport TEXT,
            goal TEXT,
            total_workouts INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            description TEXT,
            duration INTEGER
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_user(user_id, username, sport, goal):
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO users (user_id, username, sport, goal, total_workouts)
        VALUES (?, ?, ?, ?, COALESCE((SELECT total_workouts FROM users WHERE user_id=?), 0))
    """, (user_id, username, sport, goal, user_id))
    conn.commit()
    conn.close()

def log_workout(user_id, description, duration):
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    from datetime import date
    c.execute(
        "INSERT INTO workouts (user_id, date, description, duration) VALUES (?, ?, ?, ?)",
        (user_id, str(date.today()), description, duration)
    )
    c.execute(
        "UPDATE users SET total_workouts = total_workouts + 1 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("""
        SELECT username, sport, total_workouts
        FROM users
        ORDER BY total_workouts DESC
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def get_my_stats(user_id):
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("SELECT total_workouts, sport, goal FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    c.execute("""
        SELECT date, description, duration FROM workouts
        WHERE user_id=? ORDER BY date DESC LIMIT 5
    """, (user_id,))
    recent = c.fetchall()
    conn.close()
    return row, recent

# ── Команди ─────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)
    if existing:
        await update.message.reply_text(
            f"З поверненням, {user.first_name}! Ти вже зареєстрований.\n\n"
            "Що робимо?\n"
            "/workout — записати тренування\n"
            "/stats — моя статистика\n"
            "/leaderboard — рейтинг\n"
            "/plan — мій план\n"
            "/motivation — заряд мотивації\n"
            "/settings — змінити вид спорту чи ціль"
        )
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(s, callback_data=f"sport_{s}")] for s in SPORTS]
    await update.message.reply_text(
        f"Привіт, {user.first_name}! Я твій спортивний помічник.\n\n"
        "Спочатку — оберемо твій вид спорту:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SPORT

async def choose_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sport = query.data.replace("sport_", "")
    context.user_data["sport"] = sport

    keyboard = [[InlineKeyboardButton(g, callback_data=f"goal_{g}")] for g in GOALS]
    await query.edit_message_text(
        f"Чудово! Ти обрав: {sport}\n\nТепер — яка твоя ціль?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_GOAL

async def choose_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    goal = query.data.replace("goal_", "")
    user = query.from_user
    sport = context.user_data.get("sport", "Невідомо")

    save_user(user.id, user.first_name, sport, goal)

    await query.edit_message_text(
        f"Відмінно! Твій профіль збережено:\n\n"
        f"Вид спорту: {sport}\n"
        f"Ціль: {goal}\n\n"
        "Тепер доступні команди:\n"
        "/workout — записати тренування\n"
        "/stats — моя статистика\n"
        "/leaderboard — рейтинг\n"
        "/plan — мій план\n"
        "/motivation — заряд мотивації"
    )
    return ConversationHandler.END

async def workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return ConversationHandler.END
    await update.message.reply_text(
        "Опиши своє тренування у форматі:\n\n"
        "<b>Опис | Тривалість у хвилинах</b>\n\n"
        "Наприклад: <code>Біг у парку | 45</code>",
        parse_mode="HTML"
    )
    return LOGGING_WORKOUT

async def workout_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        parts = text.split("|")
        description = parts[0].strip()
        duration = int(parts[1].strip())
        log_workout(update.effective_user.id, description, duration)

        import random
        quote = random.choice(MOTIVATION)
        await update.message.reply_text(
            f"Тренування записано!\n\n"
            f"Що зробив: {description}\n"
            f"Тривалість: {duration} хв\n\n"
            f"💬 {quote}"
        )
    except Exception:
        await update.message.reply_text(
            "Формат невірний. Спробуй так:\n<code>Біг | 30</code>",
            parse_mode="HTML"
        )
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    row, recent = get_my_stats(user_id)
    if not row:
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return

    total, sport, goal = row
    text = (
        f"Твоя статистика:\n\n"
        f"Вид спорту: {sport}\n"
        f"Ціль: {goal}\n"
        f"Всього тренувань: {total}\n\n"
    )
    if recent:
        text += "Останні тренування:\n"
        for date, desc, dur in recent:
            text += f"  {date} — {desc} ({dur} хв)\n"
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_leaderboard()
    if not rows:
        await update.message.reply_text("Ще ніхто не записав тренування. Будь першим!")
        return
    text = "Рейтинг — топ гравців:\n\n"
    medals = ["1", "2", "3"]
    for i, (name, sport, count) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        text += f"{prefix} {name} — {count} трен. ({sport})\n"
    await update.message.reply_text(text)

async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return

    sport = user[2]
    goal = user[3]

    plans = {
        "Схуднути": "Пн — кардіо 40 хв\nВт — відпочинок\nСр — інтервали 30 хв\nЧт — відпочинок\nПт — кардіо 45 хв\nСб — активна прогулянка\nНд — відпочинок",
        "Набрати масу": "Пн — груди + трицепс\nВт — спина + біцепс\nСр — відпочинок\nЧт — ноги\nПт — плечі + прес\nСб — кардіо легке\nНд — відпочинок",
        "Витривалість": "Пн — довга пробіжка\nВт — відпочинок\nСр — темпове тренування\nЧт — відпочинок\nПт — інтервали\nСб — довга дистанція\nНд — відпочинок",
        "Гнучкість": "Щодня 20-30 хв розтяжки\nПн/Ср/Пт — йога\nВт/Чт — динамічна розтяжка\nСб — пілатес\nНд — відпочинок",
        "Загальна форма": "Пн — силове\nВт — кардіо\nСр — відпочинок\nЧт — функціональне\nПт — кардіо + прес\nСб — активний відпочинок\nНд — відпочинок",
    }

    week_plan = plans.get(goal, "Тренуйся 3-4 рази на тиждень рівномірно.")
    await update.message.reply_text(
        f"Твій тижневий план:\n\n"
        f"Вид спорту: {sport}\n"
        f"Ціль: {goal}\n\n"
        f"{week_plan}"
    )

async def motivation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    quote = random.choice(MOTIVATION)
    await update.message.reply_text(f"Твій заряд на сьогодні:\n\n{quote}")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(s, callback_data=f"sport_{s}")] for s in SPORTS]
    await update.message.reply_text(
        "Оберемо новий вид спорту:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SPORT

# ── Щоденне нагадування ──────────────────────────

async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    import random
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, username FROM users")
    users = c.fetchall()
    conn.close()

    quote = random.choice(MOTIVATION)
    for user_id, name in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Доброго ранку, {name}!\n\n{quote}\n\nЗапиши тренування: /workout"
            )
        except Exception:
            pass

# ── Запуск ───────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("settings", settings),
        ],
        states={
            CHOOSING_SPORT: [CallbackQueryHandler(choose_sport, pattern="^sport_")],
            CHOOSING_GOAL: [CallbackQueryHandler(choose_goal, pattern="^goal_")],
        },
        fallbacks=[],
    )

    workout_handler = ConversationHandler(
        entry_points=[CommandHandler("workout", workout_start)],
        states={
            LOGGING_WORKOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, workout_log)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(workout_handler)
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("plan", plan))
    app.add_handler(CommandHandler("motivation", motivation))

    # Щоденне нагадування о 08:00
    app.job_queue.run_daily(daily_reminder, time=time(hour=8, minute=0))

    print("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
