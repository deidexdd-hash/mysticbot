import asyncio
import logging
import os
import sys
import json
import random
from datetime import datetime, date
from typing import List, Optional
from urllib.parse import quote

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiohttp import web
from dotenv import load_dotenv
from groq import AsyncGroq
import httpx
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# ENV / INIT
# ─────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 10000))

if not TOKEN or not GROQ_API_KEY:
    sys.exit("❌ BOT_TOKEN или GROQ_API_KEY не найдены")

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = "users_data.json"

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
# MATRIX INTERPRETATIONS (PRODUCTION)
# ─────────────────────────────────────────────
MATRIX_VALUES = {
    "10": {
        "title": "Характер",
        "male": "Подавленное эго. Важно учиться отстаивать себя.",
        "female": "Склонность жертвовать собой. Нужны личные границы."
    },
    "1": {
        "title": "Характер",
        "male": "Сильное эго, лидерская энергия. Важно не давить на других.",
        "female": "Мягкость, интуиция. Важно проживать эмоции."
    },
    "11": {
        "title": "Характер",
        "male": "Много страхов, сильная связь с матерью.",
        "female": "Семейность, уступчивость."
    },
    "111": {
        "title": "Характер",
        "male": "Надёжный, но нуждается в стимуле.",
        "female": "Мудрость, сильная интуиция."
    },
    "1111": {
        "title": "Характер",
        "male": "Лидер, дипломат.",
        "female": "Сильный характер, карьеристка."
    },

    "20": {
        "title": "Энергия",
        "male": "Энергетический дефицит. Нужны спорт и природа.",
        "female": "Истощение энергии, важно наполнение."
    },
    "2": {
        "title": "Энергия",
        "male": "Энергия нестабильна.",
        "female": "Тонкая энергетика."
    },
    "22": {
        "title": "Энергия",
        "male": "Донор энергии.",
        "female": "Высокий ресурс, долгожительство."
    },

    "40": {
        "title": "Здоровье",
        "male": "Нет врожденного ресурса. Контроль тела обязателен.",
        "female": "Риски по здоровью и репродукции."
    },
    "4": {
        "title": "Здоровье",
        "male": "Стабильное здоровье.",
        "female": "Ресурс есть, но нельзя копить обиды."
    },
    "44": {
        "title": "Здоровье",
        "male": "Крепкий организм.",
        "female": "Сильная родовая энергия."
    },

    "80": {
        "title": "Род",
        "male": "Нарушена связь с родом. Претензии к родителям запрещены.",
        "female": "Свободолюбие, важно принять род."
    },
    "8": {
        "title": "Род",
        "male": "Ответственность за материальное благополучие рода.",
        "female": "Служение семье, объединение рода."
    },

    "9": {
        "title": "Интеллект",
        "male": "Память требует тренировки.",
        "female": "Интуитивный ум."
    },
    "99": {
        "title": "Интеллект",
        "male": "Аналитический склад ума.",
        "female": "Хорошая память и обучаемость."
    },
}

# ─────────────────────────────────────────────
# MATRIX CALCULATION (1:1 App.tsx)
# ─────────────────────────────────────────────
def split_int(value) -> List[int]:
    return [int(x) for x in str(value).replace('.', '')]

def string_sum(number: int) -> int:
    return sum(int(d) for d in str(number))

def calculate_matrix(birthdate: str):
    nums = split_int(birthdate)
    dt = datetime.strptime(birthdate, "%d.%m.%Y")

    first = sum(nums)
    second = string_sum(first)

    if dt.year >= 2000:
        third = first + 19
    else:
        day_digits = split_int(dt.day)
        subtractor = day_digits[0] if day_digits[0] != 0 else day_digits[1]
        third = first - subtractor * 2

    fourth = string_sum(third)

    full_array = nums + split_int(first) + split_int(second) + split_int(third) + split_int(fourth)
    if dt.year >= 2000:
        full_array += [1, 9]

    return full_array

def get_matrix_value(num: int, fa: List[int], gender: str) -> str:
    count = fa.count(num)
    if count == 0:
        key = f"{num}0"
    elif count > 5:
        key = str(num) * (count - 5)
    else:
        key = str(num) * count

    data = MATRIX_VALUES.get(key)
    if not data:
        return "—"

    return data["male"] if gender == "мужской" else data["female"]

# ─────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────
class States(StatesGroup):
    date = State()
    gender = State()

# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):")
    await state.set_state(States.date)

@dp.message(States.date)
async def set_date(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(date=message.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="М", callback_data="g_m"),
            InlineKeyboardButton(text="Ж", callback_data="g_f")
        ]])
        await message.answer("Ваш пол:", reply_markup=kb)
        await state.set_state(States.gender)
    except:
        await message.answer("Неверный формат. Пример: 21.03.1992")

@dp.callback_query(F.data.startswith("g_"))
async def set_gender(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gender = "мужской" if cb.data == "g_m" else "женский"

    db = load_db()
    db[str(cb.from_user.id)] = {
        "date": data["date"],
        "gender": gender
    }
    save_db(db)

    await cb.message.answer(
        "Готово. Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔢 Матрица судьбы")],
                [KeyboardButton(text="🔮 Прогноз на день")]
            ],
            resize_keyboard=True
        )
    )
    await state.clear()

# ─────────────────────────────────────────────
# MATRIX OUTPUT
# ─────────────────────────────────────────────
@dp.message(F.text == "🔢 Матрица судьбы")
async def matrix(message: types.Message):
    user = load_db().get(str(message.from_user.id))
    if not user:
        return

    fa = calculate_matrix(user["date"])
    g = user["gender"]

    text = f"""
🔢 **Матрица судьбы**

🧠 **Характер**
{get_matrix_value(1, fa, g)}

⚡ **Энергия**
{get_matrix_value(2, fa, g)}

🌳 **Род**
{get_matrix_value(8, fa, g)}

❤️ **Здоровье**
{get_matrix_value(4, fa, g)}

📚 **Интеллект**
{get_matrix_value(9, fa, g)}
"""
    await message.answer(text, parse_mode="Markdown")

# ─────────────────────────────────────────────
# DAILY FORECAST
# ─────────────────────────────────────────────
@dp.message(F.text == "🔮 Прогноз на день")
async def forecast(message: types.Message):
    user = load_db().get(str(message.from_user.id))
    if not user:
        return

    status = await message.answer("🔮 Считываю поле дня...")

    fa = calculate_matrix(user["date"])
    g = user["gender"]

    birth = datetime.strptime(user["date"], "%d.%m.%Y").date()
    age = date.today().year - birth.year

    prompt = f"""
Дата: {date.today().strftime('%d.%m.%Y')}
Пол: {g}
Возраст: {age}

Матрица:
Характер: {get_matrix_value(1, fa, g)}
Энергия: {get_matrix_value(2, fa, g)}
Род: {get_matrix_value(8, fa, g)}
Здоровье: {get_matrix_value(4, fa, g)}

Составь детальный мистический прогноз дня:

🔮 Фон дня  
❤️ Отношения  
💼 Работа и деньги  
⚠️ Риски  
🧿 Совет матрицы  

Без общих фраз.
В конце добавь:
IMAGE_PROMPT: mystical tarot card, dark gold, high detail
"""

    res = await groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )

    text = res.choices[0].message.content

    if "IMAGE_PROMPT:" in text:
        text, img = text.split("IMAGE_PROMPT:")
        url = f"https://image.pollinations.ai/prompt/{quote(img.strip())}?width=800&height=1000&nologo=true&seed={random.randint(1,999)}"
        async with httpx.AsyncClient() as client:
            img_bytes = (await client.get(url)).content
        await message.answer_photo(
            BufferedInputFile(img_bytes, "day.jpg"),
            caption=text[:1024],
            parse_mode="Markdown"
        )
        await status.delete()
    else:
        await status.edit_text(text, parse_mode="Markdown")

# ─────────────────────────────────────────────
# WEB SERVER
# ─────────────────────────────────────────────
async def web_handle(request):
    return web.Response(text="Bot is live")

async def main():
    app = web.Application()
    app.router.add_get("/", web_handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
