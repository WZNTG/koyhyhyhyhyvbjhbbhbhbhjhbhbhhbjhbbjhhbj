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

# --- КОНФИГУРАЦИЯ ---
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
                      (user_id INTEGER PRIMARY KEY, last_roll TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS collection 
                      (user_id INTEGER, car_id INTEGER)''')
    conn.commit()

RARITIES = {
    "1": "⚪️ Common",
    "2": "🔵 Rare",
    "3": "🟣 Epic",
    "4": "🟡 Legendary"
}
CHANCES = [70, 20, 8, 2]

# --- СОСТОЯНИЯ ---
class AdminStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_data = State()

class SuggestStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_data = State()

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def set_main_menu(bot: Bot):
    user_commands = [
        BotCommand(command="roll", description="Выбить случайную машину"),
        BotCommand(command="profile", description="Мой профиль и статы"),
        BotCommand(command="garage", description="Посмотреть свои машины"),
        BotCommand(command="top", description="Топ-5 по легендаркам"),
        BotCommand(command="suggest", description="Предложить свою машину"),
        BotCommand(command="cancel", description="Отменить ввод")
    ]
    admin_commands = user_commands + [BotCommand(command="add", description="[Админ] Добавить авто")]
    
    await bot.set_my_commands(user_commands, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(admin_commands, scope=BotCommandScopeAllPrivateChats())

# --- ОБРАБОТКА КОМАНД ---

@dp.message(Command("cancel"))
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    
    # Исправленный переход для предложки
    if message.chat.type == "private" and "suggest" in (message.text or ""):
        await state.set_state(SuggestStates.waiting_for_photo)
        return await message.answer("📸 Отправь <b>фото</b> машины для предложки:", parse_mode="HTML")

    await message.answer(
        "🏎 <b>Бот запущен и готов к работе!</b>\n\n"
        "Пиши /roll чтобы начать собирать коллекцию.", 
        parse_mode="HTML"
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    uid = message.from_user.id
    cursor.execute("""SELECT COUNT(col.car_id), SUM(c.points) FROM collection col 
                      JOIN cars c ON col.car_id = c.id WHERE col.user_id = ?""", (uid,))
    res = cursor.fetchone()
    total_cars, total_pts = res[0] or 0, res[1] or 0
    
    cursor.execute("""SELECT COUNT(*) FROM collection col JOIN cars c ON col.car_id = c.id 
                      WHERE col.user_id = ? AND c.rarity = '🟡 Legendary'""", (uid,))
    legs = cursor.fetchone()[0] or 0
    
    text = (f"👤 <b>Профиль:</b> {message.from_user.full_name}\n"
            f"🆔 ID: <code>{uid}</code>\n\n"
            f"🏎 Машин: <b>{total_cars}</b>\n"
            f"⚡️ Очки: <b>{total_pts}</b>\n"
            f"🟡 Легенды: <b>{legs}</b>")
    
    try:
        photos = await bot.get_user_profile_photos(uid, limit=1)
        if photos.total_count > 0:
            return await message.answer_photo(photos.photos[0][-1].file_id, caption=text, parse_mode="HTML")
    except: pass
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("roll"))
async def cmd_roll(message: types.Message):
    uid = message.from_user.id
    cursor.execute("SELECT last_roll FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    
    if row and row[0]:
        last = datetime.fromisoformat(row[0])
        if datetime.now() < last + timedelta(hours=2):
            wait = (last + timedelta(hours=2)) - datetime.now()
            return await message.reply(f"⏳ Гараж закрыт еще {wait.seconds // 60} мин.")

    rar_name = random.choices(list(RARITIES.values()), weights=CHANCES)[0]
    cursor.execute("SELECT id, name, description, photo_id, points FROM cars WHERE rarity = ? ORDER BY RANDOM() LIMIT 1", (rar_name,))
    car = cursor.fetchone()
    
    if not car:
        cursor.execute("SELECT id, name, description, photo_id, points, rarity FROM cars ORDER BY RANDOM() LIMIT 1")
        car = cursor.fetchone()
        if not car: return await message.answer("⚠️ База пуста.")
        car_id, name, desc, photo, pts, rar_name = car
    else:
        car_id, name, desc, photo, pts = car

    cursor.execute("INSERT INTO collection VALUES (?, ?)", (uid, car_id))
    cursor.execute("UPDATE users SET last_roll = ? WHERE user_id = ?", (datetime.now().isoformat(), uid))
    conn.commit()

    caption = (f"✨ <b>{message.from_user.first_name}</b> выбил:\n\n"
               f"🏎 <b>{name}</b>\n💎 {rar_name}\n⚡️ Очки: {pts}\n\n<i>{desc}</i>")
    await message.answer_photo(photo, caption=caption, parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    cursor.execute("""SELECT col.user_id, COUNT(*) as c FROM collection col 
                      JOIN cars c ON col.car_id = c.id WHERE c.rarity = '🟡 Legendary'
                      GROUP BY col.user_id ORDER BY c DESC LIMIT 5""")
    rows = cursor.fetchall()
    if not rows: return await message.answer("🏆 Легенд пока нет.")
    
    msg = "🏆 <b>ТОП ПО ЛЕГЕНДАРКАМ:</b>\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"{i}. ID <code>{r[0]}</code> — 🟡 {r[1]} шт.\n"
    await message.answer(msg, parse_mode="HTML")

@dp.message(Command("garage"))
async def cmd_garage(message: types.Message):
    cursor.execute("""SELECT c.name, c.rarity FROM collection col 
                      JOIN cars c ON col.car_id = c.id WHERE col.user_id = ?""", (message.from_user.id,))
    cars = cursor.fetchall()
    if not cars: return await message.reply("Пусто.")
    res = "\n".join([f"• {c[1]} <b>{c[0]}</b>" for c in cars[-15:]])
    await message.answer(f"🚘 <b>Твой гараж:</b>\n\n{res}", parse_mode="HTML")

# --- ПРЕДЛОЖКА (ИСПРАВЛЕНО) ---
@dp.message(Command("suggest"))
async def cmd_suggest(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📨 В личку", url=f"t.me/{(await bot.get_me()).username}?start=suggest")
        ]])
        return await message.reply("Пиши в ЛС:", reply_markup=kb)
    
    await state.set_state(SuggestStates.waiting_for_photo)
    await message.answer("📸 Отправь фото:")

@dp.message(SuggestStates.waiting_for_photo, F.photo)
async def suggest_photo(message: types.Message, state: FSMContext):
    await state.update_data(pic=message.photo[-1].file_id)
    await state.set_state(SuggestStates.waiting_for_data)
    await message.answer("Напиши Название и Описание:")

@dp.message(SuggestStates.waiting_for_data)
async def suggest_data(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"ok_{message.from_user.id}")
    ]])
    await bot.send_photo(ADMIN_ID, data['pic'], caption=f"📩 От {message.from_user.id}:\n\n{message.text}", reply_markup=kb)
    await message.answer("🚀 Отправлено!")

# --- АДМИНКА ---
@dp.message(Command("add"))
async def admin_add(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_for_photo)
    await message.answer("📸 Фото:")

@dp.callback_query(F.data.startswith("ok_"))
async def approve_callback(call: CallbackQuery, state: FSMContext):
    user_id = call.data.split("_")[1]
    await state.update_data(pic=call.message.photo[-1].file_id, target=user_id)
    await state.set_state(AdminStates.waiting_for_data)
    await bot.send_message(ADMIN_ID, "Данные: <code>Название _ Описание _ 1-4 _ Очки</code>", parse_mode="HTML")
    await call.answer()

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
        cursor.execute("INSERT INTO cars (name, description, rarity, points, photo_id) VALUES (?,?,?,?,?)",
                       (name, desc, RARITIES.get(p[2], "⚪️ Common"), int(p[3]), data['pic']))
        conn.commit()
        await message.answer(f"✅ Добавлено: {name}")
        if 'target' in data:
            try: await bot.send_message(data['target'], f"🎉 Твою тачку {name} добавили!")
            except: pass
        await state.clear()
    except: await message.answer("❌ Ошибка формата!")

async def main():
    logging.basicConfig(level=logging.INFO)
    db_init()
    await set_main_menu(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
