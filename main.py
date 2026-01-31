import asyncio
import logging
import os
import sys
import json
import random
import urllib.parse
from datetime import datetime
from io import BytesIO

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web, ClientSession, ClientTimeout
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users_data.json"

def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- ИНТЕРПРЕТАЦИИ ИЗ ВАШИХ ФАЙЛОВ ---
NUMEROLOGY_DATA = {
    "1": {
        "female": "Женщины: деспот. При рождении милосердные, альтруисты. Если идет не так — болезни. В основе характера доброта, но происходит слом, и женщина остается в состоянии 'я сама'. Внутри нежная, снаружи — кирпич. Нужно проживать эмоции (плевать, кричать в землю, удары).",
        "male": "Мужчины: любит отыгрываться на других, абьюзит семью. Если не нашел путь — деспот. Крайне высокая адаптивность, но при невозможности реализоваться считывается как мерзкий человек."
    },
    "2": "Энергия, контактность. 20 — дефицит, 22 — норма, 222+ — избыток (донор).",
    "3": "Интерес к наукам, технике, творчеству. Фундамент познания.",
    "4": "Здоровье, тело. Связь с физическим миром и выносливостью.",
    "5": "Интуиция и логика. Планирование, предчувствие событий.",
    "6": "Заземление, физический труд. Мастерство рук.",
    "7": "Везение, ангел-хранитель. Помощь вселенной.",
    "8": "Долг и Род. Восьмерка — это родовая история, связь с семьей, в которой человек родился.",
    "9": "Память, экстрасенсорика. Родовой поток памяти. Проблемы здесь ведут к родовым болезням (Альцгеймер и др.).",
    "11": "Число духовных учителей. Древняя душа, ведущая других к свету. Сложно распаковать.",
    "12": "Самое сложное предназначение! После 20 лет — задача помогать людям через эзотерику. Сила слова.",
    "22": "Сверхдоход. Задача перед родом — ставить большие цели и организовывать людей (бизнесмены)."
}

MYSTIC_PERSONA = (
    "Ты — Оракул Рода. Твои ответы глубоки и метафоричны. "
    "Ты используешь данные Психоматрицы (Квадрат Пифагора) для анализа. "
    "Всегда связывай события с Родом и кармическими задачами. "
    "Используй **Markdown** для оформления. Используй только русский язык, проверяй ответы не содержат ли они иностранные слова и иероглифы. "
    "В конце ВСЕГДА добавляй: 'IMAGE_PROMPT: [fantasy mystical card description in English]'."
)

# --- СОСТОЯНИЯ ---
class ProfileStates(StatesGroup):
    waiting_for_birthdate = State()
    waiting_for_gender = State()

class HoroscopeStates(StatesGroup):
    waiting_for_sign_day = State()

# --- ЛОГИКА РАСЧЕТА (ИЗ App.tsx) ---
def get_psychomatrix(birthdate_str):
    clean = birthdate_str.replace(".", "")
    digits = [int(d) for d in clean]
    
    # 1 рабочее число
    w1 = sum(digits)
    # 2 рабочее число
    w2 = sum(int(d) for d in str(w1))
    # 3 рабочее число (первое число - 2 * первая цифра дня рождения)
    first_digit = int(clean[0])
    w3 = w1 - (2 * first_digit)
    # 4 рабочее число
    w4 = sum(int(d) for d in str(abs(w3)))
    
    all_numbers = clean + str(w1) + str(w2) + str(w3) + str(w4)
    full_list = [int(d) for d in all_numbers if d.isdigit()]
    
    matrix = {}
    for i in range(1, 10):
        count = full_list.count(i)
        matrix[i] = str(i) * count if count > 0 else f"{i}0"
    
    # Проверка спец. задач (11, 12, 22)
    special = []
    work_nums = [w1, w2, w3, w4]
    for sn in [11, 12, 22]:
        if sn in work_nums:
            special.append(str(sn))
            
    return matrix, special

def get_zodiac(date_obj):
    d, m = date_obj.day, date_obj.month
    if (m == 12 and d >= 22) or (m == 1 and d <= 19): return "♑ Козерог"
    if (m == 1 and d >= 20) or (m == 2 and d <= 18): return "♒ Водолей"
    if (m == 2 and d >= 19) or (m == 3 and d <= 20): return "♓ Рыбы"
    if (m == 3 and d >= 21) or (m == 4 and d <= 19): return "♈ Овен"
    if (m == 4 and d >= 20) or (m == 5 and d <= 20): return "♉ Телец"
    if (m == 5 and d >= 21) or (m == 6 and d <= 20): return "♊ Близнецы"
    if (m == 6 and d >= 21) or (m == 7 and d <= 22): return "♋ Рак"
    if (m == 7 and d >= 23) or (m == 8 and d <= 22): return "♌ Лев"
    if (m == 8 and d >= 23) or (m == 9 and d <= 22): return "♍ Дева"
    if (m == 9 and d >= 23) or (m == 10 and d <= 22): return "♎ Весы"
    if (m == 10 and d >= 23) or (m == 11 and d <= 21): return "♏ Скорпион"
    return "♐ Стрелец"

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔮 Прогноз на день")],
        [KeyboardButton(text="🔢 Психоматрица Рода")],
        [KeyboardButton(text="🎂 Мой профиль")]
    ], resize_keyboard=True)

# --- УТИЛИТЫ ДЛЯ ИЗОБРАЖЕНИЙ ---
async def download_image(url: str) -> bytes:
    """Скачивает изображение по URL"""
    timeout = ClientTimeout(total=30)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    if len(image_data) < 100:  # Проверяем, что это не пустой ответ
                        logging.error(f"Слишком маленькое изображение: {len(image_data)} байт")
                        return None
                    return image_data
                else:
                    logging.error(f"Ошибка загрузки изображения: статус {response.status}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка при скачивании изображения: {e}")
        return None

async def send_image_safely(message: types.Message, image_data: bytes, caption: str):
    """Безопасная отправка изображения с обработкой ошибок"""
    try:
        if image_data:
            photo = BufferedInputFile(image_data, filename="horoscope.jpg")
            await message.answer_photo(photo=photo, caption=caption)
            return True
        else:
            await message.answer(caption)
            return False
    except Exception as e:
        logging.error(f"Ошибка при отправке изображения: {e}")
        # Фолбэк: отправляем только текст
        await message.answer(caption)
        return False

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer("✨ Приветствую в Обители Рода. Чтобы я мог видеть твой путь, укажи дату рождения (ДД.ММ.ГГГГ):")
    await state.set_state(ProfileStates.waiting_for_birthdate)

@dp.message(ProfileStates.waiting_for_birthdate)
async def process_bday(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(bday=message.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Женщина", callback_data="gender_female"),
             InlineKeyboardButton(text="Мужчина", callback_data="gender_male")]
        ])
        await message.answer("Твой земной пол?", reply_markup=kb)
        await state.set_state(ProfileStates.waiting_for_gender)
    except ValueError:
        await message.answer("Используй формат ДД.ММ.ГГГГ (например, 12.05.1990)")

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "female" if "female" in callback.data else "male"
    data = await state.get_data()
    db = load_db()
    db[str(callback.from_user.id)] = {"birthdate": data['bday'], "gender": gender}
    save_db(db)
    await callback.message.edit_text("✅ Данные сохранены. Твой путь открыт.")
    await callback.message.answer("Выбери действие:", reply_markup=get_main_kb())
    await state.clear()

@dp.message(F.text == "🔢 Психоматрица Рода")
async def show_matrix(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if not user_data:
        await message.answer("Сначала настрой профиль.")
        return
    
    matrix, special = get_psychomatrix(user_data['birthdate'])
    m_view = f"| {matrix[1]} | {matrix[4]} | {matrix[7]} |\n| {matrix[2]} | {matrix[5]} | {matrix[8]} |\n| {matrix[3]} | {matrix[6]} | {matrix[9]} |"
    
    status = await message.answer("🌌 Раскладываю числовые потоки...")
    
    prompt = (
        f"Проанализируй матрицу человека (пол: {user_data['gender']}).\n"
        f"Матрица:\n{m_view}\nСпец. задачи: {', '.join(special)}.\n"
        f"Используй базу данных интерпретаций: {json.dumps(NUMEROLOGY_DATA, ensure_ascii=False)}.\n"
        "Сделай упор на предназначение и силу Рода."
    )
    
    res = await ask_ai(prompt)
    await status.delete()
    
    # Генерация URL для изображения
    img_prompt = special[0] if special else str(matrix[1])
    img_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(img_prompt)}?width=1024&height=1024&nologo=true"
    
    # Скачиваем и отправляем изображение безопасно
    image_data = await download_image(img_url)
    
    caption = f"✨ **Твоя Матрица:**\n`{m_view}`"
    await send_image_safely(message, image_data, caption)
    
    # Отправляем анализ
    analysis_text = res.split("IMAGE_PROMPT:")[0] if "IMAGE_PROMPT:" in res else res
    await message.answer(analysis_text, parse_mode="Markdown")

@dp.message(F.text == "🔮 Прогноз на день")
async def daily_horoscope(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if not user_data:
        await message.answer("Укажи дату в профиле.")
        return
    
    dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
    sign = get_zodiac(dt)
    matrix, _ = get_psychomatrix(user_data['birthdate'])
    
    status = await message.answer("🔮 Обращаюсь к звездам...")
    
    prompt = (
        f"Ты — опытный астролог, специализирующийся на индивидуальных прогнозах. "
        f"Создай персонализированный ежедневный прогноз на {datetime.now().strftime('%d.%m.%Y')} "
        f"для человека с учетом следующих данных:\n"
        f"Знак: {sign}.\n"
        f"Его матрица (единицы: {matrix[1]}, восьмерки: {matrix[8]}).\n\n"
        "**Инструкции:**\n"
        "1. **Анализ дня:**\n"
        "*   Проанализируй, через какие дома натальной карты человека (фокусируясь на его Солнечном знаке) "
        "проходят сегодня основные транзиты (Луна, Меркурий, Венера, Марс).\n"
        "*   Опиши, какие сферы жизни будут активированы (работа, дом, отношения, творчество и т.д.).\n"
        "*   Упомяни ключевые аспекты (трины, квадратуры, соединения).\n\n"
        "2. **Детальный прогноз по сферам:**\n"
        "*   Раздели прогноз на 4-5 ключевых сфер: **Карьера и дела**, **Личные отношения**, "
        "**Финансы**, **Эмоции и здоровье**, **Интуиция и внутреннее состояние**.\n"
        "*   Для каждой сферы:\n"
        "    *   Объясни, *почему* эта тема важна сегодня.\n"
        "    *   Опиши возможные **вызовы** (напряженные аспекты).\n"
        "    *   Дай **советы**, как использовать благоприятные энергии.\n"
        "    *   Укажи **лучшее время дня** для действий в этой сфере, если есть указание от положения Луны.\n\n"
        "3. **Общий вердикт и совет дня:**\n"
        "*   Суммируй основную тему дня в 1-2 предложениях.\n"
        "*   Дай один главный практический совет и одну 'аффирмацию/мысль на день'.\n\n"
        "4. **Стиль:**\n"
        "*   Будь прямым, аналитическим, но поддерживающим.\n"
        "*   Используй немного астрологической терминологии, но сразу ее поясняй."
    )
    
    res = await ask_ai(prompt)
    await status.delete()
    
    # Извлекаем текст и промпт для изображения
    if "IMAGE_PROMPT:" in res:
        clean_text, img_prompt_part = res.split("IMAGE_PROMPT:")
        img_prompt = img_prompt_part.strip()
    else:
        clean_text = res
        img_prompt = f"mystical oracle card for {sign} astrology"
    
    # Генерация URL для изображения с случайным seed
    img_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(img_prompt)}?width=1024&height=1024&nologo=true&seed={random.randint(1, 9999)}"
    
    # Скачиваем изображение
    image_data = await download_image(img_url)
    
    # Отправляем изображение с безопасной обработкой ошибок
    caption = f"🌟 Прогноз для знака {sign}"
    await send_image_safely(message, image_data, caption)
    
    # Отправляем текст прогноза
    await message.answer(clean_text, parse_mode="Markdown")

async def ask_ai(prompt):
    try:
        completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": MYSTIC_PERSONA},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка при обращении к Groq: {e}")
        return f"⚠️ Эфир затуманен... ({str(e)})"

@dp.message(F.text == "🎂 Мой профиль")
async def show_profile(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if not user_data:
        await message.answer("Профиль пуст. Нажми /start")
    else:
        dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
        sign = get_zodiac(dt)
        await message.answer(
            f"📅 Дата рождения: {user_data['birthdate']}\n"
            f"👤 Пол: {user_data['gender']}\n"
            f"♊ Знак зодиака: {sign}\n\n"
            "Чтобы изменить данные, нажми /start"
        )

# --- ВЕБ-СЕРВЕР ---
async def handle(request):
    return web.Response(text="Oracle is online")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
