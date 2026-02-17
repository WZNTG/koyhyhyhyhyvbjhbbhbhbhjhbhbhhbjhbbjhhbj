import json
import os
import random
import time
from datetime import timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

DATA_FILE = "data.json"
COOLDOWN_HOURS = 20

# ВСТАВЬ СВОЙ TELEGRAM ID
ADMIN_ID = 5394084759  


# ---------- Работа с данными ----------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "promocodes": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id, data):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "balance": 0,
            "last_dick_ts": 0
        }
    return data["users"][user_id]


# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я dick-бот.\n"
        "/dick — раз в 20 часов даёт от -5 до 10 чайхана-коинов.\n"
        "/promo <код> — активировать промокод.\n"
        "/topCK — топ по балансу."
    )


async def dick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    data = load_data()
    user_data = get_user_data(user_id, data)

    now_ts = int(time.time())
    last_ts = user_data.get("last_dick_ts", 0)

    cooldown_seconds = COOLDOWN_HOURS * 3600
    elapsed = now_ts - last_ts

    if elapsed < cooldown_seconds and last_ts != 0:
        remaining = cooldown_seconds - elapsed
        td = timedelta(seconds=remaining)
        hours, remainder = divmod(td.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        await update.message.reply_text(
            f"Рано ещё дергать /dick 😏\n"
            f"Осталось {hours} ч {minutes} мин."
        )
        return

    delta = random.randint(-5, 10)
    user_data["balance"] += delta
    user_data["last_dick_ts"] = now_ts
    save_data(data)

    sign = "+" if delta >= 0 else ""
    await update.message.reply_text(
        f"Твой dick-ролл: {sign}{delta} чайхана-коинов.\n"
        f"Баланс: {user_data['balance']}."
    )


# ---------- Промокоды ----------

async def createpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Ты не админ.")
        return

    if len(context.args) != 3:
        await update.message.reply_text("Использование: /createpromo <код> <кол-во> <использований>")
        return

    code = context.args[0].lower()
    amount = int(context.args[1])
    uses = int(context.args[2])

    data = load_data()

    data["promocodes"][code] = {
        "amount": amount,
        "uses": uses
    }

    save_data(data)

    await update.message.reply_text(
        f"Промокод создан:\n"
        f"Код: {code}\n"
        f"Награда: {amount}\n"
        f"Использований: {uses}"
    )


async def promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /promo <код>")
        return

    code = context.args[0].lower()
    user_id = update.effective_user.id

    data = load_data()

    if code not in data["promocodes"]:
        await update.message.reply_text("Такого промокода нет.")
        return

    promo_data = data["promocodes"][code]

    if promo_data["uses"] <= 0:
        await update.message.reply_text("Этот промокод уже закончился.")
        return

    user_data = get_user_data(user_id, data)
    user_data["balance"] += promo_data["amount"]

    promo_data["uses"] -= 1

    if promo_data["uses"] <= 0:
        del data["promocodes"][code]

    save_data(data)

    await update.message.reply_text(
        f"Промокод активирован!\n"
        f"+{promo_data['amount']} чайхана-коинов.\n"
        f"Баланс: {user_data['balance']}."
    )


# ---------- Топ игроков ----------

async def topck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    users = data.get("users", {})

    if not users:
        await update.message.reply_text("Пока нет данных для статистики.")
        return

    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("balance", 0),
        reverse=True
    )

    top_list = sorted_users[:10]

    text = "🏆 Топ 10 по чайхана-коинам:\n\n"
    place = 1

    for user_id, info in top_list:
        balance = info.get("balance", 0)

        try:
            user = await context.bot.get_chat(int(user_id))

            if user.username:
                # НЕ пишем @username, чтобы не было синего текста
                name = f"{user.username}"
            elif user.first_name:
                name = user.first_name
            else:
                name = "Без ника"

        except:
            name = "Неизвестный"

        text += f"{place}. {name} — {balance}\n"
        place += 1

    await update.message.reply_text(text)



# ---------- Запуск ----------

def main():
    BOT_TOKEN = "8477161043:AAEusYx3wESbcHRtK5yUJJtu6G3OwSRijzg"  # ВСТАВЬ НОВЫЙ ТОКЕН

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dick", dick))
    app.add_handler(CommandHandler("promo", promo))
    app.add_handler(CommandHandler("createpromo", createpromo))
    app.add_handler(CommandHandler("topCK", topck))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
