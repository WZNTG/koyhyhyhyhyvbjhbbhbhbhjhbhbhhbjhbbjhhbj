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

# ---------------- DATABASE ----------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
name TEXT,
last_roll INTEGER DEFAULT 0,
last_daily INTEGER DEFAULT 0,
pts INTEGER DEFAULT 0
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

# ---------------- SETTINGS ----------------

ROLL_COOLDOWN = 14400
DAILY_COOLDOWN = 86400

RARITY_NAME = {
1: "⚪ Common",
2: "🔵 Rare",
3: "🟣 Epic",
4: "🟡 Legendary",
5: "💎 Secret"
}

DUPLICATE_PTS = {
1:1,
2:2,
3:4,
4:10,
5:25
}

# ---------------- COMMAND LIST ----------------

async def set_commands():
    commands = [
        types.BotCommand(command="roll", description="Выбить машину"),
        types.BotCommand(command="profile", description="Твой профиль"),
        types.BotCommand(command="garage", description="Твой гараж"),
        types.BotCommand(command="collection", description="Коллекция машин"),
        types.BotCommand(command="daily", description="Ежедневный бонус"),
        types.BotCommand(command="top", description="Топ по Legendary"),
        types.BotCommand(command="top_pts", description="Топ по очкам"),
        types.BotCommand(command="shop", description="Магазин"),
        types.BotCommand(command="roulette", description="Казино рулетка"),
        types.BotCommand(command="car", description="Посмотреть машину")
    ]

    await bot.set_my_commands(commands)

# ---------------- RARITY ----------------

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

# ---------------- START ----------------

@dp.message(Command("start"))
async def start(message: types.Message):

    user_id = message.from_user.id
    name = message.from_user.first_name

    cursor.execute(
        "INSERT OR IGNORE INTO users(id,name) VALUES(?,?)",
        (user_id,name)
    )

    conn.commit()

    await message.answer("🚗 Добро пожаловать в Car Collection!\n\nИспользуй /roll")

# ---------------- ROLL ----------------

@dp.message(Command("roll"))
async def roll(message: types.Message):

    user_id = message.from_user.id

    cursor.execute("SELECT last_roll FROM users WHERE id=?", (user_id,))
    last = cursor.fetchone()[0]

    now = int(time.time())

    if now-last < ROLL_COOLDOWN:

        left = ROLL_COOLDOWN-(now-last)
        h = left//3600
        m = (left%3600)//60

        await message.answer(f"⏳ Следующий roll через {h}ч {m}м")
        return

    # animation
    msg = await message.answer("🎰 Крутим...")
    await asyncio.sleep(0.6)
    await msg.edit_text("🎰 Крутим...\n⚪")
    await asyncio.sleep(0.6)
    await msg.edit_text("🎰 Крутим...\n⚪🔵")
    await asyncio.sleep(0.6)
    await msg.edit_text("🎰 Крутим...\n⚪🔵🟣")
    await asyncio.sleep(0.6)
    await msg.edit_text("🎰 Крутим...\n⚪🔵🟣🟡")

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

    car_id,name,desc,rarity,pts,photo = car

    cursor.execute(
        "SELECT * FROM collection WHERE user_id=? AND car_id=?",
        (user_id,car_id)
    )

    have = cursor.fetchone()

    if have:

        bonus = DUPLICATE_PTS[rarity]

        cursor.execute(
            "UPDATE users SET pts = pts + ? WHERE id=?",
            (bonus,user_id)
        )

        conn.commit()

        await message.answer(
            f"♻️ Дубликат!\n\n+{bonus} pts"
        )

    else:

        cursor.execute(
            "INSERT INTO collection VALUES(?,?)",
            (user_id,car_id)
        )

        conn.commit()

        if rarity == 5:
            title="💎💎💎 SECRET DROP 💎💎💎"
        elif rarity == 4:
            title="🟡 ЛЕГЕНДАРНАЯ МАШИНА!"
        elif rarity == 3:
            title="🟣 ЭПИЧЕСКАЯ МАШИНА!"
        else:
            title="🎉 Новая машина!"

        text=f"""
{title}

🏎 {name}

{RARITY_NAME[rarity]}
⭐ {pts} pts

{desc}
"""

        await message.answer_photo(photo,caption=text)

    cursor.execute(
        "UPDATE users SET last_roll=? WHERE id=?",
        (now,user_id)
    )

    conn.commit()

# ---------------- PROFILE ----------------

@dp.message(Command("profile"))
async def profile(message: types.Message):

    user_id=message.from_user.id

    cursor.execute("SELECT pts FROM users WHERE id=?", (user_id,))
    pts=cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM collection WHERE user_id=?",
        (user_id,)
    )

    total=cursor.fetchone()[0]

    photos = await bot.get_user_profile_photos(user_id,limit=1)

    text=f"""
👤 {message.from_user.first_name}

🚗 Машин: {total}
⭐ Очки: {pts}

💰 Скоро трата
"""

    if photos.total_count>0:

        photo=photos.photos[0][-1].file_id
        await message.answer_photo(photo,caption=text)

    else:
        await message.answer(text)

# ---------------- GARAGE ----------------

@dp.message(Command("garage"))
async def garage(message: types.Message):

    user_id=message.from_user.id

    cursor.execute("""
    SELECT cars.name,cars.rarity
    FROM collection
    JOIN cars ON cars.id=collection.car_id
    WHERE user_id=?
    """,(user_id,))

    cars=cursor.fetchall()

    if not cars:
        await message.answer("🚗 Гараж пуст")
        return

    text="🏎 Твой гараж\n\n"

    i=1
    for name,rarity in cars:

        text+=f"{i}. {name} — {RARITY_NAME[rarity]}\n"
        i+=1

    await message.answer(text)

# ---------------- COLLECTION ----------------

@dp.message(Command("collection"))
async def collection(message: types.Message):

    user_id=message.from_user.id

    cursor.execute("SELECT id,name FROM cars")
    all_cars=cursor.fetchall()

    cursor.execute(
        "SELECT car_id FROM collection WHERE user_id=?",
        (user_id,)
    )

    owned=[x[0] for x in cursor.fetchall()]

    text="📖 Коллекция\n\n"

    owned_count=0

    for car_id,name in all_cars:

        if car_id in owned:

            text+=f"✅ {name}\n"
            owned_count+=1

        else:

            text+=f"❌ {name}\n"

    text=f"📖 Коллекция ({owned_count}/{len(all_cars)})\n\n"+text

    await message.answer(text)

# ---------------- DAILY ----------------

@dp.message(Command("daily"))
async def daily(message: types.Message):

    user_id=message.from_user.id

    cursor.execute("SELECT last_daily FROM users WHERE id=?", (user_id,))
    last=cursor.fetchone()[0]

    now=int(time.time())

    if now-last < DAILY_COOLDOWN:

        await message.answer("⏳ Уже получено")
        return

    cursor.execute(
        "UPDATE users SET pts=pts+5,last_daily=? WHERE id=?",
        (now,user_id)
    )

    conn.commit()

    await message.answer("🎁 Ежедневный бонус\n\n+5 pts")

# ---------------- TOP LEGENDARY ----------------

@dp.message(Command("top"))
async def top(message: types.Message):

    cursor.execute("""
    SELECT users.name,COUNT(*)
    FROM collection
    JOIN cars ON cars.id=collection.car_id
    JOIN users ON users.id=collection.user_id
    WHERE cars.rarity=4
    GROUP BY users.id
    ORDER BY COUNT(*) DESC
    LIMIT 5
    """)

    players=cursor.fetchall()

    if not players:
        await message.answer("Пока нет Legendary")
        return

    text="🏆 Топ Legendary\n\n"

    i=1
    for name,count in players:

        text+=f"{i}. {name} — {count}\n"
        i+=1

    await message.answer(text)

# ---------------- TOP PTS ----------------

@dp.message(Command("top_pts"))
async def top_pts(message: types.Message):

    cursor.execute("""
    SELECT name,pts
    FROM users
    ORDER BY pts DESC
    LIMIT 5
    """)

    players=cursor.fetchall()

    text="🏆 Топ по очкам\n\n"

    i=1
    for name,pts in players:

        text+=f"{i}. {name} — {pts} pts\n"
        i+=1

    await message.answer(text)

# ---------------- SHOP ----------------

@dp.message(Command("shop"))
async def shop(message: types.Message):

    await message.answer(
        "🎰 Магазин\n\n1️⃣ Рулетка — 300 pts\nИспользуй /roulette"
    )

# ---------------- ROULETTE ----------------

@dp.message(Command("roulette"))
async def roulette(message: types.Message):

    user_id=message.from_user.id

    cursor.execute("SELECT pts FROM users WHERE id=?", (user_id,))
    pts=cursor.fetchone()[0]

    if pts<300:

        await message.answer("❌ Нужно 300 pts")
        return

    cursor.execute(
        "UPDATE users SET pts=pts-300 WHERE id=?",
        (user_id,)
    )

    conn.commit()

    nums=["7️⃣","🎲","7️⃣"]

    random.shuffle(nums)

    text="🎰 Казино...\n\n"

    for n in nums:

        text+=n+"\n"
        await message.answer(text)
        await asyncio.sleep(0.6)

    if nums==["7️⃣","7️⃣","7️⃣"]:

        cursor.execute(
            "SELECT * FROM cars WHERE rarity=4 ORDER BY RANDOM() LIMIT 1"
        )

        car=cursor.fetchone()

        if car:

            await message.answer(
                f"🏆 ДЖЕКПОТ!\n\n{car[1]}"
            )

    else:

        await message.answer("❌ Не повезло")

# ---------------- ADMIN ADD ----------------

admin_state={}

@dp.message(Command("add"))
async def add(message: types.Message):

    if message.from_user.id!=ADMIN_ID:
        return

    admin_state[message.from_user.id]="photo"

    await message.answer("📸 Отправь фото машины")

@dp.message()
async def process_add(message: types.Message):

    if message.from_user.id not in admin_state:
        return

    state=admin_state[message.from_user.id]

    if state=="photo":

        if not message.photo:
            await message.answer("Нужно фото")
            return

        photo=message.photo[-1].file_id

        admin_state[message.from_user.id]={"photo":photo}

        await message.answer(
            "Название | Описание | Редкость | Очки"
        )

    else:

        data=message.text.split("|")

        if len(data)!=4:
            await message.answer("Неверный формат")
            return

        name=data[0].strip()
        desc=data[1].strip()
        rarity=int(data[2].strip())
        pts=int(data[3].strip())
        photo=admin_state[message.from_user.id]["photo"]

        cursor.execute("""
        INSERT INTO cars(name,description,rarity,pts,photo)
        VALUES(?,?,?,?,?)
        """,(name,desc,rarity,pts,photo))

        conn.commit()

        admin_state.pop(message.from_user.id)

        await message.answer("✅ Машина добавлена")

# ---------------- ADMIN DELETE CAR ----------------

@dp.message(Command("delete_car"))
async def delete_car(message: types.Message):

    if message.from_user.id!=ADMIN_ID:
        return

    try:

        car_id=int(message.text.split()[1])

    except:

        await message.answer("Используй /delete_car ID")
        return

    cursor.execute("DELETE FROM cars WHERE id=?", (car_id,))
    cursor.execute("DELETE FROM collection WHERE car_id=?", (car_id,))

    conn.commit()

    await message.answer("❌ Машина удалена")

# ---------------- ADMIN RESET ----------------

@dp.message(Command("admin_reset"))
async def admin_reset(message: types.Message):

    if message.from_user.id!=ADMIN_ID:
        return

    cursor.execute(
        "DELETE FROM collection WHERE user_id=?",
        (message.from_user.id,)
    )

    cursor.execute(
        "UPDATE users SET last_roll=0 WHERE id=?",
        (message.from_user.id,)
    )

    conn.commit()

    await message.answer("🧹 Коллекция очищена")

# ---------------- START BOT ----------------

async def main():

    await set_commands()

    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
