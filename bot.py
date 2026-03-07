import logging
import random
import sqlite3
import time
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

ROLL_COOLDOWN = 14400

RARITY_NAME = {
1: "Common",
2: "Rare",
3: "Epic",
4: "Legendary",
5: "Secret"
}

# ---------- РЕДКОСТЬ ----------

def get_random_rarity():

    roll = random.randint(1,1000)

    if roll <= 700:
        return 1
    elif roll <= 900:
        return 2
    elif roll <= 980:
        return 3
    elif roll <= 998:
        return 4
    else:
        return 5
# ---------- START ----------

@dp.message(Command("start"))
async def start(message: types.Message):

    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute(
        "INSERT OR IGNORE INTO users(id,name,last_roll) VALUES(?,?,?)",
        (user_id,name,0)
    )

    conn.commit()

    await message.answer("🏎 Добро пожаловать!\n\nИспользуй /roll чтобы выбить машину")

# ---------- ROLL ----------

@dp.message(Command("roll"))
async def roll(message: types.Message):

    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute(
        "INSERT OR IGNORE INTO users(id,name,last_roll) VALUES(?,?,?)",
        (user_id,name,0)
    )

    cursor.execute(
        "SELECT last_roll FROM users WHERE id=?",
        (user_id,)
    )

    last_roll = cursor.fetchone()[0]

    now = int(time.time())

    if now - last_roll < ROLL_COOLDOWN:

        left = ROLL_COOLDOWN - (now-last_roll)
        hours = left//3600
        minutes = (left%3600)//60

        await message.answer(
            f"⏳ Следующий roll через {hours}ч {minutes}м"
        )
        return

    rarity = get_random_rarity()

    cursor.execute(
        "SELECT * FROM cars WHERE rarity=? ORDER BY RANDOM() LIMIT 1",
        (rarity,)
    )

    car = cursor.fetchone()

    if not car:
        cursor.execute("SELECT * FROM cars ORDER BY RANDOM() LIMIT 1")
        car = cursor.fetchone()

    if not car:
        await message.answer("🚫 В базе нет машин")
        return

    car_id,name_car,desc,rarity,pts,photo = car

    cursor.execute(
        "INSERT INTO collection(user_id,car_id) VALUES(?,?)",
        (user_id,car_id)
    )

    cursor.execute(
        "UPDATE users SET last_roll=? WHERE id=?",
        (now,user_id)
    )

    conn.commit()

    text = f"""
🎰 ТЫ ВЫБИЛ МАШИНУ

🏎 {name_car}

✨ {RARITY_NAME[rarity]}
⭐ +{pts} pts

{desc}
"""

    await message.answer_photo(photo,caption=text)

# ---------- PROFILE ----------

@dp.message(Command("profile"))
async def profile(message: types.Message):

    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute(
        "SELECT COUNT(*) FROM collection WHERE user_id=?",
        (user_id,)
    )

    total = cursor.fetchone()[0]

    cursor.execute("""
    SELECT SUM(cars.pts)
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    WHERE user_id=?
    """,(user_id,))

    pts = cursor.fetchone()[0]

    if pts is None:
        pts = 0

    photos = await bot.get_user_profile_photos(user_id, limit=1)

    text = f"""
👤 {name}

🚗 Машин: {total}
⭐ Очки: {pts}

💰 Скоро появится магазин для траты очков
"""

    if photos.total_count > 0:

        photo_id = photos.photos[0][-1].file_id

        await message.answer_photo(photo_id, caption=text)

    else:

        await message.answer(text)

# ---------- ГАРАЖ ----------

@dp.message(Command("garage"))
async def garage(message: types.Message):

    user_id = message.from_user.id

    cursor.execute("""
    SELECT cars.name,cars.rarity
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    WHERE user_id=?
    ORDER BY rowid DESC
    LIMIT 15
    """,(user_id,))

    cars = cursor.fetchall()

    if not cars:
        await message.answer("🚗 Гараж пуст")
        return

    text = "🏎 Твой гараж\n\n"

    for name,rarity in cars:

        text += f"{name} — {RARITY_NAME[rarity]}\n"

    await message.answer(text)

# ---------- TOP LEGENDARY ----------

@dp.message(Command("top"))
async def top(message: types.Message):

    cursor.execute("""
    SELECT users.name, COUNT(*)
    FROM collection
    JOIN cars ON cars.id = collection.car_id
    JOIN users ON users.id = collection.user_id
    WHERE cars.rarity = 4
    GROUP BY collection.user_id
    ORDER BY COUNT(*) DESC
    LIMIT 5
    """)

    players = cursor.fetchall()

    if not players:
        await message.answer("🏆 Пока никто не выбил Legendary")
        return

    text = "🏆 Топ игроков по Legendary\n\n"

    place = 1
    for name,count in players:

        text += f"{place}. {name} — {count} 🏎\n"
        place += 1

    await message.answer(text)

# ---------- ADD CAR ----------

admin_state = {}

@dp.message(Command("add"))
async def add(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    admin_state[message.from_user.id] = "photo"

    await message.answer("📸 Отправь фото машины")

@dp.message()
async def add_process(message: types.Message):

    if message.from_user.id not in admin_state:
        return

    state = admin_state[message.from_user.id]

    if state == "photo":

        if not message.photo:
            await message.answer("Нужно отправить фото")
            return

        photo = message.photo[-1].file_id

        admin_state[message.from_user.id] = {
            "photo":photo
        }

        await message.answer(
            "Теперь отправь:\n\nНазвание | Описание | Редкость | Очки"
        )

    else:

        data = message.text.split("|")

        if len(data) != 4:
            await message.answer("Неверный формат")
            return

        name = data[0].strip()
        desc = data[1].strip()
        rarity = int(data[2].strip())
        pts = int(data[3].strip())
        photo = admin_state[message.from_user.id]["photo"]

        cursor.execute("""
        INSERT INTO cars(name,description,rarity,pts,photo)
        VALUES(?,?,?,?,?)
        """,(name,desc,rarity,pts,photo))

        conn.commit()

        admin_state.pop(message.from_user.id)

        await message.answer("✅ Машина добавлена")

# ---------- ЗАПУСК ----------
@dp.message(Command("admin_reset"))
async def admin_reset(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    user_id = message.from_user.id

    cursor.execute(
        "DELETE FROM collection WHERE user_id=?",
        (user_id,)
    )

    cursor.execute(
        "UPDATE users SET last_roll=0 WHERE id=?",
        (user_id,)
    )

    conn.commit()

    await message.answer("🧹 Коллекция и КД очищены (только у админа)")
    
    
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

