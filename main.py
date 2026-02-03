import os
import io
import logging
from datetime import datetime

import requests
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

from matrix import calculate_matrix
from horoscope import (
    build_matrix_text,
    build_tasks_text,
    daily_horoscope,
)

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Токен бота ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN не задан в окружении!")
    exit(1)

# --- Обработчики команд ---
def start(update: Update, context):
    update.message.reply_text(
        "🔮 Персональный оракул\n\n"
        "Отправь дату рождения в формате:\n"
        "DD.MM.YYYY"
    )

# --- Функция безопасной отправки изображения ---
def send_image_safely(update: Update, image_url: str, caption: str = ""):
    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image_bytes = io.BytesIO(resp.content)
        image_bytes.name = "image.png"  # Telegram требует имя файла
        update.message.reply_photo(photo=InputFile(image_bytes), caption=caption)
    except requests.RequestException as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        update.message.reply_text("❌ Не удалось загрузить изображение. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        update.message.reply_text("❌ Произошла ошибка при обработке изображения.")

# --- Обработчик текста с датой ---
def handle_date(update: Update, context):
    try:
        date_str = update.message.text.strip()
        datetime.strptime(date_str, "%d.%m.%Y")

        matrix_data = calculate_matrix(date_str)

        text = (
            daily_horoscope(matrix_data)
            + "\n\n"
            + build_tasks_text(matrix_data)
            + "\n"
            + build_matrix_text(matrix_data)
        )

        update.message.reply_text(
            text,
            parse_mode="Markdown"
        )

        # Пример отправки изображения
        image_url = "https://image.pollinations.ai/prompt/mystical%20tarot%20card.png"
        send_image_safely(update, image_url, caption="Вот ваш прогноз 🔮")

    except Exception as e:
        logger.error(f"Ошибка при обработке даты: {e}")
        update.message.reply_text(
            "❌ Ошибка.\nИспользуй формат DD.MM.YYYY"
        )

def main():
    # Создаём Updater (старый синхронный API PTB 13.x)
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Добавляем хэндлеры
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_date))

    logger.info("Бот запущен...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
