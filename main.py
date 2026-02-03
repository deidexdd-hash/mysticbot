import os
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Персональный оракул\n\n"
        "Отправь дату рождения в формате:\n"
        "DD.MM.YYYY"
    )


# --- Обработчик текста с датой ---
async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        await update.message.reply_text(
            text,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке даты: {e}")
        await update.message.reply_text(
            "❌ Ошибка.\nИспользуй формат DD.MM.YYYY"
        )


# --- Основная функция запуска ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Добавляем хэндлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date))

    logger.info("Бот запущен...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
