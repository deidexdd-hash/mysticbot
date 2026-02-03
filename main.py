import os
import logging
import json
import time
from datetime import datetime

import requests

# Ваши модули
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

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text, parse_mode=None):
    """Отправка сообщения"""
    url = f"{API_URL}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    # Убираем None значения
    if parse_mode is None:
        del data["parse_mode"]
    
    response = requests.post(url, json=data, timeout=10)
    return response.json()

def split_long_text(text, max_length=4000):
    """Разбивает длинный текст на части"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Простой сплит по абзацам
    paragraphs = text.split("\n\n")
    
    for paragraph in paragraphs:
        if len(current_part) + len(paragraph) + 2 > max_length:
            if current_part:
                parts.append(current_part)
            current_part = paragraph
        else:
            if current_part:
                current_part += "\n\n" + paragraph
            else:
                current_part = paragraph
    
    if current_part:
        parts.append(current_part)
    
    return parts

def send_photo(chat_id, photo_url, caption=None):
    """Отправка фото по URL"""
    url = f"{API_URL}/sendPhoto"
    data = {
        "chat_id": chat_id,
        "photo": photo_url,
        "parse_mode": "Markdown"
    }
    
    if caption:
        data["caption"] = caption[:1024]  # Ограничение Telegram
    
    try:
        response = requests.post(url, json=data, timeout=30)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {e}")
        return None

def get_updates(offset=None):
    """Получение обновлений"""
    url = f"{API_URL}/getUpdates"
    params = {
        "timeout": 30,
        "offset": offset,
        "allowed_updates": ["message"]
    }
    
    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json().get("result", [])
    except Exception as e:
        logger.error(f"Ошибка при получении обновлений: {e}")
        return []

def process_update(update):
    """Обработка обновления"""
    if "message" not in update:
        return None
    
    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    
    if not text:
        return update["update_id"]
    
    # Команда /start или /help
    if text.lower() in ["/start", "/help"]:
        send_message(
            chat_id,
            "🔮 *Персональный оракул*\n\n"
            "Отправь дату рождения в формате:\n"
            "*DD.MM.YYYY*\n\n"
            "Например: *15.05.1990*",
            parse_mode="Markdown"
        )
        return update["update_id"]
    
    # Обработка даты
    try:
        datetime.strptime(text, "%d.%m.%Y")
        
        # Рассчитываем матрицу
        matrix_data = calculate_matrix(text)
        
        # Формируем текст
        text_parts = [
            f"📅 *Дата рождения:* {text}\n\n",
            daily_horoscope(matrix_data),
            "\n",
            build_tasks_text(matrix_data),
            "\n",
            build_matrix_text(matrix_data)
        ]
        
        full_text = "".join(text_parts)
        
        # Отправляем текст частями
        text_parts_list = split_long_text(full_text)
        for part in text_parts_list:
            send_message(chat_id, part, parse_mode="Markdown")
            time.sleep(0.5)  # Небольшая задержка между сообщениями
        
        # Отправляем изображение
        image_url = "https://image.pollinations.ai/prompt/mystical%20tarot%20card%20digital%20art.png"
        send_photo(
            chat_id,
            image_url,
            caption="🎴 *Ваше персональное таро*\n\nЭто изображение сгенерировано специально для вас."
        )
        
    except ValueError:
        send_message(
            chat_id,
            "❌ *Ошибка.*\nИспользуй формат *DD.MM.YYYY*\n\nПример: *15.05.1990*",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке даты: {e}")
        send_message(chat_id, "❌ *Произошла ошибка при обработке запроса.*", parse_mode="Markdown")
    
    return update["update_id"]

def main():
    """Основной цикл бота"""
    logger.info("Бот запущен...")
    offset = None
    
    while True:
        try:
            updates = get_updates(offset)
            
            for update in updates:
                last_update_id = process_update(update)
                if last_update_id:
                    offset = last_update_id + 1
                
                # Небольшая задержка между обработкой сообщений
                time.sleep(0.1)
            
            # Если обновлений нет, ждем
            if not updates:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
