import logging
import random
import sqlite3
import time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import asyncio

TOKEN = "8477161043:AAEmtwhIKd5wiYzQ0W5r8cuVyCx_t-FJuiM"
ADMIN_ID = 5394084759

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

conn = sqlite3.connect("cars_bot.db")
cursor = conn.cursor()


# ---------- БАЗА ----------

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
name TEXT,
last_roll INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cars(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
description TEXT,
rarity INTEGER,
pts INTEGER,
photo TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS collection(
user_id INTEGER,
car_id INTEGER
)
""")

conn.commit()


# ---------- НАСТРОЙКИ ----------

ROLL_COOLDOWN = 7200

CHANCES = {
    1: 70,
    2: 20,
    3: 8,
    4: 2
}

RARITY_NAME = {
    1: "Common",
    2: "Rare",
    3: "Epic",
    4: "Legendary"
}


# ---------- ФУНКЦИИ ----------

def get_random_rarity():
    roll = random.randint(1, 100)

    if roll <= 70:
        return 1
    elif roll <= 90:
        return 2
    elif roll <= 98:
        return 3
    else:
        return 4


# ---------- КОМАНДЫ ----------

@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute(
        "INSERT OR IGNORE INTO users (id,name) VALUES (?,?)",
        (user_id, name)
    )

    cursor.execute(
        "UPDATE users SET name=? WHERE id=?",
        (name, user_id)
    )

    conn.commit()

    await message.answer("🏎 Добро пожаловать в Cars Roll Bot!\n\nИспользуй /roll чтобы выбить машину")


# ---------- ROLL ----------

@dp.message(Command("roll"))
async def roll(message: Message):

    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute("SELECT last_roll FROM users WHERE id=?", (user_id,))
    data = cursor.fetchone()

    now = int(time.time())

    if data:
        last_roll = data[0]

        if now - last_roll < ROLL_COOLDOWN:

            left = ROLL_COOLDOWN - (now - last_roll)
            minutes = left // 60

            await message.answer(f"⏳ Подожди {minutes} мин до следующего roll")
            return

    rarity = get_random_rarity()

    cursor.execute(
        "SELECT * FROM cars WHERE rarity=? ORDER BY RANDOM() LIMIT 1",
        (rarity,)
    )

    car = cursor.fetchone()

    if not car:
        cursor.execute(
            "SELECT * FROM cars ORDER BY RANDOM() LIMIT 1"
        )
        car = cursor.fetchone()

    car_id, name_car, desc, rarity, pts, photo = car

    cursor.execute(
        "INSERT INTO collection (user_id,car_id) VALUES (?,?)",
        (user_id, car_id)
    )

    cursor.execute(
        "UPDATE users SET last_roll=? WHERE id=?",
        (now, user_id)
    )

    conn.commit()

    text = f"""
🏎 Ты выбил машину!

{name_car}

✨ {RARITY_NAME[rarity]}
⭐ +{pts} pts

{desc}
"""

    await message.answer_photo(photo, caption=text)


# ---------- ПРОФИЛЬ ----------

@dp.message(Command("profile"))
async def profile(message: Message):

    user_id = message.from_user.id

    cursor.execute("""
    SELECT COUNT(*)
    FROM collection
    WHERE user_id=?
    """, (user_id,))

    total = cursor.fetchone()[0]

    cursor.execute("""
    SELECT SUM(cars.pts)
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    WHERE user_id=?
    """, (user_id,))

    pts = cursor.fetchone()[0]

    if pts is None:
        pts = 0

    await message.answer(
        f"""
👤 Профиль

Машин: {total}
Pts: {pts}
"""
    )


# ---------- ГАРАЖ ----------

@dp.message(Command("garage"))
async def garage(message: Message):

    user_id = message.from_user.id

    cursor.execute("""
    SELECT cars.name, cars.rarity
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    WHERE user_id=?
    ORDER BY rowid DESC
    LIMIT 15
    """, (user_id,))

    cars = cursor.fetchall()

    if not cars:
        await message.answer("🚗 Гараж пуст")
        return

    text = "🏎 Твой гараж:\n\n"

    for name, rarity in cars:
        text += f"{name} — {RARITY_NAME[rarity]}\n"

    await message.answer(text)


# ---------- ТОП ----------

@dp.message(Command("top"))
async def top(message: Message):

    cursor.execute("""
    SELECT users.name, COUNT(*)
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    JOIN users ON users.id = collection.user_id
    WHERE cars.rarity=4
    GROUP BY user_id
    ORDER BY COUNT(*) DESC
    LIMIT 5
    """)

    players = cursor.fetchall()

    if not players:
        await message.answer("Пока нет легендарок")
        return

    text = "🏆 Топ игроков по Legendary:\n\n"

    i = 1
    for name, count in players:
        text += f"{i}. {name} — {count}\n"
        i += 1

    await message.answer(text)


# ---------- ЗАПУСК ----------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

