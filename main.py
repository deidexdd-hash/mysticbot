import os
import logging
import time
from datetime import datetime

import requests

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

def send_message(chat_id, text):
    """Отправка сообщения"""
    url = f"{API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, json=data)

def get_updates(offset=None):
    """Получение обновлений"""
    url = f"{API_URL}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    response = requests.get(url, params=params)
    return response.json().get("result", [])

def process_update(update):
    """Обработка обновления"""
    if "message" not in update:
        return
    
    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    
    if not text:
        return
    
    # Команда /start или /help
    if text.lower() in ["/start", "/help"]:
        send_message(chat_id, "🔮 Персональный оракул\n\nОтправь дату рождения (DD.MM.YYYY)")
        return
    
    # Обработка даты
    try:
        datetime.strptime(text, "%d.%m.%Y")
        
        # Простой расчет для примера
        day_sum = sum(int(d) for d in text if d.isdigit())
        destiny_number = (day_sum % 9) or 9
        
        response = (
            f"📅 Дата рождения: {text}\n"
            f"🧮 Число судьбы: {destiny_number}\n"
            f"✨ Индивидуальный код: {day_sum}"
        )
        
        send_message(chat_id, response)
        
    except ValueError:
        send_message(chat_id, "❌ Ошибка. Используй формат DD.MM.YYYY")

def main():
    """Основной цикл бота"""
    logger.info("Бот запущен...")
    offset = None
    
    while True:
        try:
            updates = get_updates(offset)
            
            for update in updates:
                process_update(update)
                offset = update["update_id"] + 1
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
