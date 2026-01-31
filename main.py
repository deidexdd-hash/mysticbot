import asyncio
import logging
import os
import sys
import json
import random
import re
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Optional
from urllib.parse import quote

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web, ClientSession, ClientTimeout
from dotenv import load_dotenv
from groq import AsyncGroq
from bs4 import BeautifulSoup

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

# --- КОЛЛЕКТОР ГОРОСКОПОВ ---
class HoroscopeCollector:
    def __init__(self):
        self.session = None
        self.zodiac_signs = {
            'овен': ['aries', 'oven'],
            'телец': ['taurus', 'telec'],
            'близнецы': ['gemini', 'bliznecy', 'bliznetsy'],
            'рак': ['cancer', 'rak'],
            'лев': ['leo', 'lev'],
            'дева': ['virgo', 'deva'],
            'весы': ['libra', 'vesy'],
            'скорпион': ['scorpio', 'skorpion'],
            'стрелец': ['sagittarius', 'strelets', 'strelec'],
            'козерог': ['capricorn', 'kozerog'],
            'водолей': ['aquarius', 'vodoley'],
            'рыбы': ['pisces', 'ryby']
        }
        
    async def init_session(self):
        if not self.session:
            timeout = ClientTimeout(total=15)
            self.session = ClientSession(timeout=timeout)
    
    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None
    
    async def fetch_horoscope_rambler(self, sign_rus: str) -> Optional[str]:
        """Парсинг с horoscopes.rambler.ru"""
        try:
            sign_en = self.zodiac_signs.get(sign_rus.lower(), [sign_rus.lower()])[0]
            url = f"https://horoscopes.rambler.ru/{sign_en}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем основной текст гороскопа
                    content_div = soup.find('div', {'class': '_1QBrg'})
                    if content_div:
                        paragraphs = content_div.find_all('p')
                        if paragraphs:
                            text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                            return f"📰 **Rambler.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка парсинга Rambler: {e}")
        return None
    
    async def fetch_horoscope_mail(self, sign_rus: str) -> Optional[str]:
        """Парсинг с horo.mail.ru"""
        try:
            sign_en = self.zodiac_signs.get(sign_rus.lower(), [sign_rus.lower()])[0]
            url = f"https://horo.mail.ru/prediction/{sign_en}/today/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем блок с прогнозом
                    article_div = soup.find('div', {'class': 'article__text'})
                    if article_div:
                        paragraphs = article_div.find_all('p')
                        if paragraphs:
                            text = ' '.join([p.get_text(strip=True) for p in paragraphs[:3]])
                            return f"📧 **Mail.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка парсинга Mail.ru: {e}")
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
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем текст гороскопа
                    content_div = soup.find('div', {'class': 'horoscope_text'})
                    if content_div:
                        text = content_div.get_text(strip=True)
                        return f"🔢 **1001goroskop.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка парсинга 1001goroskop: {e}")
        return None
    
    async def fetch_horoscope_astromeridian(self, sign_rus: str) -> Optional[str]:
        """Парсинг с astromeridian.ru"""
        try:
            sign_ru_for_url = sign_rus.lower()
            url = f"https://www.astromeridian.ru/horoscope/{sign_ru_for_url}.html"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Ищем блок с ежедневным гороскопом
                    for tag in soup.find_all(['p', 'div']):
                        text = tag.get_text(strip=True)
                        if 'сегодня' in text.lower() and len(text) > 100:
                            return f"🌙 **Astromeridian.ru**: {text}\n"
        except Exception as e:
            logger.error(f"Ошибка парсинга Astromeridian: {e}")
        return None
    
    async def fetch_horoscope_joinfo(self, sign_rus: str) -> Optional[str]:
        """API-подобный запрос к joinfo.ru"""
        try:
            sign_mapping = {
                'овен': 'oven',
                'телец': 'telec',
                'близнецы': 'bliznecy',
                'рак': 'rak',
                'лев': 'lev',
                'дева': 'deva',
                'весы': 'vesy',
                'скорпион': 'skorpion',
                'стрелец': 'strelec',
                'козерог': 'kozerog',
                'водолей': 'vodolei',
                'рыбы': 'ryby'
            }
            
            sign_key = sign_mapping.get(sign_rus.lower(), sign_rus.lower())
            url = f"https://api.jinfo.ru/v1/horoscope/daily/{sign_key}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'text' in data:
                        return f"📊 **JoInfo.ru**: {data['text']}\n"
        except Exception as e:
            logger.error(f"Ошибка парсинга JoInfo: {e}")
        return None
    
    async def collect_all_horoscopes(self, sign_rus: str) -> List[str]:
        """Сбор всех доступных гороскопов"""
        await self.init_session()
        
        tasks = [
            self.fetch_horoscope_rambler(sign_rus),
            self.fetch_horoscope_mail(sign_rus),
            self.fetch_horoscope_1001(sign_rus),
            self.fetch_horoscope_astromeridian(sign_rus),
            self.fetch_horoscope_joinfo(sign_rus)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for result in results:
            if isinstance(result, str) and len(result.strip()) > 50:
                valid_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Ошибка при сборе гороскопа: {result}")
        
        logger.info(f"Собрано {len(valid_results)} гороскопов для {sign_rus}")
        return valid_results

# --- ЛОГИКА РАСЧЕТА ---
def get_zodiac(date_obj: datetime) -> tuple:
    """Возвращает знак зодиака и символ"""
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
    """Рассчитывает психоматрицу по дате рождения"""
    clean = birthdate_str.replace(".", "")
    digits = [int(d) for d in clean]
    
    # 1 рабочее число
    w1 = sum(digits)
    # 2 рабочее число
    w2 = sum(int(d) for d in str(w1))
    # 3 рабочее число
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
    
    # Специальные числа
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
    """Скачивает изображение по URL"""
    timeout = ClientTimeout(total=20)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
    return None

async def send_image_safely(message: types.Message, image_data: bytes, caption: str):
    """Безопасная отправка изображения"""
    try:
        if image_data and len(image_data) > 1000:  # Проверяем что изображение не пустое
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
            temperature=0.8,
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
        "• Вашей даты рождения\n"
        "• Актуальных гороскопов из 5+ источников\n"
        "• Вашей психоматрицы Пифагора\n\n"
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
    zodiac_full, zodiac_name, zodiac_key = get_zodiac(dt)
    
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
        f"*Зарегистрирован:* {user_data.get('registered_at', 'Неизвестно')}\n\n"
        f"Используй /start чтобы изменить данные."
    )
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(F.text == "🔮 Прогноз на день")
async def daily_horoscope(message: types.Message):
    """Главный обработчик ежедневного гороскопа"""
    user_data = load_db().get(str(message.from_user.id))
    
    if not user_data:
        await message.answer("Сначала настрой профиль через /start")
        return
    
    # Отправляем сообщение о начале сбора данных
    status_msg = await message.answer("🔮 *Собираю актуальные прогнозы...*\n\nЭто займет 10-15 секунд.", parse_mode="Markdown")
    
    try:
        # Получаем данные пользователя
        birthdate = user_data['birthdate']
        gender = user_data['gender']
        dt = datetime.strptime(birthdate, "%d.%m.%Y")
        zodiac_full, zodiac_name, zodiac_key = get_zodiac(dt)
        
        # Шаг 1: Сбор гороскопов из сети
        await status_msg.edit_text("📡 *Шаг 1/3:* Сбор прогнозов из 5+ источников...")
        
        collector = HoroscopeCollector()
        raw_horoscopes = await collector.collect_all_horoscopes(zodiac_key)
        await collector.close_session()
        
        if not raw_horoscopes:
            await status_msg.edit_text("⚠️ *Не удалось собрать прогнозы из сети*\nСоздаю универсальный прогноз...")
            raw_horoscopes_text = "Данные из внешних источников временно недоступны."
        else:
            raw_horoscopes_text = "\n".join(raw_horoscopes[:5])  # Берем до 5 источников
        
        # Шаг 2: Рассчитываем психоматрицу
        await status_msg.edit_text("🔢 *Шаг 2/3:* Анализ вашей психоматрицы...")
        
        matrix, special = get_psychomatrix(birthdate)
        matrix_view = f"| {matrix[1]} | {matrix[4]} | {matrix[7]} |\n| {matrix[2]} | {matrix[5]} | {matrix[8]} |\n| {matrix[3]} | {matrix[6]} | {matrix[9]} |"
        
        # Шаг 3: Генерация персонализированного прогноза через Groq
        await status_msg.edit_text("🧠 *Шаг 3/3:* Создание персонализированного прогноза...")
        
        current_date = datetime.now().strftime("%d.%m.%Y %A")
        
        system_prompt = (
            "Ты — опытный астролог и нумеролог, специализирующийся на персонализированных прогнозах. "
            "Ты анализируешь гороскопы из разных источников, учитываешь психоматрицу Пифагора и создаешь "
            "уникальный, точный прогноз для конкретного человека.\n\n"
            "**Твой стиль:**\n"
            "1. Профессиональный, но понятный язык\n"
            "2. Конкретные рекомендации по сферам жизни\n"
            "3. Учет числовой матрицы и особых чисел\n"
            "4. Позитивный, поддерживающий тон\n"
            "5. Структурированный ответ с разделами\n\n"
            "**Обязательные разделы в ответе:**\n"
            "1. Общая тема дня\n"
            "2. Карьера и финансы\n"
            "3. Личные отношения\n"
            "4. Здоровье и энергия\n"
            "5. Совет дня от Рода\n"
            "6. Особое указание (по матрице)\n\n"
            "В конце добавь IMAGE_PROMPT: [детальное описание картинки на английском для визуализации прогноза, связанное с ключевой темой дня]"
        )
        
        user_prompt = (
            f"Создай персонализированный ежедневный прогноз на {current_date}\n\n"
            f"**ДАННЫЕ ЧЕЛОВЕКА:**\n"
            f"- Дата рождения: {birthdate}\n"
            f"- Знак зодиака: {zodiac_full}\n"
            f"- Пол: {gender}\n"
            f"- Матрица Пифагора:\n{matrix_view}\n"
            f"- Особые числа: {', '.join(special) if special else 'Нет'}\n\n"
            f"**СОБРАННЫЕ ПРОГНОЗЫ ИЗ СЕТИ:**\n{raw_horoscopes_text}\n\n"
            f"**ИНСТРУКЦИЯ:**\n"
            f"1. Проанализируй ВСЕ предоставленные прогнозы из разных источников\n"
            f"2. Выдели ОБЩИЕ темы и ПРОТИВОРЕЧИЯ между источниками\n"
            f"3. Учеть особенности матрицы:\n"
            f"   - Единицы ({matrix[1]}) - характер, воля\n"
            f"   - Восьмерки ({matrix[8]}) - связь с Родом, долг\n"
            f"   - Особые числа: {special if special else 'нет'}\n"
            f"4. Дай КОНКРЕТНЫЕ рекомендации\n"
            f"5. Свяжи с кармическими задачами человека\n"
            f"6. Будь реалистичным - укажи и вызовы, и возможности\n\n"
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
            img_prompt = f"mystical astrology tarot card for {zodiac_name}, celestial energy, detailed, mystical atmosphere, digital art"
        
        # Удаляем статус-сообщение
        await status_msg.delete()
        
        # Шаг 4: Генерация и отправка изображения
        img_url = f"https://image.pollinations.ai/prompt/{quote(img_prompt)}?width=1024&height=1024&nologo=true&seed={random.randint(1, 99999)}"
        
        # Скачиваем и отправляем изображение
        image_data = await download_image(img_url)
        
        # Отправляем изображение с заголовком
        caption = f"✨ *Ежедневный прогноз для {zodiac_full}*\n📅 {current_date}"
        await send_image_safely(message, image_data, caption)
        
        # Отправляем текст прогноза
        final_text = (
            f"{horoscope_text}\n\n"
            f"---\n"
            f"📊 *Ваша матрица:*\n`{matrix_view}`\n"
            f"🔮 *Особые числа:* {', '.join(special) if special else 'Нет'}\n"
            f"🔄 *Прогноз обновлен:* {datetime.now().strftime('%H:%M')}\n\n"
            f"_Прогноз создан на основе анализа {len(raw_horoscopes)} источников_"
        )
        
        await message.answer(final_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка в daily_horoscope: {e}")
        
        try:
            await status_msg.delete()
        except:
            pass
        
        error_text = (
            "⚠️ *Произошла ошибка при создании прогноза*\n\n"
            "Попробуйте снова через несколько минут. \n"
            "Или используйте другие функции бота:\n"
            "- /start - изменить профиль\n"
            "- 🔢 Психоматрица - узнать свою матрицу\n"
            f"\nОшибка: {str(e)[:100]}..."
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
    
    matrix_text += f"\n**Дата рождения:** {birthdate}"
    
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
        "1. Я собираю актуальные гороскопы из 5+ источников\n"
        "2. Анализирую вашу психоматрицу по дате рождения\n"
        "3. Использую AI для создания уникального прогноза\n"
        "4. Генерирую визуализацию\n\n"
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
