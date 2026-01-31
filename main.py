import asyncio
import logging
import os
import sys
import json
import random
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web, ClientSession, ClientTimeout
from dotenv import load_dotenv
from groq import AsyncGroq
import httpx

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users_data.json"

def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки БД: {e}")
        return {}
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

# --- КОЛЛЕКТОР ГОРОСКОПОВ С ПАРСИНГОМ ---
class HoroscopeCollector:
    def __init__(self):
        self.zodiac_map = {
            'овен': ['aries', 'oven'],
            'телец': ['taurus', 'telec'],
            'близнецы': ['gemini', 'bliznecy', 'bliznetsy'],
            'рак': ['cancer', 'rak'],
            'лев': ['leo', 'lev'],
            'дева': ['virgo', 'deva'],
            'весы': ['libra', 'vesy'],
            'скорпион': ['scorpio', 'skorpion'],
            'стрелец': ['sagittarius', 'strelec', 'strelets'],
            'козерог': ['capricorn', 'kozerog'],
            'водолей': ['aquarius', 'vodoley'],
            'рыбы': ['pisces', 'ryby']
        }
    
    async def fetch_horoscope_api(self, sign_rus: str) -> List[str]:
        """Получаем гороскопы через публичные API"""
        results = []
        
        # API 1: Используем open API для гороскопов (пример)
        try:
            # Этот эндпоинт может работать, но нужно проверить его доступность
            url = "https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily"
            params = {
                'sign': self.zodiac_map.get(sign_rus.lower(), ['aries'])[0],
                'day': 'TODAY'
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and 'horoscope_data' in data['data']:
                        text = data['data']['horoscope_data']
                        results.append(f"🌐 **API Гороскоп**: {text}")
        except Exception as e:
            logger.info(f"API 1 недоступен: {e}")
        
        # API 2: Альтернативный источник
        try:
            # Можно использовать другой открытый API
            sign_en = self.zodiac_map.get(sign_rus.lower(), ['aries'])[0]
            url = f"https://ohmanda.com/api/horoscope/{sign_en}/"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if 'horoscope' in data:
                        text = data['horoscope']
                        results.append(f"✨ **Гороскоп**: {text}")
        except Exception as e:
            logger.info(f"API 2 недоступен: {e}")
        
        return results
    
    async def parse_rambler_horoscope(self, sign_rus: str) -> Optional[str]:
        """Парсинг с Rambler.ru (без BeautifulSoup, только regex)"""
        try:
            sign_en = self.zodiac_map.get(sign_rus.lower(), ['aries'])[0]
            url = f"https://horoscopes.rambler.ru/{sign_en}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    html = response.text
                    
                    # Ищем тексты гороскопа по ключевым словам
                    patterns = [
                        r'"text":"([^"]+)"',  # JSON-like тексты
                        r'<p[^>]*>(.*?)</p>',  # Параграфы
                        r'content":"([^"]+)"', # Контент в JSON
                        r'description":"([^"]+)"' # Описания
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                        for match in matches:
                            # Очищаем текст
                            text = re.sub(r'<[^>]+>', '', match)
                            text = re.sub(r'\s+', ' ', text).strip()
                            if len(text) > 100 and any(word in text.lower() for word in ['сегодня', 'день', 'неделя', 'месяц', 'год', 'совет', 'рекоменда']):
                                # Проверяем, что это похоже на гороскоп
                                if any(astro_word in text.lower() for astro_word in ['звезд', 'планет', 'судьб', 'удач', 'любов', 'денег', 'работ']):
                                    return f"📰 **Rambler.ru**: {text[:500]}..."
                    
                    # Альтернативный поиск
                    if 'horoscope' in html.lower() or 'гороскоп' in html.lower():
                        # Вырезаем большой кусок текста вокруг ключевых слов
                        horoscope_sections = re.findall(r'[^>]+гороскоп[^<]+', html, re.IGNORECASE)
                        for section in horoscope_sections:
                            text = re.sub(r'<[^>]+>', '', section)
                            text = re.sub(r'\s+', ' ', text).strip()
                            if len(text) > 80:
                                return f"📰 **Rambler.ru**: {text[:400]}..."
                            
        except Exception as e:
            logger.error(f"Ошибка парсинга Rambler: {e}")
        return None
    
    async def parse_mail_horoscope(self, sign_rus: str) -> Optional[str]:
        """Парсинг с Mail.ru"""
        try:
            sign_en = self.zodiac_map.get(sign_rus.lower(), ['aries'])[0]
            url = f"https://horo.mail.ru/prediction/{sign_en}/today/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    html = response.text
                    
                    # Ищем основной контент
                    content_patterns = [
                        r'<div[^>]*class="[^"]*article__item[^"]*"[^>]*>([\s\S]*?)</div>',
                        r'<div[^>]*class="[^"]*article__text[^"]*"[^>]*>([\s\S]*?)</div>',
                        r'<p[^>]*itemprop="[^"]*description[^"]*"[^>]*>([\s\S]*?)</p>'
                    ]
                    
                    for pattern in content_patterns:
                        matches = re.findall(pattern, html, re.DOTALL)
                        for match in matches:
                            # Извлекаем текст из всех тегов внутри
                            text = re.sub(r'<[^>]+>', ' ', match)
                            text = re.sub(r'\s+', ' ', text).strip()
                            if len(text) > 100:
                                # Проверяем что это гороскоп
                                if any(word in text.lower() for word in ['сегодня', 'завтра', 'день', 'неделя']):
                                    return f"📧 **Mail.ru**: {text[:500]}..."
                    
        except Exception as e:
            logger.error(f"Ошибка парсинга Mail.ru: {e}")
        return None
    
    async def parse_1001_horoscope(self, sign_rus: str) -> Optional[str]:
        """Парсинг с 1001goroskop.ru"""
        try:
            sign_mapping = {
                'овен': 'aries',
                'телец': 'taurus', 
                'близнецы': 'gemini',
                'рак': 'cancer',
                'лев': 'leo',
                'дева': 'virgo',
                'весы': 'libra',
                'скорпион': 'scorpio',
                'стрелец': 'sagittarius',
                'козерог': 'capricorn',
                'водолей': 'aquarius',
                'рыбы': 'pisces'
            }
            
            sign_en = sign_mapping.get(sign_rus.lower(), 'aries')
            url = f"https://1001goroskop.ru/?znak={sign_en}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    html = response.text
                    
                    # Ищем текст гороскопа
                    patterns = [
                        r'<div[^>]*class="[^"]*horoscope_text[^"]*"[^>]*>([\s\S]*?)</div>',
                        r'<div[^>]*class="[^"]*text[^"]*"[^>]*>([\s\S]*?)</div>',
                        r'<p[^>]*align="[^"]*justify[^"]*"[^>]*>([\s\S]*?)</p>'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, html, re.DOTALL)
                        for match in matches:
                            text = re.sub(r'<[^>]+>', ' ', match)
                            text = re.sub(r'\s+', ' ', text).strip()
                            if len(text) > 50:
                                return f"🔢 **1001goroskop.ru**: {text[:500]}..."
                    
        except Exception as e:
            logger.error(f"Ошибка парсинга 1001goroskop: {e}")
        return None
    
    async def collect_horoscopes(self, sign_rus: str) -> List[str]:
        """Сбор гороскопов из разных источников"""
        results = []
        
        # Сначала пробуем API
        api_results = await self.fetch_horoscope_api(sign_rus)
        results.extend(api_results)
        
        # Затем парсинг сайтов (параллельно)
        tasks = [
            self.parse_rambler_horoscope(sign_rus),
            self.parse_mail_horoscope(sign_rus),
            self.parse_1001_horoscope(sign_rus)
        ]
        
        try:
            parsed_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in parsed_results:
                if isinstance(result, str) and result:
                    results.append(result)
                elif isinstance(result, Exception):
                    logger.debug(f"Ошибка при парсинге: {result}")
        except Exception as e:
            logger.error(f"Ошибка в асинхронном сборе: {e}")
        
        # Если ничего не нашли, создаем базовые прогнозы
        if not results:
            logger.info(f"Не удалось собрать гороскопы для {sign_rus}, создаю базовые")
            base_horoscopes = [
                f"🌟 **Общий прогноз для {sign_rus}**: Сегодня хороший день для начинаний. Стоит обратить внимание на новые возможности.",
                f"📊 **Астрологический анализ**: Влияние планет способствует гармонии в отношениях и успеху в делах.",
                f"💫 **Рекомендация дня**: Проявите гибкость в принятии решений и доверьтесь своей интуиции."
            ]
            results.extend(base_horoscopes)
        
        logger.info(f"Собрано {len(results)} гороскопов для {sign_rus}")
        return results

# --- ЛОГИКА РАСЧЕТА ---
def get_zodiac(date_obj: datetime) -> Tuple[str, str, str]:
    """Возвращает знак зодиака"""
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

def get_psychomatrix(birthdate_str: str):
    """Рассчитывает психоматрицу"""
    clean = birthdate_str.replace(".", "")
    digits = [int(d) for d in clean]
    
    w1 = sum(digits)
    w2 = sum(int(d) for d in str(w1))
    first_digit = int(clean[0])
    w3 = w1 - (2 * first_digit)
    w4 = sum(int(d) for d in str(abs(w3)))
    
    all_numbers = clean + str(w1) + str(w2) + str(w3) + str(w4)
    full_list = [int(d) for d in all_numbers if d.isdigit()]
    
    matrix = {}
    for i in range(1, 10):
        count = full_list.count(i)
        matrix[i] = str(i) * count if count > 0 else f"{i}0"
    
    special = []
    work_nums = [w1, w2, w3, w4]
    for sn in [11, 12, 22]:
        if sn in work_nums:
            special.append(str(sn))
    
    return matrix, special

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔮 Прогноз на день")],
            [KeyboardButton(text="🔢 Психоматрица")],
            [KeyboardButton(text="🎂 Мой профиль")]
        ],
        resize_keyboard=True
    )

# --- УТИЛИТЫ ---
async def download_image(url: str) -> Optional[bytes]:
    """Скачивает изображение"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.content
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
    return None

async def send_image_safely(message: types.Message, image_data: Optional[bytes], caption: str):
    """Безопасная отправка изображения"""
    try:
        if image_data and len(image_data) > 1000:
            photo = BufferedInputFile(image_data, filename="horoscope.jpg")
            await message.answer_photo(photo=photo, caption=caption)
            return True
        else:
            await message.answer(caption)
            return False
    except Exception as e:
        logger.error(f"Ошибка отправки изображения: {e}")
        await message.answer(caption)
        return False

async def ask_groq(prompt: str, system_prompt: str = None) -> str:
    """Запрос к Groq API"""
    try:
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        completion = await groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=1500
        )
        
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка Groq API: {e}")
        raise

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer(
        "✨ *Добро пожаловать в Оракул Рода!*\n\n"
        "Я создаю персонализированные прогнозы на основе:\n"
        "• Вашей даты рождения и знака зодиака\n"
        "• Актуальных гороскопов из нескольких источников\n"
        "• Вашей психоматрицы Пифагора\n"
        "• Анализа через искусственный интеллект\n\n"
        "Для начала, укажи свою дату рождения в формате *ДД.ММ.ГГГГ*:",
        parse_mode="Markdown"
    )
    await state.set_state(ProfileStates.waiting_for_birthdate)

@dp.message(ProfileStates.waiting_for_birthdate)
async def process_birthdate(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text, "%d.%m.%Y")
        
        if dt > datetime.now():
            await message.answer("Дата рождения не может быть в будущем. Попробуй снова:")
            return
        
        await state.update_data(birthdate=message.text)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female"),
             InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male")]
        ])
        
        await message.answer("Выбери свой пол:", reply_markup=keyboard)
        await state.set_state(ProfileStates.waiting_for_gender)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, используй формат *ДД.ММ.ГГГГ* (например, 15.05.1990)", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "женский" if "female" in callback.data else "мужской"
    
    data = await state.get_data()
    birthdate = data['birthdate']
    
    # Сохраняем в БД
    db = load_db()
    user_id = str(callback.from_user.id)
    
    db[user_id] = {
        "birthdate": birthdate,
        "gender": gender,
        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    save_db(db)
    
    # Рассчитываем знак зодиака
    dt = datetime.strptime(birthdate, "%d.%m.%Y")
    zodiac_full, zodiac_name, _ = get_zodiac(dt)
    
    await callback.message.edit_text(
        f"✅ *Профиль сохранен!*\n\n"
        f"📅 Дата рождения: {birthdate}\n"
        f"👤 Пол: {gender}\n"
        f"♊ Знак зодиака: {zodiac_full}\n\n"
        f"Теперь ты можешь получать персонализированные прогнозы!",
        parse_mode="Markdown"
    )
    
    await callback.message.answer("Выбери действие:", reply_markup=get_main_kb())
    await state.clear()

@dp.message(F.text == "🎂 Мой профиль")
async def show_profile(message: types.Message):
    user_data = load_db().get(str(message.from_user.id))
    
    if not user_data:
        await message.answer("Профиль не найден. Нажми /start для регистрации.")
        return
    
    dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
    zodiac_full, zodiac_name, _ = get_zodiac(dt)
    
    profile_text = (
        f"📋 *Твой профиль*\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"📅 Дата рождения: {user_data['birthdate']}\n"
        f"👤 Пол: {user_data['gender']}\n"
        f"♊ Знак зодиака: {zodiac_full}\n"
        f"📊 Число судьбы: {sum(int(d) for d in user_data['birthdate'].replace('.', '')) % 9 or 9}\n\n"
        f"*Зарегистрирован:* {user_data.get('registered_at', 'Неизвестно')}"
    )
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "🔮 Прогноз на день")
async def daily_horoscope(message: types.Message):
    """Главный обработчик ежедневного гороскопа"""
    user_data = load_db().get(str(message.from_user.id))
    
    if not user_data:
        await message.answer("Сначала настрой профиль через /start")
        return
    
    # Отправляем сообщение о начале
    status_msg = await message.answer("🔮 *Собираю актуальные прогнозы...*\n\nПодожди 10-15 секунд.", parse_mode="Markdown")
    
    try:
        # Получаем данные пользователя
        birthdate = user_data['birthdate']
        gender = user_data['gender']
        dt = datetime.strptime(birthdate, "%d.%m.%Y")
        zodiac_full, zodiac_name, zodiac_key = get_zodiac(dt)
        
        # Шаг 1: Сбор гороскопов из сети
        await status_msg.edit_text("📡 *Шаг 1/3:* Сбор прогнозов из нескольких источников...")
        
        collector = HoroscopeCollector()
        raw_horoscopes = await collector.collect_horoscopes(zodiac_key)
        
        if not raw_horoscopes:
            raw_horoscopes_text = "Не удалось собрать актуальные прогнозы из внешних источников. Буду использовать общие астрологические данные."
        else:
            raw_horoscopes_text = "\n\n".join(raw_horoscopes)
        
        # Шаг 2: Рассчитываем психоматрицу
        await status_msg.edit_text("🔢 *Шаг 2/3:* Анализ вашей психоматрицы...")
        
        matrix, special = get_psychomatrix(birthdate)
        matrix_view = f"| {matrix[1]} | {matrix[4]} | {matrix[7]} |\n| {matrix[2]} | {matrix[5]} | {matrix[8]} |\n| {matrix[3]} | {matrix[6]} | {matrix[9]} |"
        
        # Шаг 3: Генерация персонализированного прогноза через Groq
        await status_msg.edit_text("🧠 *Шаг 3/3:* Создание персонализированного прогноза...")
        
        current_date = datetime.now().strftime("%d.%m.%Y %A")
        
        system_prompt = (
            "Ты — опытный астролог-аналитик с 20-летним стажем. Твоя задача — проанализировать гороскопы из разных источников "
            "и создать единый, персонализированный прогноз для конкретного человека.\n\n"
            "**ТВОЙ СТИЛЬ:**\n"
            "1. Профессиональный, но понятный язык\n"
            "2. Конкретные рекомендации по сферам жизни\n"
            "3. Учет психоматрицы (квадрата Пифагора)\n"
            "4. Позитивный, поддерживающий тон\n"
            "5. Структурированный ответ с разделами\n\n"
            "**СТРУКТУРА ОТВЕТА:**\n"
            "1. 🌟 Общая тема дня (ключевая энергия дня)\n"
            "2. 💼 Карьера и финансы (конкретные рекомендации)\n"
            "3. ❤️ Личные отношения (советы по общению)\n"
            "4. 🌿 Здоровье и энергия (рекомендации по самочувствию)\n"
            "5. 🔮 Особое послание (на основе психоматрицы)\n"
            "6. 💫 Практический совет на день\n\n"
            "**ВАЖНО:**\n"
            "- Сравни прогнозы из разных источников\n"
            "- Выдели общие тенденции и противоречия\n"
            "- Учеть особенности знака зодиака\n"
            "- Интегрируй данные психоматрицы\n"
            "- Будь конкретен в рекомендациях\n\n"
            "В конце обязательно добавь: IMAGE_PROMPT: [детальное описание для генерации изображения на английском, связанное с ключевой темой дня, 10-15 слов]"
        )
        
        user_prompt = (
            f"Создай детальный персонализированный прогноз на {current_date}\n\n"
            f"**ДАННЫЕ ЧЕЛОВЕКА:**\n"
            f"- Дата рождения: {birthdate}\n"
            f"- Знак зодиака: {zodiac_full}\n"
            f"- Пол: {gender}\n\n"
            f"**ПСИХОМАТРИЦА (КВАДРАТ ПИФАГОРА):**\n{matrix_view}\n"
            f"Особые числа: {', '.join(special) if special else 'нет'}\n\n"
            f"**СОБРАННЫЕ ПРОГНОЗЫ ИЗ РАЗНЫХ ИСТОЧНИКОВ:**\n{raw_horoscopes_text}\n\n"
            f"**ТВОЯ ЗАДАЧА:**\n"
            f"1. Проанализируй ВСЕ предоставленные прогнозы из разных источников\n"
            f"2. Сравни их, найди общие тенденции и противоречия\n"
            f"3. Учеть особенности знака зодиака {zodiac_name}\n"
            f"4. Проанализируй психоматрицу:\n"
            f"   - Единицы ({matrix[1]}) — характер и воля\n"
            f"   - Восьмерки ({matrix[8]}) — связь с Родом\n"
            f"   - Особые числа: {', '.join(special) if special else 'отсутствуют'}\n"
            f"5. Создай уникальный, персонализированный прогноз в указанной структуре\n"
            f"6. Дай конкретные, практические рекомендации\n"
            f"7. Свяжи прогноз с кармическими задачами человека\n\n"
            f"**ФОРМАТ:** Используй Markdown для форматирования, эмодзи для разделов"
        )
        
        # Получаем ответ от AI
        ai_response = await ask_groq(user_prompt, system_prompt)
        
        # Извлекаем текст и промпт для изображения
        if "IMAGE_PROMPT:" in ai_response:
            horoscope_text, img_prompt_part = ai_response.split("IMAGE_PROMPT:")
            img_prompt = img_prompt_part.strip()
        else:
            horoscope_text = ai_response
            img_prompt = f"mystical astrology tarot card for {zodiac_name}, celestial energy, mystical atmosphere, digital art, fantasy style"
        
        # Удаляем статус-сообщение
        await status_msg.delete()
        
        # Генерация и отправка изображения
        encoded_prompt = quote(img_prompt, safe='')
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={random.randint(1, 99999)}"
        
        # Скачиваем и отправляем изображение
        image_data = await download_image(img_url)
        
        # Отправляем изображение с заголовком
        caption = f"✨ *Персональный прогноз для {zodiac_full}*\n📅 {current_date}"
        await send_image_safely(message, image_data, caption)
        
        # Отправляем текст прогноза
        final_text = (
            f"{horoscope_text}\n\n"
            f"---\n"
            f"📊 *Ваша психоматрица:*\n```\n{matrix_view}\n```\n"
            f"🔮 *Особые числа:* {', '.join(special) if special else 'Нет'}\n"
            f"🔄 *Создано на основе анализа {len(raw_horoscopes)} источников*\n"
            f"⭐ *Ваш знак:* {zodiac_full}"
        )
        
        await message.answer(final_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка в daily_horoscope: {e}", exc_info=True)
        
        try:
            await status_msg.delete()
        except:
            pass
        
        # Фолбэк: показываем пользователю простой прогноз
        dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
        zodiac_full, zodiac_name, _ = get_zodiac(dt)
        
        error_text = (
            f"✨ *Прогноз для {zodiac_full}*\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"🌟 **Общая тема дня**: Благоприятное время для самоанализа и планирования.\n\n"
            f"💼 *Карьера*: Сосредоточьтесь на завершении текущих задач.\n"
            f"❤️ *Отношения*: Проявляйте терпение и понимание в общении.\n"
            f"🌿 *Здоровье*: Уделите внимание физической активности и отдыху.\n\n"
            f"🔮 *Послание от Рода*: Прислушайтесь к внутреннему голосу.\n\n"
            f"💫 *Совет дня*: Составьте список приоритетов и следуйте ему.\n\n"
            f"_⚠️ Временные технические сложности. Полный анализ будет доступен позже._"
        )
        
        await message.answer(error_text, parse_mode="Markdown")

@dp.message(F.text == "🔢 Психоматрица")
async def show_psychomatrix(message: types.Message):
    """Показывает психоматрицу пользователя"""
    user_data = load_db().get(str(message.from_user.id))
    
    if not user_data:
        await message.answer("Сначала настрой профиль через /start")
        return
    
    birthdate = user_data['birthdate']
    matrix, special = get_psychomatrix(birthdate)
    
    # Создаем визуальное представление матрицы
    matrix_view = (
        f"┌───────┬───────┬───────┐\n"
        f"│   {matrix[1]:<3} │   {matrix[4]:<3} │   {matrix[7]:<3} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│   {matrix[2]:<3} │   {matrix[5]:<3} │   {matrix[8]:<3} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│   {matrix[3]:<3} │   {matrix[6]:<3} │   {matrix[9]:<3} │\n"
        f"└───────┴───────┴───────┘"
    )
    
    # Интерпретация цифр
    interpretations = {
        1: "Характер, воля",
        2: "Энергия, эмоции", 
        3: "Интерес к наукам",
        4: "Здоровье",
        5: "Логика и интуиция",
        6: "Склонность к труду",
        7: "Везение, удача",
        8: "Чувство долга, Род",
        9: "Память, ум"
    }
    
    matrix_text = "**Ваша психоматрица (Квадрат Пифагора):**\n```\n" + matrix_view + "\n```\n\n"
    matrix_text += "**Значение цифр:**\n"
    
    for i in range(1, 10):
        count = len(matrix[i].replace('0', ''))
        significance = "Низкая" if count == 0 else ("Средняя" if count == 1 else ("Высокая" if count == 2 else "Очень высокая"))
        matrix_text += f"{i} ({interpretations[i]}): {count} единиц - {significance}\n"
    
    if special:
        matrix_text += f"\n**Особые числа:** {', '.join(special)}\n"
        if '11' in special:
            matrix_text += "  • 11 - Число духовного учителя, древняя душа\n"
        if '12' in special:
            matrix_text += "  • 12 - Предназначение помогать людям через эзотерику\n"
        if '22' in special:
            matrix_text += "  • 22 - Мастер-строитель, организаторские способности\n"
    
    await message.answer(matrix_text, parse_mode="Markdown")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = (
        "🌟 *Оракул Рода - Помощь*\n\n"
        "**Доступные команды:**\n"
        "/start - Начать/изменить профиль\n"
        "/help - Эта справка\n\n"
        "**Основные функции:**\n"
        "• 🔮 Прогноз на день - Персональный астрологический прогноз\n"
        "• 🔢 Психоматрица - Ваш квадрат Пифагора\n"
        "• 🎂 Мой профиль - Информация о вас\n\n"
        "**Как это работает:**\n"
        "1. Собираю актуальные гороскопы из нескольких источников\n"
        "2. Анализирую вашу дату рождения и знак зодиака\n"
        "3. Рассчитываю психоматрицу Пифагора\n"
        "4. Использую AI для создания уникального прогноза\n"
        "5. Генерирую индивидуальную визуализацию\n\n"
        "⏱ *Обновление:* Ежедневные прогнозы обновляются каждый день"
    )
    
    await message.answer(help_text, parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Oracle Bot is running")

async def main():
    # Создаем веб-сервер для Render
    app = web.Application()
    app.router.add_get('/', handle)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Bot started on port {PORT}")
    
    # Запускаем бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
