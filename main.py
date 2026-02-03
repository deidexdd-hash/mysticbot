import asyncio
import os
import re
import json
import random
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from dotenv import load_dotenv
from groq import AsyncGroq
import httpx

# ─────────────────────────────────────
# INIT
# ─────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("❌ BOT_TOKEN / GROQ_API_KEY не заданы")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
groq = AsyncGroq(api_key=GROQ_API_KEY)

# ─────────────────────────────────────
# CACHE (in-memory)
# ─────────────────────────────────────
CACHE: Dict[str, Dict] = {}

# ─────────────────────────────────────
# LOAD values.tsx.txt
# ─────────────────────────────────────
def load_ts_object(raw: str, name: str) -> dict:
    pattern = rf"{name}\s*=\s*({{[\s\S]*?}})"
    match = re.search(pattern, raw)
    if not match:
        raise ValueError(f"{name} не найден в values.tsx.txt")

    obj = match.group(1)
    obj = re.sub(r"(\w+):", r'"\1":', obj)
    obj = obj.replace("'", '"')
    return json.loads(obj)

def load_values():
    raw = Path("values.tsx.txt").read_text(encoding="utf-8")
    return {
        "matrix": load_ts_object(raw, "MATRIX_VALUES"),
        "tasks": load_ts_object(raw, "TASKS")
    }

CACHE = load_values()

MATRIX_VALUES = CACHE["matrix"]
TASKS = CACHE["tasks"]

# ─────────────────────────────────────
# MATRIX CALC (1:1 App.tsx)
# ─────────────────────────────────────
def split_int(v): return [int(x) for x in str(v).replace(".", "")]
def string_sum(v): return sum(map(int, str(v)))

def calculate_matrix(birth: str) -> List[int]:
    nums = split_int(birth)
    dt = datetime.strptime(birth, "%d.%m.%Y")

    first = sum(nums)
    second = string_sum(first)

    if dt.year >= 2000:
        third = first + 19
    else:
        day = split_int(dt.day)
        third = first - (day[0] if day[0] else day[1]) * 2

    fourth = string_sum(third)

    fa = (
        nums +
        split_int(first) +
        split_int(second) +
        split_int(third) +
        split_int(fourth)
    )

    if dt.year >= 2000:
        fa += [1, 9]

    return fa

# ─────────────────────────────────────
# INTERPRETATION
# ─────────────────────────────────────
def extract_gender(text: str, gender: str) -> str:
    if "Мужчины:" in text and "Женщины:" in text:
        m, f = text.split("Женщины:")
        m = m.replace("Мужчины:", "").strip()
        f = f.strip()
        return m if gender == "мужской" else f
    return text

def get_matrix_value(num: int, fa: list[int], gender: str) -> str:
    count = fa.count(num)

    if count == 0:
        key = f"{num}0"
    elif count > 5:
        key = str(num) * 5
    else:
        key = str(num) * count

    item = MATRIX_VALUES.get(key)
    if not item:
        return "—"

    return extract_gender(item["text"], gender)

def get_task(num: int) -> str:
    item = TASKS.get(str(num))
    if not item:
        return "—"
    return item["text"]

# ─────────────────────────────────────
# FSM
# ─────────────────────────────────────
class UserState(StatesGroup):
    date = State()
    gender = State()

USERS = {}

# ─────────────────────────────────────
# START
# ─────────────────────────────────────
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await msg.answer("Введите дату рождения (ДД.ММ.ГГГГ):")
    await state.set_state(UserState.date)

@dp.message(UserState.date)
async def set_date(msg: types.Message, state: FSMContext):
    try:
        datetime.strptime(msg.text, "%d.%m.%Y")
        await state.update_data(date=msg.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Мужской", callback_data="g_m"),
            InlineKeyboardButton(text="Женский", callback_data="g_f"),
        ]])
        await msg.answer("Выберите пол:", reply_markup=kb)
        await state.set_state(UserState.gender)
    except:
        await msg.answer("❌ Неверный формат. Пример: 21.03.1992")

@dp.callback_query(F.data.startswith("g_"))
async def set_gender(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gender = "мужской" if cb.data == "g_m" else "женский"

    USERS[cb.from_user.id] = {
        "date": data["date"],
        "gender": gender
    }

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

# ─────────────────────────────────────
# MATRIX OUTPUT
# ─────────────────────────────────────
@dp.message(F.text == "🔢 Матрица судьбы")
async def matrix(msg: types.Message):
    u = USERS.get(msg.from_user.id)
    if not u:
        return

    fa = calculate_matrix(u["date"])
    g = u["gender"]

    second = string_sum(sum(split_int(u["date"])))
    fourth = string_sum(string_sum(sum(split_int(u["date"]))))

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

🧭 **Личная задача души**
{get_task(second)}

🌿 **Родовая задача**
{get_task(fourth)}
"""
    await msg.answer(text, parse_mode="Markdown")

# ─────────────────────────────────────
# DAILY FORECAST
# ─────────────────────────────────────
@dp.message(F.text == "🔮 Прогноз на день")
async def forecast(msg: types.Message):
    u = USERS.get(msg.from_user.id)
    if not u:
        return

    status = await msg.answer("🔮 Считываю поле дня...")

    fa = calculate_matrix(u["date"])
    g = u["gender"]

    birth = datetime.strptime(u["date"], "%d.%m.%Y").date()
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

Личная задача: {get_task(string_sum(sum(split_int(u["date"]))))}
Родовая задача: {get_task(string_sum(string_sum(sum(split_int(u["date"])))))} 

Составь детальный мистический прогноз:
🔮 Фон дня
❤️ Отношения
💼 Работа и деньги
⚠️ Риски
🧿 Совет матрицы

Без воды.
В конце добавь:
IMAGE_PROMPT: mystical tarot card, dark gold, ultra detailed
"""

    res = await groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )

    text = res.choices[0].message.content

    if "IMAGE_PROMPT:" in text:
        body, img = text.split("IMAGE_PROMPT:")
        url = f"https://image.pollinations.ai/prompt/{img.strip()}?width=800&height=1000&seed={random.randint(1,999)}"
        async with httpx.AsyncClient() as c:
            img_bytes = (await c.get(url)).content

        await msg.answer_photo(
            BufferedInputFile(img_bytes, "day.jpg"),
            caption=body[:1024],
            parse_mode="Markdown"
        )
        await status.delete()
    else:
        await status.edit_text(text)

# ─────────────────────────────────────
# RUN
# ─────────────────────────────────────
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
