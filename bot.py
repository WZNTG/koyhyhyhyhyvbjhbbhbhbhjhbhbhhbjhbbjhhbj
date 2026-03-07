import asyncio
import logging
import random
import sqlite3
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, 
                           BotCommand, BotCommandScopeAllGroupChats, 
                           BotCommandScopeAllPrivateChats, CallbackQuery)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- КОНФИГ ---
TOKEN = "8303496738:AAHRcdrzIUW1r-Fo5K5Zif_4EWx3UHhxzyY"
ADMIN_ID = 5394084759

# --- БД ---
conn = sqlite3.connect('cars_bot.db', check_same_thread=False)
cursor = conn.cursor()

def db_init():
    cursor.execute('''CREATE TABLE IF NOT EXISTS cars 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, 
                       rarity TEXT, points INTEGER, photo_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, last_roll TEXT, username TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS collection 
                      (user_id INTEGER, car_id INTEGER)''')
    try: cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
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

# --- ЛОГИКА ---

@dp.message(Command("reset_stats"))
async def cmd_reset_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("DELETE FROM collection")
    cursor.execute("UPDATE users SET last_roll = NULL")
    conn.commit()
    await message.answer("✅ Статистика сброшена. КД у всех удалено.")

@dp.message(Command("roll"))
async def cmd_roll(message: types.Message):
    uid, uname = message.from_user.id, message.from_user.full_name
    
    # Регистрация/Обновление ника
    cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET username = excluded.username", (uid, uname))
    
    # ПРОВЕРКА КД (Исправлено)
    cursor.execute("SELECT last_roll FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    now = datetime.now()
    
    if row and row[0]:
        try:
            last_roll_time = datetime.fromisoformat(row[0])
            next_roll_time = last_roll_time + timedelta(hours=2)
            if now < next_roll_time:
                diff = next_roll_time - now
                mins = int(diff.total_seconds() // 60)
                return await message.reply(f"⏳ Твой гараж закрыт! Попробуй через <b>{mins} мин.</b>", parse_mode="HTML")
        except: pass

    # ВЫБОР РЕДКОСТИ
    rar_name = random.choices(list(RARITIES.values()), weights=CHANCES)[0]
    
    # ВЫБОР МАШИНЫ (Гарантированный рандом)
    cursor.execute("SELECT id, name, description, photo_id, points FROM cars WHERE rarity = ? ORDER BY RANDOM() LIMIT 1", (rar_name,))
    car = cursor.fetchone()
    
    # Если в этой редкости нет машин, берем ЛЮБУЮ другую
    if not car:
        cursor.execute("SELECT id, name, description, photo_id, points, rarity FROM cars ORDER BY RANDOM() LIMIT 1")
        car = cursor.fetchone()
        if not car: return await message.answer("⚠️ Админ еще не завез машины! База пуста.")
        car_id, name, desc, photo, pts, rar_name = car
    else:
        car_id, name, desc, photo, pts = car

    # СОХРАНЕНИЕ
    cursor.execute("INSERT INTO collection (user_id, car_id) VALUES (?, ?)", (uid, car_id))
    cursor.execute("UPDATE users SET last_roll = ? WHERE user_id = ?", (now.isoformat(), uid))
    conn.commit()

    caption = (f"🏎 <b>{uname}</b> выбил новую тачку!\n\n"
               f"🏷 <b>{name}</b>\n💎 Редкость: {rar_name}\n⚡️ Очки: {pts}\n\n<i>{desc}</i>")
    
    await message.answer_photo(photo, caption=caption, parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    cursor.execute("""SELECT u.username, COUNT(col.car_id) as c FROM collection col 
                      JOIN cars c ON col.car_id = c.id 
                      JOIN users u ON col.user_id = u.user_id
                      WHERE c.rarity = '🟡 Legendary' GROUP BY col.user_id ORDER BY c DESC LIMIT 5""")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🏆 Легенд пока нет ни у кого.")
    
    res = "🏆 <b>ТОП ПО ЛЕГЕНДАРКАМ:</b>\n\n"
    for i, r in enumerate(rows, 1):
        res += f"{i}. <b>{r[0]}</b> — 🟡 {r[1]} шт.\n"
    await message.answer(res, parse_mode="HTML")

# --- АДМИНКА (Добавление машин) ---

@dp.message(Command("add"))
async def admin_add(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_for_photo)
    await message.answer("📸 Отправь фото машины:")

@dp.message(AdminStates.waiting_for_photo, F.photo)
async def admin_photo(message: types.Message, state: FSMContext):
    await state.update_data(pic=message.photo[-1].file_id)
    await state.set_state(AdminStates.waiting_for_data)
    await message.answer("Введи данные: <code>Название _ Описание _ 1-4 _ Очки</code>", parse_mode="HTML")

@dp.message(AdminStates.waiting_for_data)
async def admin_save(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        parts = [x.strip() for x in message.text.split("_")]
        name = parts[0].replace("_", " ")
        desc = parts[1].replace("_", " ")
        rar = RARITIES.get(parts[2], "⚪️ Common")
        pts = int(parts[3])
        
        cursor.execute("INSERT INTO cars (name, description, rarity, points, photo_id) VALUES (?,?,?,?,?)",
                       (name, desc, rar, pts, data['pic']))
        conn.commit()
        await message.answer(f"✅ Машина <b>{name}</b> добавлена!", parse_mode="HTML")
        await state.clear()
    except:
        await message.answer("❌ Ошибка! Формат: Название _ Описание _ 1-4 _ Очки")

# --- ПРОЧЕЕ ---

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
    if not cars: return await message.reply("Твой гараж пуст.")
    res = "\n".join([f"• {c[1]} {c[0]}" for c in cars[-15:]])
    await message.answer(f"🚘 <b>Последние поступления:</b>\n\n{res}", parse_mode="HTML")

async def main():
    logging.basicConfig(level=logging.INFO)
    db_init()
    # Установка команд в меню
    await bot.set_my_commands([BotCommand(command="roll", description="Крутить"), BotCommand(command="top", description="Топ"), BotCommand(command="profile", description="Профиль")], scope=BotCommandScopeAllGroupChats())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
