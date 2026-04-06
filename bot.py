import logging
import sqlite3
import os
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

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
    from datetime import date
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO workouts (user_id, date, description, duration) VALUES (?, ?, ?, ?)",
        (user_id, str(date.today()), description, duration)
    )
    c.execute("UPDATE users SET total_workouts = total_workouts + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("SELECT username, sport, total_workouts FROM users ORDER BY total_workouts DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return rows

def get_my_stats(user_id):
    conn = sqlite3.connect("sport_bot.db")
    c = conn.cursor()
    c.execute("SELECT total_workouts, sport, goal FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    c.execute("SELECT date, description, duration FROM workouts WHERE user_id=? ORDER BY date DESC LIMIT 5", (user_id,))
    recent = c.fetchall()
    conn.close()
    return row, recent

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)
    if existing:
        await update.message.reply_text(
            f"З поверненням, {user.first_name}!\n\n"
            "/workout — записати тренування\n"
            "/stats — моя статистика\n"
            "/leaderboard — рейтинг\n"
            "/plan — мій план\n"
            "/motivation — мотивація\n"
            "/settings — змінити налаштування"
        )
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(s, callback_data=f"sport_{s}")] for s in SPORTS]
    await update.message.reply_text(
        f"Привіт, {user.first_name}! Я твій спортивний помічник.\n\nОбери вид спорту:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SPORT

async def choose_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sport = query.data.replace("sport_", "")
    context.user_data["sport"] = sport
    keyboard = [[InlineKeyboardButton(g, callback_data=f"goal_{g}")] for g in GOALS]
    await query.edit_message_text(f"Обрав: {sport}\n\nТепер вибери ціль:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_GOAL

async def choose_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    goal = query.data.replace("goal_", "")
    user = query.from_user
    sport = context.user_data.get("sport", "")
    save_user(user.id, user.first_name, sport, goal)
    await query.edit_message_text(
        f"Профіль збережено!\n\nСпорт: {sport}\nЦіль: {goal}\n\n"
        "/workout — записати тренування\n/stats — статистика\n/leaderboard — рейтинг\n/plan — план\n/motivation — мотивація"
    )
    return ConversationHandler.END

async def workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return ConversationHandler.END
    await update.message.reply_text(
        "Опиши тренування у форматі:\n\n<b>Опис | Хвилини</b>\n\nНаприклад: <code>Біг у парку | 45</code>",
        parse_mode="HTML"
    )
    return LOGGING_WORKOUT

async def workout_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    try:
        parts = update.message.text.split("|")
        description = parts[0].strip()
        duration = int(parts[1].strip())
        log_workout(update.effective_user.id, description, duration)
        await update.message.reply_text(f"Записано!\n\n{description} — {duration} хв\n\n{random.choice(MOTIVATION)}")
    except Exception:
        await update.message.reply_text("Невірний формат. Спробуй: <code>Біг | 30</code>", parse_mode="HTML")
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, recent = get_my_stats(update.effective_user.id)
    if not row:
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return
    total, sport, goal = row
    text = f"Статистика:\n\nСпорт: {sport}\nЦіль: {goal}\nТренувань: {total}\n"
    if recent:
        text += "\nОстанні:\n"
        for d, desc, dur in recent:
            text += f"  {d} — {desc} ({dur} хв)\n"
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_leaderboard()
    if not rows:
        await update.message.reply_text("Ще ніхто не тренувався. Будь першим!")
        return
    text = "Рейтинг:\n\n"
    for i, (name, sport, count) in enumerate(rows):
        text += f"{i+1}. {name} — {count} трен. ({sport})\n"
    await update.message.reply_text(text)

async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Спочатку зареєструйся: /start")
        return
    sport, goal = user[2], user[3]
    plans = {
        "Схуднути": "Пн — кардіо 40 хв\nВт — відпочинок\nСр — інтервали 30 хв\nЧт — відпочинок\nПт — кардіо 45 хв\nСб — прогулянка\nНд — відпочинок",
        "Набрати масу": "Пн — груди + трицепс\nВт — спина + біцепс\nСр — відпочинок\nЧт — ноги\nПт — плечі + прес\nСб — кардіо\nНд — відпочинок",
        "Витривалість": "Пн — довга пробіжка\nВт — відпочинок\nСр — темпове\nЧт — відпочинок\nПт — інтервали\nСб — довга дистанція\nНд — відпочинок",
        "Гнучкість": "Пн/Ср/Пт — йога 30 хв\nВт/Чт — розтяжка\nСб — пілатес\nНд — відпочинок",
        "Загальна форма": "Пн — силове\nВт — кардіо\nСр — відпочинок\nЧт — функціональне\nПт — кардіо + прес\nСб — активний відпочинок\nНд — відпочинок",
    }
    await update.message.reply_text(f"Твій план:\n\nСпорт: {sport}\nЦіль: {goal}\n\n{plans.get(goal, 'Тренуйся 3-4 рази на тиждень.')}")

async def motivation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    await update.message.reply_text(random.choice(MOTIVATION))

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(s, callback_data=f"sport_{s}")] for s in SPORTS]
    await update.message.reply_text("Обери новий вид спорту:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_SPORT

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
            await context.bot.send_message(chat_id=user_id, text=f"Доброго ранку, {name}!\n\n{quote}\n\n/workout — записати тренування")
        except Exception:
            pass

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("settings", settings)],
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

    app.job_queue.run_daily(daily_reminder, time=time(hour=6, minute=0))

    print("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
