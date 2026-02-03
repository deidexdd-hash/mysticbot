import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from matrix import calculate_matrix
from horoscope import (
    build_matrix_text,
    build_tasks_text,
    daily_horoscope,
)

TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()
bot_app = ApplicationBuilder().token(TOKEN).build()


@app.get("/")
async def root():
    return {"status": "Bot is running"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет.\n\n"
        "Отправь дату рождения в формате:\n"
        "DD.MM.YYYY"
    )


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_str = update.message.text.strip()
        matrix_data = calculate_matrix(date_str)

        text = (
            daily_horoscope(matrix_data)
            + "\n\n"
            + build_tasks_text(matrix_data)
            + "\n"
            + build_matrix_text(matrix_data)
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception:
        await update.message.reply_text(
            "Ошибка. Проверь формат даты: DD.MM.YYYY"
        )


bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", start))
bot_app.add_handler(CommandHandler("matrix", handle_date))


@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.start()


@app.on_event("shutdown")
async def shutdown():
    await bot_app.stop()
    await bot_app.shutdown()
