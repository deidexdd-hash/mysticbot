import os
import io
import logging
from datetime import datetime

import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from matrix import calculate_matrix
from horoscope import (
    build_matrix_text,
    build_tasks_text,
    daily_horoscope,
)

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Токен ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не задан в окружении!")
    exit(1)

# --- Инициализация бота и диспетчера ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# --- Обработчик команды /start ---
@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 Персональный оракул\n\n"
        "Отправь дату рождения в формате:\n"
        "DD.MM.YYYY"
    )


# --- Функция безопасной отправки изображения ---
async def send_image_safely(message: types.Message, url: str, caption: str = ""):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            image_bytes = io.BytesIO(resp.content)
            image_bytes.name = "image.png"
            await message.answer_photo(photo=InputFile(image_bytes), caption=caption)
    except httpx.RequestError as e:
        logger.error(f"Ошибка запроса изображения: {e}")
        await message.answer("❌ Не удалось соединиться с сервером изображений.")
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        await message.answer("❌ Произошла ошибка при обработке изображения.")


# --- Обработчик текста с датой ---
@dp.message()
async def handle_date(message: types.Message):
    try:
        date_str = message.text.strip()
        datetime.strptime(date_str, "%d.%m.%Y")

        matrix_data = calculate_matrix(date_str)

        text = (
            daily_horoscope(matrix_data)
            + "\n\n"
            + build_tasks_text(matrix_data)
            + "\n"
            + build_matrix_text(matrix_data)
        )

        await message.answer(text)

        # Пример безопасной отправки изображения
        image_url = "https://image.pollinations.ai/prompt/mystical%20tarot%20card.png"
        await send_image_safely(message, image_url, caption="Вот ваш прогноз 🔮")

    except ValueError:
        await message.answer("❌ Ошибка.\nИспользуй формат DD.MM.YYYY")
    except Exception as e:
        logger.error(f"Ошибка при обработке даты: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса.")


# --- Основная функция запуска ---
async def main():
    logger.info("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
