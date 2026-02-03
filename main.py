import asyncio
import logging
import os
import sys
import json
import random
import re
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from urllib.parse import quote

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from dotenv import load_dotenv
from groq import AsyncGroq
import httpx
from bs4 import BeautifulSoup

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 8080))

# Проверка токенов
if not TOKEN or not GROQ_API_KEY:
    sys.exit("Ошибка: Не заданы BOT_TOKEN или GROQ_API_KEY в переменных окружения.")

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

DB_FILE = "users_data.json"

# --- БАЗА ДАННЫХ И ЗНАЧЕНИЯ МАТРИЦЫ ---

# 1. Загружаем интерпретации из values.ts (конвертировано в Python словарь)
MATRIX_VALUES: Dict[str, str] = {
    "1": "Женщины: деспот. При рождении милосердные, альтруисты, быстро адаптируются к миру. Необходимо научиться проживать эмоции. Мужчины: любят отыгрываться на других, абьюзят семью, если не нашли путь.",
    "11": "Женщины: семейная, мягкая, уступчивая. Мужчины: много страхов, мягкий характер, часто симбиоз с мамой.",
    "111": "Женщины: врожденная мудрость, интуиция. Мужчины: хороший семьянин, но нужен стимул от жены.",
    "1111": "Женщины: мужская сила характера, карьеристка. Мужчины: идеальный характер, 'Пчелка', лидер, дипломат.",
    "11111": "Женщины: тираны, продавливают мир. Мужчины: поздно взрослеют, огромная сила распаковывается после 30.",
    "2": "Нейтрал/дефицит энергии. Энергия уходит скачками. В 45-50 лет возможен сильный спад.",
    "22": "Донор энергии. Нужно двигаться, полезно делиться энергией. Долгожители.",
    "222": "Экстрасенсорные способности. Нельзя завидовать и ревновать. Быстро проваливаются в стресс, но и восстанавливаются.",
    "2222": "Профицит энергии. Обязаны быть в постоянном движении, иначе энергия разрушает изнутри (депрессии).",
    "22222": "Мощная энергия, 'ведьмаки'. Тотальный запрет на ревность и рассказы о планах.",
    "20": "Истинные вампиры (нет двоек). Нужен спорт, природа, дыхательные практики для набора сил.",
    "3": "Норма. Разумный, реалистичный, практичный подход.",
    "33": "Аналитический ум, креатив, но склонность к накопительству.",
    "333": "Видят мир через призму красоты. Творчество.",
    "3333": "Много страхов, особенно за репутацию. Фантазеры.",
    "33333": "Усиленные страхи и мнительность.",
    "30": "Страх потерять деньги. Нужно учиться на своем опыте, меньше анализировать, больше делать.",
    "4": "Здоровье среднее, но есть ресурсы. Важно не копить обиды.",
    "44": "Крепкое здоровье, высокая сексуальная энергия. Дар продолжения рода.",
    "444": "Любители изысков, могут влиять на людей своей верой во что-то.",
    "4444": "Богатырское здоровье. Сила слова — могут исцелить или покалечить словом.",
    "40": "Нет врожденного ресурса здоровья/рода. Нужно следить за телом, планировать детей.",
    "5": "Развитая интуиция и логика. Мужчины — надежные 'мужики'.",
    "55": "Все ресурсы идут через детей. Тотальный запрет на аборты/отказ от детей.",
    "555": "Сбой в родовой программе любви. Задача: всегда выбирать любовь и опираться на себя.",
    "50": "Тяжелый показатель. У женщин — необходимость социума. У мужчин — ранимость, доказательство мужественности.",
    "6": "Умение работать руками. Мастера, заземленные люди. Могут доносить информацию.",
    "66": "Манипуляторы, дипломаты. 'Золотые руки'.",
    "666": "Кодировщики на страхи. Сбывается то, чего боятся. Нужно работать с мышлением.",
    "6666": "Сила слова. Могут 'накаркать' себе болезни или успех. Важна чистота речи.",
    "60": "Нет шестерок. Чувство вины, 'я всем должен'. Часто проблемы с ручным трудом.",
    "7": "Мощный ангел-хранитель. До 33 лет многое сходит с рук.",
    "77": "Везунчики. Родовая удача. Важно благодарить за все.",
    "777": "Феи удачи. Нужно делиться удачей с другими, иначе канал схлопнется.",
    "7777": "Высшая опека, но риск внезапного ухода. Важно соблюдать законы Вселенной.",
    "70": "Временная удача. В 26, 33, 36 лет проверки. Нужно нарабатывать удачу благодарностью.",
    "8": "Чувство долга. Привязанность к семье.",
    "88": "Служение людям. Задача — быть наставником, социально активным.",
    "888": "Гуру, великие учителя. Могут быть тираничны в семье ради служения обществу.",
    "8888": "Высокая духовность, сенсорика. Риск ухода в зависимости без духовности.",
    "88888": "Духовные лидеры. Огромный потенциал влияния.",
    "80": "Свободолюбивые. Нарушена связь с родом. Нельзя иметь претензии к родителям.",
    "9": "Память нужно тренировать. Риск забывчивости к старости.",
    "99": "Норма, хорошая память. Легко учатся.",
    "999": "Яснознание. Должны передавать знания через чувства.",
    "9999": "Код Мага. Трансформаторы судеб. Обязаны помогать людям.",
    "99999": "Высочайший канал связи. Скептики, которые должны прийти к вере.",
    "90": "Не бывает (ошибка расчета).",
}

TASKS_VALUES: Dict[str, str] = {
    "1": "Я, эго, лидерство. Задача: самореализация, управление, но без деспотизма.",
    "2": "Дипломатия. Задача: налаживать связи, объединять род, не вампирить.",
    "3": "Творчество. Задача: дарить радость, не зацикливаться на деньгах.",
    "4": "Стабильность. Задача: профессионализм, не копить обиды, продолжать род.",
    "5": "Свобода и перемены. Задача: передавать знания, не бояться нового.",
    "6": "Любовь и гармония. Задача: помогать людям, работать руками.",
    "7": "Духовность и магия. Задача: раскрыть талант, доверять интуиции.",
    "8": "Власть и деньги. Задача: служить семье и роду, приумножать ресурсы.",
    "9": "Служение человечеству. Задача: быть примером, защищать слабых.",
    "10": "Лидерство (усиленная 1).",
    "11": "Духовное учительство. Задача: вдохновлять других.",
    "12": "Служение и иное видение. Задача: психологическая помощь, инновации.",
    "22": "Мастер-строитель. Задача: глобальные проекты, созидание."
}

def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки БД: {e}")
    return {}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения БД: {e}")

# --- СОСТОЯНИЯ ---
class ProfileStates(StatesGroup):
    waiting_for_birthdate = State()
    waiting_for_gender = State()

# --- ПАРСИНГ ГОРОСКОПОВ (ОБНОВЛЕННЫЙ) ---
class HoroscopeCollector:
    def __init__(self):
        self.zodiac_map = {
            'овен': 'aries', 'телец': 'taurus', 'близнецы': 'gemini',
            'рак': 'cancer', 'лев': 'leo', 'дева': 'virgo',
            'весы': 'libra', 'скорпион': 'scorpio', 'стрелец': 'sagittarius',
            'козерог': 'capricorn', 'водолей': 'aquarius', 'рыбы': 'pisces'
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def get_mail_ru(self, sign_rus: str) -> Optional[str]:
        """Парсинг Mail.ru"""
        try:
            sign = self.zodiac_map.get(sign_rus.lower())
            url = f"https://horo.mail.ru/prediction/{sign}/today/"
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    # Поиск текста
                    text_div = soup.find('div', class_='article__text')
                    if text_div:
                        return f"📧 **Mail.ru**: {text_div.get_text(separator=' ', strip=True)[:600]}..."
        except Exception as e:
            logger.error(f"Mail.ru error: {e}")
        return None

    async def get_rambler(self, sign_rus: str) -> Optional[str]:
        """Парсинг Rambler"""
        try:
            sign = self.zodiac_map.get(sign_rus.lower())
            url = f"https://horoscopes.rambler.ru/{sign}/"
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    # Специфичный класс может меняться, ищем по контексту или структуре
                    # Обычно текст в <div class="_1E4Zo"> или похожем, но лучше искать <p>
                    paragraphs = soup.find_all('p')
                    text = " ".join([p.text.strip() for p in paragraphs if len(p.text) > 50])
                    if text:
                         return f"📰 **Rambler**: {text[:600]}..."
        except Exception as e:
            logger.error(f"Rambler error: {e}")
        return None
    
    async def get_1001(self, sign_rus: str) -> Optional[str]:
        """Парсинг 1001goroskop"""
        try:
            sign = self.zodiac_map.get(sign_rus.lower())
            url = f"https://1001goroskop.ru/?znak={sign}"
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'lxml', from_encoding='utf-8')
                    item = soup.find('div', itemprop='description')
                    if item:
                         return f"🔮 **1001goroskop**: {item.get_text(strip=True)[:600]}..."
        except Exception as e:
            logger.error(f"1001 error: {e}")
        return None

    async def collect(self, sign_rus: str) -> List[str]:
        tasks = [self.get_mail_ru(sign_rus), self.get_rambler(sign_rus), self.get_1001(sign_rus)]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r]

# --- ЛОГИКА РАСЧЕТА (ИЗ REACT APP) ---

def split_int(value: str) -> List[int]:
    """Аналог splitInt из App.tsx"""
    clean = str(value).replace('.', '')
    return [int(x) for x in clean]

def string_sum(number: int) -> int:
    """Аналог stringSum из App.tsx"""
    return sum(int(digit) for digit in str(number))

def get_matrix_value_text(number: int, full_array: List[int]) -> str:
    """Аналог getMatrixValue из App.tsx"""
    count = full_array.count(number)
    
    # Логика из Source 7-11
    if not full_array:
        return "—"
    
    if count > 5:
        # Source 9: filteredArray.slice(5).join('')
        # В JS slice(5) берет элементы с индекса 5 до конца.
        # Если у нас 7 единиц: [1,1,1,1,1,1,1], slice(5) вернет [1,1] -> "11"
        key = str(number) * (count - 5)
    elif count == 0:
        key = f"{number}0" # Source 10
    else:
        key = str(number) * count # Source 11
        
    return MATRIX_VALUES.get(key, "—")

def calculate_psychomatrix_full(date_str: str) -> dict:
    """Полный расчет согласно логике App.tsx"""
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        formatted_date = dt.strftime("%d.%m.%Y")
        year = dt.year
        
        numbers = split_int(formatted_date)
        
        # 1. First number: Sum of all digits
        first = sum(numbers)
        
        # 2. Second number: Sum of digits of First
        second = string_sum(first)
        
        # 3. Third number
        if year >= 2000:
            third = first + 19 # Source 13
        else:
            # Source 13: first - ((numbers[0] !== 0 ? numbers[0] : numbers[1]) * 2)
            # numbers[0] это первая цифра дня рождения (т.к. splitInt идет от даты)
            d0 = numbers[0]
            d1 = numbers[1]
            subtractor = d0 if d0 != 0 else d1
            third = first - (subtractor * 2)
            
        # 4. Fourth number
        fourth = string_sum(third)
        
        # Формирование полного массива
        full_array = []
        # Source 13/14: [...numbers, ...splitInt(first), ...splitInt(second), ...splitInt(third), ...splitInt(fourth)]
        # + splitInt(19) если 2000+
        full_array.extend(numbers)
        full_array.extend(split_int(str(first)))
        full_array.extend(split_int(str(second)))
        
        if year >= 2000:
            full_array.extend([1, 9]) # 19
            
        full_array.extend(split_int(str(third)))
        full_array.extend(split_int(str(fourth)))
        
        # Специальные числа
        number_array = [first, second, third, fourth]
        if year >= 2000:
            number_array.insert(2, 19)
            
        return {
            "first": first,
            "second": second,
            "third": third,
            "fourth": fourth,
            "number_array": number_array,
            "full_array": full_array,
            "year": year
        }
    except Exception as e:
        logger.error(f"Matrix calc error: {e}")
        return {}

def get_zodiac(date_obj: datetime) -> Tuple[str, str, str]:
    d, m = date_obj.day, date_obj.month
    zodiacs = [
        ((12, 22), (1, 19), ("♑ Козерог", "Козерог", "козерог")),
        ((1, 20), (2, 18), ("♒ Водолей", "Водолей", "водолей")),
        ((2, 19), (3, 20), ("♓ Рыбы", "Рыбы", "рыбы")),
        ((3, 21), (4, 19), ("♈ Овен", "Овен", "овен")),
        ((4, 20), (5, 20), ("♉ Телец", "Телец", "телец")),
        ((5, 21), (6, 20), ("♊ Близнецы", "Близнецы", "близнецы")),
        ((6, 21), (7, 22), ("♋ Рак", "Рак", "рак")),
        ((7, 23), (8, 22), ("♌ Лев", "Лев", "лев")),
        ((8, 23), (9, 22), ("♍ Дева", "Дева", "дева")),
        ((9, 23), (10, 22), ("♎ Весы", "Весы", "весы")),
        ((10, 23), (11, 21), ("♏ Скорпион", "Скорпион", "скорпион")),
        ((11, 22), (12, 21), ("♐ Стрелец", "Стрелец", "стрелец"))
    ]
    for (start_m, start_d), (end_m, end_d), (full, name_rus, name_key) in zodiacs:
        if (m == start_m and d >= start_d) or (m == end_m and d <= end_d):
            return full, name_rus, name_key
    return "♐ Стрелец", "Стрелец", "стрелец"

# --- КЛАВИАТУРЫ И УТИЛИТЫ ---
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔮 Прогноз на день")],
            [KeyboardButton(text="🔢 Психоматрица")],
            [KeyboardButton(text="🎂 Мой профиль")]
        ],
        resize_keyboard=True
    )

async def download_image(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            return resp.content if resp.status_code == 200 else None
    except: return None

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer(
        "✨ *Добро пожаловать в Оракул Рода!*\n\n"
        "Я сочетаю современную астрологию с глубоким анализом Психоматрицы (Квадрат Пифагора).\n\n"
        "Укажи свою дату рождения в формате *ДД.ММ.ГГГГ*:",
        parse_mode="Markdown"
    )
    await state.set_state(ProfileStates.waiting_for_birthdate)

@dp.message(ProfileStates.waiting_for_birthdate)
async def process_birthdate(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text, "%d.%m.%Y")
        if dt > datetime.now(): raise ValueError
        await state.update_data(birthdate=message.text)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female"),
             InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male")]
        ])
        await message.answer("Ваш пол:", reply_markup=kb)
        await state.set_state(ProfileStates.waiting_for_gender)
    except ValueError:
        await message.answer("❌ Неверный формат. Используй *ДД.ММ.ГГГГ* (напр. 15.05.1990)")

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "женский" if "female" in callback.data else "мужской"
    data = await state.get_data()
    
    db = load_db()
    db[str(callback.from_user.id)] = {
        "birthdate": data['birthdate'],
        "gender": gender,
        "registered_at": datetime.now().strftime("%Y-%m-%d")
    }
    save_db(db)
    
    await callback.message.edit_text(f"✅ Профиль сохранен!\nДата: {data['birthdate']}\nПол: {gender}")
    await callback.message.answer("Меню:", reply_markup=get_main_kb())
    await state.clear()

@dp.message(F.text == "🔢 Психоматрица")
async def show_matrix(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if not user_data: return await message.answer("Нажми /start")
    
    calc = calculate_psychomatrix_full(user_data['birthdate'])
    full_array = calc['full_array']
    
    # Генерация таблицы
    def count(n): return full_array.count(n)
    def cell(n): return (str(n) * count(n)) if count(n) > 0 else "—"
    
    matrix_view = (
        f"┌───────┬───────┬───────┐\n"
        f"│ {cell(1):<5} │ {cell(4):<5} │ {cell(7):<5} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│ {cell(2):<5} │ {cell(5):<5} │ {cell(8):<5} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│ {cell(3):<5} │ {cell(6):<5} │ {cell(9):<5} │\n"
        f"└───────┴───────┴───────┘"
    )
    
    # Дополнительные числа
    add_nums = ".".join(map(str, calc['number_array']))
    task_soul = TASKS_VALUES.get(str(calc['second']), "Нет данных")
    task_rod = TASKS_VALUES.get(str(calc['fourth']), "Нет данных")
    
    res = f"🧬 **Ваша Матрица**\n`{matrix_view}`\n\n"
    res += f"🔢 **Доп. числа:** `{add_nums}`\n\n"
    res += f"✨ **Личная задача Души ({calc['second']}):**\n_{task_soul}_\n\n"
    res += f"🌳 **Родовая задача ({calc['fourth']}):**\n_{task_rod}_\n\n"
    
    res += "**Ключевые характеристики:**\n"
    # Пример вывода нескольких ключевых показателей (не всех сразу, чтобы не спамить)
    for i in [1, 2, 8]:
        val_text = get_matrix_value_text(i, full_array)
        res += f"📌 **Сектор {i}:** {val_text}\n"

    await message.answer(res, parse_mode="Markdown")

@dp.message(F.text == "🔮 Прогноз на день")
async def daily_forecast(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if not user_data: return await message.answer("Нажми /start")
    
    msg = await message.answer("📡 Подключаюсь к эгрегору...")
    
    # 1. Данные пользователя
    dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
    _, zodiac_name, zodiac_key = get_zodiac(dt)
    
    # 2. Сбор гороскопов
    collector = HoroscopeCollector()
    raw_horoscopes = await collector.collect(zodiac_key)
    horoscope_text = "\n\n".join(raw_horoscopes) if raw_horoscopes else "Общий фон нейтральный."
    
    # 3. Расчет матрицы для контекста
    calc = calculate_psychomatrix_full(user_data['birthdate'])
    full_array = calc['full_array']
    
    # Формируем контекст личности для AI
    # Берем интерпретации 1 (Характер), 2 (Энергия) и 8 (Род/Удача) для синтеза
    context_traits = f"""
    Характер (1): {get_matrix_value_text(1, full_array)}
    Энергия (2): {get_matrix_value_text(2, full_array)}
    Родовая задача: {TASKS_VALUES.get(str(calc['fourth']), '')}
    """
    
    # 4. Запрос к AI
    prompt = f"""
    Составь мистический и полезный прогноз на {datetime.now().strftime('%d.%m.%Y')}.
    
    👤 ЧЕЛОВЕК:
    Знак: {zodiac_name} ({user_data['gender']})
    Матрица Пифагора особенности:
    {context_traits}
    
    📰 СОБРАННЫЕ ГОРОСКОПЫ ИЗ СЕТИ:
    {horoscope_text}
    
    ЗАДАЧА:
    1. Синтезируй гороскопы в единый прогноз.
    2. Добавь совет, опираясь на "Характер" и "Энергию" человека (например, если мало двоек - посоветуй беречь силы).
    3. Стиль: Поддерживающий, эзотерический, но практичный.
    4. Структура: Общий фон, Работа/Финансы, Отношения, Совет Матрицы.
    5. В конце добавь: IMAGE_PROMPT: [описание картинки на английском, таро стиль, 15 слов]
    """
    
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )
        response = chat_completion.choices[0].message.content
        
        # Обработка картинки
        text_part = response
        if "IMAGE_PROMPT:" in response:
            parts = response.split("IMAGE_PROMPT:")
            text_part = parts[0]
            img_prompt = parts[1].strip()
            
            # Генерация
            encoded = quote(f"tarot card style, mystical, {img_prompt}", safe='')
            seed = random.randint(1, 9999)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=1000&nologo=true&seed={seed}"
            
            await msg.delete()
            photo = await download_image(url)
            
            caption = f"🌌 **Прогноз для {zodiac_name}**\n\n{text_part}"
            if len(caption) > 1024:
                await message.answer_photo(BufferedInputFile(photo, "img.jpg"))
                await message.answer(text_part, parse_mode="Markdown")
            else:
                await message.answer_photo(BufferedInputFile(photo, "img.jpg"), caption=caption, parse_mode="Markdown")
        else:
            await msg.edit_text(text_part, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await msg.edit_text(f"⚠️ Магические помехи. Прогноз из источников:\n\n{horoscope_text}", parse_mode="Markdown")

@dp.message(F.text == "🎂 Мой профиль")
async def profile(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    if user_data:
        await message.answer(f"👤 **Профиль**\nДата: {user_data['birthdate']}\nПол: {user_data['gender']}", parse_mode="Markdown")

# --- СЕРВЕР ---
async def handle(request): return web.Response(text="Bot Running")

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
