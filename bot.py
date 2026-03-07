import asyncio
import logging
import random
import sqlite3
import re
import time
from datetime import timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, 
                           BotCommand, BotCommandScopeAllGroupChats, 
                           BotCommandScopeAllPrivateChats, CallbackQuery)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- НАСТРОЙКИ ---
TOKEN = "8303496738:AAHRcdrzIUW1r-Fo5K5Zif_4EWx3UHhxzyY"
ADMIN_ID = 5394084759

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('cars_bot.db', check_same_thread=False)
cursor = conn.cursor()

def db_init():
    cursor.execute('''CREATE TABLE IF NOT EXISTS cars 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, 
                       rarity TEXT, points INTEGER, photo_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, last_roll_ts REAL, username TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS collection 
                      (user_id INTEGER, car_id INTEGER)''')
    
    # Миграция БД без потери данных
    try: cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE users ADD COLUMN last_roll_ts REAL")
    except: pass
    conn.commit()

RARITIES = {"1": "⚪️ Common", "2": "🔵 Rare", "3": "🟣 Epic", "4": "🟡 Legendary"}
CHANCES = [70, 20, 8, 2]

class AdminStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_data = State()

class SuggestStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_data = State()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- КОМАНДЫ ---

@dp.message(Command("reset_stats"))
async def cmd_reset_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("DELETE FROM collection")
    cursor.execute("UPDATE users SET last_roll_ts = 0")
    conn.commit()
    await message.answer("✅ Статистика и КД сброшены у всех. Машины на месте.")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    uid, uname = message.from_user.id, message.from_user.full_name
    cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET username = excluded.username", (uid, uname))
    conn.commit()
    if message.chat.type == "private" and "suggest" in (message.text or ""):
        await state.set_state(SuggestStates.waiting_for_photo)
        return await message.answer("📸 Отправь фото для предложки:")
    await message.answer("🏎 Бот готов! Пиши /roll.")

@dp.message(Command("roll"))
async def cmd_roll(message: types.Message):
    uid, uname = message.from_user.id, message.from_user.full_name
    now_ts = time.time()
    
    cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET username = excluded.username", (uid, uname))
    
    # ЖЕСТКИЙ ФИКС КД ЧЕРЕЗ UNIX-ВРЕМЯ
    cursor.execute("SELECT last_roll_ts FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    
    if row and row[0]:
        last_roll_ts = row[0]
        # 7200 секунд = 2 часа
        if now_ts < last_roll_ts + 7200:
            left_seconds = (last_roll_ts + 7200) - now_ts
            mins = int(left_seconds // 60)
            return await message.reply(f"⏳ Гараж закрыт! Жди {mins} мин.")

    # ЖЕСТКИЙ ФИКС РАНДОМА ЧЕРЕЗ PYTHON
    rar_name = random.choices(list(RARITIES.values()), weights=CHANCES)[0]
    
    cursor.execute("SELECT id, name, description, photo_id, points FROM cars WHERE rarity = ?", (rar_name,))
    cars_list = cursor.fetchall()
    
    if not cars_list:
        cursor.execute("SELECT id, name, description, photo_id, points, rarity FROM cars")
        cars_list = cursor.fetchall()
        if not cars_list:
            return await message.answer("⚠️ База пуста. Добавь авто.")
        car = random.choice(cars_list)
        car_id, name, desc, photo, pts, rar_name = car
    else:
        car = random.choice(cars_list)
        car_id, name, desc, photo, pts = car

    # СОХРАНЕНИЕ
    cursor.execute("INSERT INTO collection (user_id, car_id) VALUES (?, ?)", (uid, car_id))
    cursor.execute("UPDATE users SET last_roll_ts = ? WHERE user_id = ?", (now_ts, uid))
    conn.commit()

    await message.answer_photo(
        photo, 
        caption=f"🏎 <b>{uname}</b> выбил:\n\n🏷 <b>{name}</b>\n💎 {rar_name}\n⚡️ {pts} pts\n\n<i>{desc}</i>", 
        parse_mode="HTML"
    )

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    cursor.execute("""SELECT u.username, COUNT(col.car_id) as c FROM collection col 
                      JOIN cars c ON col.car_id = c.id 
                      JOIN users u ON col.user_id = u.user_id
                      WHERE c.rarity = '🟡 Legendary' GROUP BY col.user_id ORDER BY c DESC LIMIT 5""")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🏆 Легенд пока нет.")
    res = "🏆 <b>ТОП ПО ЛЕГЕНДАРКАМ:</b>\n\n" + "\n".join([f"{i+1}. <b>{r[0]}</b> — 🟡 {r[1]} шт." for i, r in enumerate(rows)])
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    uid = message.from_user.id
    cursor.execute("SELECT COUNT(*), SUM(c.points) FROM collection col JOIN cars c ON col.car_id = c.id WHERE col.user_id = ?", (uid,))
    s = cursor.fetchone()
    await message.answer(f"👤 <b>{message.from_user.full_name}</b>\n🚘 Машин: {s[0] or 0}\n⚡️ Очки: {s[1] or 0}", parse_mode="HTML")

@dp.message(Command("garage"))
async def cmd_garage(message: types.Message):
    cursor.execute("SELECT c.name, c.rarity FROM collection col JOIN cars c ON col.car_id = c.id WHERE col.user_id = ?", (message.from_user.id,))
    cars = cursor.fetchall()
    if not cars: return await message.reply("Гараж пуст.")
    res = "\n".join([f"• {c[1]} {c[0]}" for c in cars[-15:]])
    await message.answer(f"🚘 <b>Последние 15 машин:</b>\n\n{res}", parse_mode="HTML")

@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📨 В личку", url=f"t.me/{(await bot.get_me()).username}?start=suggest")]])
        return await message.reply("Пиши в ЛС:", reply_markup=kb)
    await state.set_state(SuggestStates.waiting_for_photo)
    await message.answer("📸 Отправь фото:")

@dp.callback_query(F.data.startswith("ok_"))
async def approve_callback(call: CallbackQuery, state: FSMContext):
    user_id = call.data.split("_")[1]
    await state.update_data(pic=call.message.photo[-1].file_id, target=user_id)
    await state.set_state(AdminStates.waiting_for_data)
    await bot.send_message(ADMIN_ID, "Данные: <code>Название _ Описание _ 1-4 _ Очки</code>", parse_mode="HTML")
    await call.answer()

@dp.message(Command("add"))
async def admin_add(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_for_photo)
    await message.answer("📸 Фото:")

@dp.message(AdminStates.waiting_for_photo, F.photo)
async def admin_photo(message: types.Message, state: FSMContext):
    await state.update_data(pic=message.photo[-1].file_id)
    await state.set_state(AdminStates.waiting_for_data)
    await message.answer("Введи: <code>Название _ Описание _ 1-4 _ Очки</code>", parse_mode="HTML")

@dp.message(AdminStates.waiting_for_data)
async def admin_save(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        p = [x.strip() for x in re.split(r'[_|]', message.text)]
        name, desc = p[0].replace("_", " "), p[1].replace("_", " ")
        rar = RARITIES.get(p[2], "⚪️ Common")
        pts = int(p[3])
        
        cursor.execute("INSERT INTO cars (name, description, rarity, points, photo_id) VALUES (?,?,?,?,?)",
                       (name, desc, rar, pts, data['pic']))
        conn.commit()
        await message.answer(f"✅ Добавлено: {name}")
        if 'target' in data:
            try: await bot.send_message(data['target'], f"🎉 Твою тачку {name} добавили!")
            except: pass
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка формата: {e}")

@dp.message(SuggestStates.waiting_for_photo, F.photo)
async def suggest_photo(message: types.Message, state: FSMContext):
    await state.update_data(pic=message.photo[-1].file_id)
    await state.set_state(SuggestStates.waiting_for_data)
    await message.answer("Напиши Название и Описание:")

@dp.message(SuggestStates.waiting_for_data)
async def suggest_data(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"ok_{message.from_user.id}")]])
    await bot.send_photo(ADMIN_ID, data['pic'], caption=f"📩 От {message.from_user.id}:\n\n{message.text}", reply_markup=kb)
    await message.answer("🚀 Отправлено!")

async def main():
    logging.basicConfig(level=logging.INFO)
    db_init()
    await bot.set_my_commands([
        BotCommand(command="roll", description="Крутить"),
        BotCommand(command="top", description="Топ"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="garage", description="Гараж")
    ], scope=BotCommandScopeAllGroupChats())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
