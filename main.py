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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Персональный оракул\n\n"
        "Отправь дату рождения в формате:\n"
        "DD.MM.YYYY"
    )


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
        logger.error(e)
        await update.message.reply_text(
            "❌ Ошибка.\nИспользуй формат DD.MM.YYYY"
        )


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)
    )

    logger.info("Bot started")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
