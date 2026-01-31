import asyncio
import logging
import os
import sys
import json
import random
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

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

# --- КОЛЛЕКТОР ГОРОСКОПОВ БЕЗ BeautifulSoup ---
class HoroscopeCollector:
    def __init__(self):
        self.client = None
        self.zodiac_map = {
            'овен': ['aries', 'oven'],
            'телец': ['taurus', 'telec'],
            'близнецы': ['gemini', 'bliznecy'],
            'рак': ['cancer', 'rak'],
            'лев': ['leo', 'lev'],
            'дева': ['virgo', 'deva'],
            'весы': ['libra', 'vesy'],
            'скорпион': ['scorpio', 'skorpion'],
            'стрелец': ['sagittarius', 'strelec'],
            'козерог': ['capricorn', 'kozerog'],
            'водолей': ['aquarius', 'vodoley'],
            'рыбы': ['pisces', 'ryby']
        }
        
    async def init_client(self):
        if not self.client:
            self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close_client(self):
        if self.client:
            await self.client.aclose()
            self.client = None
    
    def _extract_text_from_html(self, html: str, patterns: List[str]) -> Optional[str]:
        """Извлекает текст из HTML с помощью регулярных выражений"""
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1)
                # Очищаем от HTML тегов
                text = re.sub(r'<[^>]+>', '', text)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 50:
                    return text[:2000]  # Ограничиваем длину
        return None
    
    async def fetch_horoscope_rambler(self, sign_rus: str) -> Optional[str]:
        """Парсинг с horoscopes.rambler.ru"""
        try:
            sign_en = self.zodiac_map.get(sign_rus.lower(), [sign_rus.lower()])[0]
            url = f"https://horoscopes.rambler.ru/{sign_en}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = await self.client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text
                
                # Паттерны для поиска текста гороскопа
                patterns = [
                    r'<div[^>]*class="[^"]*_1QBrg[^"]*"[^>]*>(.*?)</div>',
                    r'<article[^>]*>(.*?)</article>',
                    r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>'
                ]
                
                text = self._extract_text_from_html(html, patterns)
                if text:
                    return f"📰 **Rambler.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка Rambler: {e}")
        return None
    
    async def fetch_horoscope_mail(self, sign_rus: str) -> Optional[str]:
        """Парсинг с horo.mail.ru"""
        try:
            sign_en = self.zodiac_map.get(sign_rus.lower(), [sign_rus.lower()])[0]
            url = f"https://horo.mail.ru/prediction/{sign_en}/today/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = await self.client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text
                
                # Паттерны для Mail.ru
                patterns = [
                    r'<div[^>]*class="[^"]*article__item[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*article__text[^"]*"[^>]*>(.*?)</div>',
                    r'<p[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</p>'
                ]
                
                text = self._extract_text_from_html(html, patterns)
                if text:
                    return f"📧 **Mail.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка Mail.ru: {e}")
        return None
    
    async def fetch_horoscope_1001(self, sign_rus: str) -> Optional[str]:
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
            
            sign_en = sign_mapping.get(sign_rus.lower(), sign_rus.lower())
            url = f"https://1001goroskop.ru/?znak={sign_en}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = await self.client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text
                
                # Паттерны для 1001goroskop
                patterns = [
                    r'<div[^>]*class="[^"]*horoscope_text[^"]*"[^>]*>(.*?)</div>',
                    r'<p[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</p>'
                ]
                
                text = self._extract_text_from_html(html, patterns)
                if text:
                    return f"🔢 **1001goroskop.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка 1001goroskop: {e}")
        return None
    
    async def fetch_horoscope_joinfo_api(self, sign_rus: str) -> Optional[str]:
        """Используем API joinfo.ru"""
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
            
            sign_en = sign_mapping.get(sign_rus.lower(), sign_rus.lower())
            url = f"https://api.jinfo.ru/v1/horoscope/daily/{sign_en}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            response = await self.client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if 'text' in data:
                    text = data['text']
                    return f"📊 **JoInfo.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка JoInfo API: {e}")
        return None
    
    async def fetch_horoscope_generic(self, sign_rus: str) -> Optional[str]:
        """Резервный источник - генерируем базовый прогноз"""
        themes = [
            "Сегодня день для реализации планов. Сосредоточьтесь на главном.",
            "Эмоции могут быть на высоте. Найдите творческий выход для них.",
            "Хороший день для общения и новых знакомств.",
            "Время подведения итогов и планирования будущего.",
            "Проявите гибкость в решении задач - это приведет к успеху.",
            "День благоприятен для финансовых операций и переговоров."
        ]
        
        advice = [
            "Прислушайтесь к своей интуиции.",
            "Не бойтесь просить о помощи.",
            "Делайте перерывы в работе.",
            "Уделите время саморазвитию.",
            "Будьте открыты новым возможностям."
        ]
        
        text = f"{random.choice(themes)} {random.choice(advice)}"
        return f"🌟 **Общий прогноз**: {text}\n"
    
    async def collect_horoscopes(self, sign_rus: str) -> List[str]:
        """Сбор гороскопов из всех доступных источников"""
        await self.init_client()
        
        # Пробуем собрать из внешних источников
        sources = [
            self.fetch_horoscope_rambler(sign_rus),
            self.fetch_horoscope_mail(sign_rus),
            self.fetch_horoscope_1001(sign_rus),
            self.fetch_horoscope_joinfo_api(sign_rus)
        ]
        
        results = []
        for source in sources:
            try:
                result = await source
                if result:
                    results.append(result)
                    logger.info(f"Успешно получен гороскоп от источника")
            except Exception as e:
                logger.error(f"Ошибка в источнике: {e}")
                continue
        
        # Если ни один источник не сработал, используем генерацию
        if not results:
            generic = await self.fetch_horoscope_generic(sign_rus)
            if generic:
                results.append(generic)
        
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
        "• Интеллектуального анализа через AI\n\n"
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
        try:
            raw_horoscopes = await collector.collect_horoscopes(zodiac_key)
            logger.info(f"Собрано {len(raw_horoscopes)} гороскопов для {zodiac_name}")
        finally:
            await collector.close_client()
        
        if not raw_horoscopes:
            raw_horoscopes_text = "Не удалось собрать данные из внешних источников. Буду использовать общий прогноз."
        else:
            raw_horoscopes_text = "\n".join(raw_horoscopes)
        
        # Шаг 2: Рассчитываем психоматрицу
        await status_msg.edit_text("🔢 *Шаг 2/3:* Анализ вашей психоматрицы...")
        
        matrix, special = get_psychomatrix(birthdate)
        matrix_view = f"| {matrix[1]} | {matrix[4]} | {matrix[7]} |\n| {matrix[2]} | {matrix[5]} | {matrix[8]} |\n| {matrix[3]} | {matrix[6]} | {matrix[9]} |"
        
        # Шаг 3: Генерация персонализированного прогноза через Groq
        await status_msg.edit_text("🧠 *Шаг 3/3:* Создание персонализированного прогноза...")
        
        current_date = datetime.now().strftime("%d.%m.%Y %A")
        
        system_prompt = (
            "Ты — опытный астролог и аналитик. Твоя задача — проанализировать гороскопы из разных источников "
            "и создать единый, персонализированный прогноз.\n\n"
            "**Стиль ответа:**\n"
            "1. Профессиональный, но понятный язык\n"
            "2. Конкретные рекомендации по сферам жизни\n"
            "3. Позитивный, поддерживающий тон\n"
            "4. Структурированный ответ с разделами\n\n"
            "**Обязательные разделы:**\n"
            "1. Общая тема дня (2-3 предложения)\n"
            "2. Карьера и финансы\n"
            "3. Личные отношения\n"
            "4. Здоровье и энергия\n"
            "5. Совет дня\n\n"
            "В конце добавь IMAGE_PROMPT: [описание для генерации изображения на английском, связанное с ключевой темой дня, 10-15 слов]"
        )
        
        user_prompt = (
            f"Создай персонализированный ежедневный прогноз на {current_date}\n\n"
            f"**ДАННЫЕ ЧЕЛОВЕКА:**\n"
            f"- Дата рождения: {birthdate}\n"
            f"- Знак зодиака: {zodiac_full}\n"
            f"- Пол: {gender}\n\n"
            f"**СОБРАННЫЕ ПРОГНОЗЫ ИЗ СЕТИ:**\n{raw_horoscopes_text}\n\n"
            f"**МАТРИЦА ПИФАГОРА:**\n{matrix_view}\n"
            f"Особые числа: {', '.join(special) if special else 'нет'}\n\n"
            f"**ИНСТРУКЦИЯ:**\n"
            f"1. Проанализируй ВСЕ предоставленные прогнозы из разных источников\n"
            f"2. Выдели ОБЩИЕ темы и тенденции\n"
            f"3. Если есть противоречия, укажи на них и дай взвешенную рекомендацию\n"
            f"4. Учеть особенности знака зодиака и даты рождения\n"
            f"5. Дай КОНКРЕТНЫЕ, практические рекомендации\n"
            f"6. Структурируй ответ по указанным разделам\n\n"
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
            img_prompt = f"mystical astrology tarot card for {zodiac_name}, celestial energy, mystical atmosphere, digital art"
        
        # Удаляем статус-сообщение
        await status_msg.delete()
        
        # Генерация и отправка изображения
        encoded_prompt = re.sub(r'[^\w\s-]', '', img_prompt).replace(' ', '%20')
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={random.randint(1, 99999)}"
        
        # Скачиваем и отправляем изображение
        image_data = await download_image(img_url)
        
        # Отправляем изображение с заголовком
        caption = f"✨ *Ежедневный прогноз для {zodiac_full}*\n📅 {current_date}"
        await send_image_safely(message, image_data, caption)
        
        # Отправляем текст прогноза
        final_text = (
            f"{horoscope_text}\n\n"
            f"---\n"
            f"📊 *Основано на анализе {len(raw_horoscopes)} источников*\n"
            f"🔄 *Обновлено:* {datetime.now().strftime('%H:%M')}\n"
            f"⭐ *Ваш знак:* {zodiac_full}"
        )
        
        await message.answer(final_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка в daily_horoscope: {e}")
        
        try:
            await status_msg.delete()
        except:
            pass
        
        # Показываем пользователю простой прогноз
        dt = datetime.strptime(user_data['birthdate'], "%d.%m.%Y")
        zodiac_full, zodiac_name, _ = get_zodiac(dt)
        
        error_text = (
            f"✨ *Прогноз для {zodiac_full}*\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"Сегодня благоприятный день для саморазвития и планирования.\n\n"
            f"💼 *Карьера:* Сосредоточьтесь на текущих задачах\n"
            f"❤️ *Отношения:* Будьте открыты для общения\n"
            f"🌿 *Здоровье:* Уделите время отдыху\n\n"
            f"_⚠️ Полный анализ временно недоступен. Попробуйте позже._"
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
        matrix_text += f"{i} ({interpretations[i]}): {count} единиц\n"
    
    if special:
        matrix_text += f"\n**Особые числа:** {', '.join(special)}\n"
        if '11' in special:
            matrix_text += "11 - Духовный учитель\n"
        if '12' in special:
            matrix_text += "12 - Помощь людям через эзотерику\n"
        if '22' in special:
            matrix_text += "22 - Организаторские способности\n"
    
    await message.answer(matrix_text, parse_mode="Markdown")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = (
        "🌟 *Оракул Рода - Помощь*\n\n"
        "**Доступные команды:**\n"
        "/start - Начать/изменить профиль\n"
        "/help - Эта справка\n\n"
        "**Основные функции:**\n"
        "• 🔮 Прогноз на день - Персонализированный гороскоп\n"
        "• 🔢 Психоматрица - Ваш квадрат Пифагора\n"
        "• 🎂 Мой профиль - Информация о вас\n\n"
        "**Как это работает:**\n"
        "1. Я собираю актуальные гороскопы из 4+ источников\n"
        "2. Анализирую вашу психоматрицу по дате рождения\n"
        "3. Использую AI для создания уникального прогноза\n"
        "4. Генерирую индивидуальную визуализацию\n\n"
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
