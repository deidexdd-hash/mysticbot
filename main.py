import os
import logging
import io
from datetime import datetime

import requests
import telebot

from matrix import calculate_matrix
from horoscope import build_matrix_text, build_tasks_text, daily_horoscope

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не задан в окружении!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "🔮 *Персональный Оракул: Матрица Судьбы*\n\n"
        "Отправь дату рождения в формате:\n"
        "*ДД.ММ.ГГГГ*\n\n"
        "Пример: *15.05.1990*\n\n"
        "Я рассчитаю твою матрицу судьбы и дам персональный прогноз на сегодня."
    )

@bot.message_handler(func=lambda message: True)
def handle_date(message):
    try:
        date_str = message.text.strip()
        datetime.strptime(date_str, "%d.%m.%Y")
        
        # Рассчитываем матрицу
        matrix_data = calculate_matrix(date_str)
        
        # Формируем текст как в оригинале
        text = (
            daily_horoscope(matrix_data)
            + "\n\n"
            + build_tasks_text(matrix_data)
            + "\n"
            + build_matrix_text(matrix_data)
        )
        
        bot.reply_to(message, text)
        
        # Пробуем отправить изображение (по желанию)
        try:
            image_url = "https://image.pollinations.ai/prompt/mystical%20tarot%20card%20esoteric%20symbols%20golden%20light.png"
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            if response.headers.get('content-type', '').startswith('image/'):
                bot.send_photo(
                    message.chat.id,
                    photo=io.BytesIO(response.content),
                    caption="🎴 *Ваша персональная энергетическая карта*"
                )
        except Exception as e:
            logger.debug(f"Изображение не загрузилось: {e}")
            # Это нормально, пропускаем
            
    except ValueError:
        bot.reply_to(
            message,
            "❌ *Ошибка формата*\n\n"
            "Используйте: *ДД.ММ.ГГГГ*\n"
            "Пример: *15.05.1990*"
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        bot.reply_to(message, "❌ *Произошла ошибка при расчете*")

if __name__ == '__main__':
    logger.info("Бот запущен...")
    bot.infinity_polling()
