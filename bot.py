import asyncio
import random
import sqlite3
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = "8477161043:AAEmtwhIKd5wiYzQ0W5r8cuVyCx_t-FJuiM"  # 🔹 Вставь сюда токен своего бота
ADMIN_ID = 5394084759            # 🔹 Вставь сюда свой Telegram ID

# --- База данных ---
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    coins INTEGER DEFAULT 0,
    last_roll INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    rarity TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS user_cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    car_id INTEGER
)
""")
conn.commit()

# --- Настройки ---
ROLL_COOLDOWN = 2 * 60 * 60  # 2 часа
RARITY_CHANCES = {
    "Common": 70,
    "Rare": 20,
    "Epic": 8,
    "Legendary": 2
}

RARITY_EMOJIS = {
    "Common": "⚪️",
    "Rare": "🟢",
    "Epic": "🔵",
    "Legendary": "🟣"
}

# --- Инициализация бота ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Вспомогательные функции ---
def get_or_create_user(user_id, username):
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()

def get_random_car():
    rarity = random.choices(list(RARITY_CHANCES.keys()), weights=RARITY_CHANCES.values())[0]
    cur.execute("SELECT * FROM cars WHERE rarity = ?", (rarity,))
    cars = cur.fetchall()
    if not cars:
        return None
    return random.choice(cars)

def add_car_to_user(user_id, car_id):
    cur.execute("INSERT INTO user_cars (user_id, car_id) VALUES (?, ?)", (user_id, car_id))
    conn.commit()

# --- Команды ---
@dp.message(Command("start"))
async def start_cmd(message: Message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"🚗 Добро пожаловать в CAR CARD!\n\n"
        f"Собирай машины разных редкостей и соревнуйся с другими!\n\n"
        f"Команды:\n"
        f"/roll — выбить новую машину (раз в 2 часа)\n"
        f"/garage — посмотреть свои машины\n"
        f"/top — топ игроков\n"
        f"/profile — твой профиль"
    )

@dp.message(Command("roll"))
async def roll_cmd(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Без ника"
    get_or_create_user(user_id, username)

    cur.execute("SELECT last_roll FROM users WHERE user_id = ?", (user_id,))
    last_roll = cur.fetchone()[0]
    now = int(time.time())

    if now - last_roll < ROLL_COOLDOWN:
        remaining = ROLL_COOLDOWN - (now - last_roll)
        h, m = divmod(remaining // 60, 60)
        await message.answer(f"⏳ Ещё нельзя! Попробуй через {h}ч {m}м.")
        return

    car = get_random_car()
    if not car:
        await message.answer("❌ Нет машин в базе! (добавь через админку)")
        return

    car_id, name, rarity = car
    add_car_to_user(user_id, car_id)
    cur.execute("UPDATE users SET last_roll = ? WHERE user_id = ?", (now, user_id))
    conn.commit()

    emoji = RARITY_EMOJIS.get(rarity, "⚪️")
    await message.answer(f"🎉 {emoji} Ты выбил: *{name}* ({rarity})", parse_mode="Markdown")

@dp.message(Command("garage"))
async def garage_cmd(message: Message):
    user_id = message.from_user.id
    cur.execute("""
        SELECT cars.name, cars.rarity FROM user_cars
        JOIN cars ON user_cars.car_id = cars.id
        WHERE user_cars.user_id = ?
    """, (user_id,))
    cars = cur.fetchall()

    if not cars:
        await message.answer("🚗 У тебя пока нет машин!")
        return

    text = "🧰 Твой гараж:\n\n"
    for name, rarity in cars:
        emoji = RARITY_EMOJIS.get(rarity, "⚪️")
        text += f"{emoji} {name} ({rarity})\n"

    await message.answer(text)

@dp.message(Command("top"))
async def top_cmd(message: Message):
    cur.execute("""
        SELECT users.username, COUNT(user_cars.id) as count
        FROM users
        LEFT JOIN user_cars ON users.user_id = user_cars.user_id
        GROUP BY users.user_id
        ORDER BY count DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    text = "🏆 Топ коллекционеров:\n\n"
    for i, (username, count) in enumerate(rows, start=1):
        text += f"{i}. @{username or 'Без ника'} — {count} машин\n"

    await message.answer(text)

@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    user_id = message.from_user.id
    cur.execute("SELECT username, coins FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        await message.answer("Ты ещё не зарегистрирован! Напиши /start")
        return

    username, coins = user
    cur.execute("SELECT COUNT(*) FROM user_cars WHERE user_id = ?", (user_id,))
    cars_count = cur.fetchone()[0]

    await message.answer(
        f"👤 Профиль @{username}\n"
        f"🚘 Машин: {cars_count}\n"
        f"💰 Монет: {coins}"
    )

# --- Админка (скрытая) ---
@dp.message(Command("add_car"))
async def add_car_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, name, rarity = message.text.split(maxsplit=2)
        cur.execute("INSERT INTO cars (name, rarity) VALUES (?, ?)", (name, rarity))
        conn.commit()
        await message.answer(f"✅ Машина '{name}' ({rarity}) добавлена.")
    except Exception as e:
        await message.answer(f"⚠ Ошибка: {e}")

@dp.message(Command("reset_user"))
async def reset_user_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid = message.text.split(maxsplit=1)
        cur.execute("DELETE FROM user_cars WHERE user_id = ?", (uid,))
        conn.commit()
        await message.answer(f"♻️ Пользователь {uid} сброшен.")
    except Exception as e:
        await message.answer(f"⚠ Ошибка: {e}")

# --- Запуск ---
async def main():
    print("🚀 Бот CAR CARD запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
