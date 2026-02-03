import asyncio
import logging
import os
import sys
import json
import random
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

# --- ИНИЦИАЛИЗАЦИЯ И ЛОГИ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 10000))

if not TOKEN or not GROQ_API_KEY:
    sys.exit("Критическая ошибка: Переменные BOT_TOKEN или GROQ_API_KEY не найдены!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

DB_FILE = "users_data.json"

# --- ДАННЫЕ ИЗ ФАЙЛОВ (ИНТЕРПРЕТАЦИИ) ---

# Тексты из values.ts
MATRIX_TEXTS = {
    "1": "Женщины: деспот. При рождении милосердные, альтруисты, быстро адаптируются к миру. Необходимо научиться проживать эмоции (крик, удары, плевки). Мужчины: крайне любит отыгрываться на других, абьюзит семью, если не нашел путь.",
    "11": "Женщины: семейная, мягкая, уступчивая, покладистая. Мужчины: много страхов, мягкий характер, часто симбиоз с мамой.",
    "111": "Женщины: врожденная мудрость, интуиция. Мужчины: хороший семьянин, но нужен стимул (пинок) от жены.",
    "1111": "Женщины: мужская сила характера, карьеристка. Мужчины: идеальный характер, 'Пчелка', лидер, дипломат.",
    "11111": "Женщины: тираны, продавливают мир. Мужчины: поздно взрослеют, огромная сила распаковывается после 30 лет.",
    "2": "Нейтрал/дефицит энергии. Энергия уходит скачками. В 45-50 лет возможен сильный спад.",
    "22": "Донор энергии. Нужно двигаться, полезно делиться энергией. Долгожители.",
    "222": "Экстрасенсорные способности. Нельзя завидовать и ревновать. Быстро проваливаются в стресс, но и быстро восстанавливаются.",
    "2222": "Профицит энергии. Обязаны быть в постоянном движении, иначе энергия разрушает изнутри (депрессии).",
    "22222": "Мощная энергия, 'ведьмаки'. Тотальный запрет на ревность и рассказы о планах.",
    "20": "Истинные вампиры (нет двоек). Нужен спорт, природа, дыхательные практики для набора сил.",
    "3": "Норма. Разумный, реалистичный, практичный подход.",
    "33": "Аналитический ум, креатив, но склонность к накопительству ('Плюшкин').",
    "333": "Видят мир через призму красоты. Творчество.",
    "3333": "Много страхов, особенно за репутацию. Фантазеры.",
    "30": "Страх потерять деньги. Нужно учиться на своем опыте, меньше анализировать, больше делать.",
    "4": "Здоровье среднее, но есть ресурсы. Важно не копить обиды.",
    "44": "Крепкое здоровье, высокая сексуальная энергия. Дар продолжения рода.",
    "444": "Любители изысков, могут влиять на людей своей верой во что-то.",
    "40": "Нет врожденного ресурса здоровья/рода. Нужно следить за телом, планировать детей заранее.",
    "5": "Развитая интуиция и логика. Мужчины — надежные 'мужики'.",
    "55": "Все ресурсы идут через детей. Тотальный запрет на аборты/отказ от детей.",
    "555": "Сбой в родовой программе любви. Задача: всегда выбирать любовь и опираться только на себя.",
    "50": "Тяжелый показатель. У женщин — необходимость социума. У мужчин — ранимость, попытка доказать мужественность.",
    "6": "Умение работать руками. Мастера, заземленные люди. Могут доносить информацию.",
    "66": "Манипуляторы, дипломаты. 'Золотые руки'.",
    "666": "Кодировщики на страхи. Сбывается то, чего боятся. Нужно работать с мышлением.",
    "60": "Нет шестерок. Чувство вины, 'я всем должен'. Часто проблемы с ручным трудом.",
    "7": "Мощный ангел-хранитель. До 33 лет многое сходит с рук.",
    "77": "Везунчики. Родовая удача. Важно благодарить за все.",
    "777": "Феи удачи. Нужно делиться удачей с другими, иначе канал закроется.",
    "70": "Временная удача. В 26, 33, 36 лет проверки. Нужно нарабатывать удачу благодарностью.",
    "8": "Чувство долга. Привязанность к семье. Родовая история.",
    "88": "Служение людям. Задача — быть наставником, социально активным.",
    "888": "Гуру, великие учителя. Могут быть тираничны в семье ради служения обществу.",
    "80": "Свободолюбивые. Нарушена связь с родом. Нельзя иметь претензии к родителям.",
    "9": "Память нужно тренировать. Риск забывчивости к старости.",
    "99": "Норма, хорошая память. Легко учатся.",
    "999": "Яснознание. Должны передавать знания через чувства.",
    "9999": "Код Мага. Трансформаторы судеб. Обязаны помогать людям.",
}

TASKS_TEXTS = {
    "1": "Я, лидерство. Самореализация без деспотизма.",
    "2": "Дипломатия и род. Задача объединять людей.",
    "10": "Усиленная задача лидера.",
    "11": "Духовный учитель, лидер просветитель. Нести свет.",
    "12": "Служение человечеству через знания и эзотерику.",
    "22": "Мастер-строитель. Создание глобальных проектов и сверхдоходы."
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ---
def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- ЛОГИКА МАТРИЦЫ (ИЗ App.tsx) ---
def split_int(value) -> List[int]:
    return [int(x) for x in str(value).replace('.', '')]

def string_sum(number: int) -> int:
    return sum(int(d) for d in str(number))

def calculate_matrix(birthdate_str: str):
    # Логика в точности повторяет App.tsx
    nums = split_int(birthdate_str)
    dt = datetime.strptime(birthdate_str, "%d.%m.%Y")
    
    # 1-е число: Сумма всех цифр даты
    first = sum(nums)
    # 2-е число: Сумма цифр первого числа
    second = string_sum(first)
    
    # 3-е число: 
    if dt.year >= 2000:
        third = first + 19
    else:
        # Для < 2000: из первого числа вычесть (первую цифру дня * 2)
        day_digits = split_int(dt.day)
        # Если первая цифра дня 0 (например 05), берется следующая (5)
        subtractor = day_digits[0] if day_digits[0] != 0 else day_digits[1] if len(day_digits) > 1 else day_digits[0]
        third = first - (subtractor * 2)
        
    # 4-е число: Сумма цифр третьего
    fourth = string_sum(third)
    
    # Полный массив для подсчета квадрата
    full_array = nums + split_int(first) + split_int(second) + split_int(third) + split_int(fourth)
    if dt.year >= 2000:
        full_array += [1, 9] # Константа 19
        
    return {
        "first": first, "second": second, "third": third, "fourth": fourth,
        "full_array": full_array, "year": dt.year
    }

def get_matrix_interpretation(number: int, full_array: List[int]) -> str:
    count = full_array.count(number)
    if count == 0:
        key = f"{number}0"
    elif count > 5:
        # По логике App.tsx: filteredArray.slice(5).join('')
        # Если 6 единиц, slice(5) оставит одну единицу -> ключ "1"
        key = str(number) * (count - 5)
    else:
        key = str(number) * count
    
    return MATRIX_TEXTS.get(key, "Нет описания для данной комбинации.")

# --- ПАРСЕР ГОРОСКОПОВ ---
class HoroscopeCollector:
    def __init__(self):
        self.map = {'овен':'aries','телец':'taurus','близнецы':'gemini','рак':'cancer','лев':'leo','дева':'virgo','весы':'libra','скорпион':'scorpio','стрелец':'sagittarius','козерог':'capricorn','водолей':'aquarius','рыбы':'pisces'}
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    async def fetch(self, sign_rus: str):
        sign = self.map.get(sign_rus.lower())
        results = []
        async with httpx.AsyncClient(headers=self.headers, timeout=10.0) as client:
            # Mail.ru
            try:
                r = await client.get(f"https://horo.mail.ru/prediction/{sign}/today/")
                soup = BeautifulSoup(r.text, 'lxml')
                text = soup.find('div', class_='article__text').get_text(strip=True)
                results.append(f"Mail.ru: {text[:300]}...")
            except: pass
            
            # 1001 Goroskop
            try:
                r = await client.get(f"https://1001goroskop.ru/?znak={sign}")
                soup = BeautifulSoup(r.content, 'lxml', from_encoding='utf-8')
                text = soup.find('div', itemprop='description').get_text(strip=True)
                results.append(f"1001: {text[:300]}...")
            except: pass
            
        return results

# --- СОСТОЯНИЯ ---
class States(StatesGroup):
    date = State()
    gender = State()

# --- ВСПОМОГАТЕЛЬНОЕ: СКАЧИВАНИЕ КАРТИНКИ ---
async def download_image(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                return resp.content
    except Exception as e:
        logger.error(f"Image error: {e}")
    return None

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer("Привет! Введи дату рождения (ДД.ММ.ГГГГ):")
    await state.set_state(States.date)

@dp.message(States.date)
async def process_date(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
        await state.update_data(date=message.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="М", callback_data="g_m"),
            InlineKeyboardButton(text="Ж", callback_data="g_f")
        ]])
        await message.answer("Твой пол:", reply_markup=kb)
        await state.set_state(States.gender)
    except:
        await message.answer("Ошибка формата. Нужно ДД.ММ.ГГГГ")

@dp.callback_query(F.data.startswith("g_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    gender = "мужской" if callback.data == "g_m" else "женский"
    db = load_db()
    db[str(callback.from_user.id)] = {"date": data['date'], "gender": gender}
    save_db(db)
    await callback.message.answer("Готово! Используй меню.", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔮 Прогноз на день"), KeyboardButton(text="🔢 Психоматрица")]],
        resize_keyboard=True
    ))
    await state.clear()

@dp.message(F.text == "🔢 Психоматрица")
async def show_matrix(message: types.Message):
    user = load_db().get(str(message.from_user.id))
    if not user: return
    
    m = calculate_matrix(user['date'])
    fa = m['full_array']
    
    def c(n): return (str(n) * fa.count(n)) if fa.count(n) > 0 else "—"
    
    grid = (
        f"┌───────┬───────┬───────┐\n"
        f"│ {c(1):<5} │ {c(4):<5} │ {c(7):<5} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│ {c(2):<5} │ {c(5):<5} │ {c(8):<5} │\n"
        f"├───────┼───────┼───────┤\n"
        f"│ {c(3):<5} │ {c(6):<5} │ {c(9):<5} │\n"
        f"└───────┴───────┴───────┘"
    )
    
    text = f"🔢 **Твоя Матрица Пифагора**\n\n`{grid}`\n\n"
    text += f"💡 **Характер (1):** {get_matrix_interpretation(1, fa)}\n\n"
    text += f"⚡️ **Энергия (2):** {get_matrix_interpretation(2, fa)}\n\n"
    text += f"🌳 **Род (8):** {get_matrix_interpretation(8, fa)}"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔮 Прогноз на день")
async def daily_forecast(message: types.Message):
    user = load_db().get(str(message.from_user.id))
    if not user: return
    
    status_msg = await message.answer("🔮 Считываю информационное поле...")
    
    try:
        # 1. Знаки и Матрица
        dt = datetime.strptime(user['date'], "%d.%m.%Y")
        # Упрощенное определение знака
        zodiac_list = [
            (1, 20, "Козерог"), (2, 19, "Водолей"), (3, 20, "Рыбы"), (4, 20, "Овен"),
            (5, 21, "Телец"), (6, 21, "Близнецы"), (7, 23, "Рак"), (8, 23, "Лев"),
            (9, 23, "Дева"), (10, 23, "Весы"), (11, 22, "Скорпион"), (12, 22, "Стрелец"), (12, 31, "Козерог")
        ]
        z_name = next(name for m, d, name in zodiac_list if (dt.month < m) or (dt.month == m and dt.day <= d))
        
        m_data = calculate_matrix(user['date'])
        
        # 2. Сбор гороскопов
        collector = HoroscopeCollector()
        raw_horos = await collector.fetch(z_name)
        horo_context = "\n".join(raw_horos)
        
        # 3. Запрос к AI
        prompt = f"""
        Сегодня {datetime.now().strftime('%d.%m.%Y')}. Составь мистический прогноз.
        Человек: {z_name}, пол {user['gender']}.
        Особенности матрицы: Характер '{get_matrix_interpretation(1, m_data['full_array'])[:100]}', Энергия '{get_matrix_interpretation(2, m_data['full_array'])[:100]}'.
        Гороскопы дня: {horo_context}
        
        Напиши кратко: фон дня, отношения, работа и совет по матрице.
        В конце добавь IMAGE_PROMPT: [описание магической карты таро для этого дня на англ, 10 слов]
        """
        
        res = await groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        full_text = res.choices[0].message.content
        
        # 4. Изображение
        text_part = full_text
        photo_bytes = None
        if "IMAGE_PROMPT:" in full_text:
            text_part, img_p = full_text.split("IMAGE_PROMPT:")
            url = f"https://image.pollinations.ai/prompt/{quote(img_p.strip())}?width=800&height=1000&nologo=true&seed={random.randint(1,999)}"
            photo_bytes = await download_image(url)

        # 5. Отправка
        if photo_bytes:
            await message.answer_photo(BufferedInputFile(photo_bytes, "daily.jpg"), caption=text_part[:1024], parse_mode="Markdown")
            await status_msg.delete()
        else:
            await status_msg.edit_text(text_part, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"Global error: {e}")
        await status_msg.edit_text("✨ Сегодня звезды туманны. Попробуйте позже.")

# --- ВЕБ-СЕРВЕР ---
async def web_handle(request): return web.Response(text="Bot is live")

async def main():
    app = web.Application()
    app.router.add_get('/', web_handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
