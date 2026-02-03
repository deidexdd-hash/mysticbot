import os
import logging
from datetime import datetime

import telebot

from matrix import calculate_matrix, get_year_forecast
from horoscope import (
    build_personal_numbers_text,
    build_matrix_text,
    build_tasks_text,
    daily_horoscope,
    build_recommendations,
)

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
    welcome_text = """
🔮 *ПЕРСОНАЛЬНЫЙ ОРАКУЛ: МАТРИЦА СУДЬБЫ*

Я помогу рассчитать вашу персональную матрицу судьбы и дам подробную интерпретацию.

*Доступные команды:*
• Просто отправьте дату рождения в формате *ДД.ММ.ГГГГ*
• Пример: *15.05.1990*
• Или используйте /forecast для прогноза на год

*Что вы получите:*
1. Персональные числа судьбы
2. Детальную матрицу с интерпретацией
3. Кармические задачи
4. Ежедневный гороскоп
5. Персональные рекомендации

Отправьте дату рождения для начала расчета...
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['forecast'])
def send_forecast(message):
    try:
        # Извлекаем год из сообщения
        parts = message.text.split()
        if len(parts) > 1:
            target_year = int(parts[1])
            date_parts = parts[2:] if len(parts) > 2 else []
        else:
            target_year = datetime.now().year
            date_parts = []
        
        if date_parts:
            date_str = ' '.join(date_parts)
        else:
            bot.reply_to(message, "Пожалуйста, укажите дату рождения после года.\nПример: /forecast 2024 15.05.1990")
            return
        
        # Проверяем дату
        datetime.strptime(date_str, "%d.%m.%Y")
        
        # Получаем прогноз
        forecast = get_year_forecast(date_str, target_year)
        
        forecast_text = f"""
📅 *ПРОГНОЗ НА {target_year} ГОД*

*Персональное число года:* {forecast['personal_year']}
*Основная тема:* {forecast['forecast']}
*Фокус года:* {forecast['focus']}
*Вызов года:* {forecast['challenge']}

*Рекомендации на год:*
• Концентрируйтесь на теме {forecast['focus']}
• Учитесь преодолевать {forecast['challenge']}
• Используйте энергию числа {forecast['personal_year']}
• Будьте открыты переменам

*Благоприятные периоды:*
• Весна: новые начинания
• Лето: активные действия
• Осень: подведение итогов
• Зима: планирование будущего
        """
        
        bot.reply_to(message, forecast_text)
        
    except ValueError:
        bot.reply_to(message, "❌ Неверный формат.\nИспользуйте: /forecast [год] ДД.ММ.ГГГГ\nПример: /forecast 2024 15.05.1990")
    except Exception as e:
        logger.error(f"Ошибка в прогнозе: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при расчете прогноза.")

@bot.message_handler(func=lambda message: True)
def handle_date(message):
    try:
        date_str = message.text.strip()
        datetime.strptime(date_str, "%d.%m.%Y")
        
        # Рассчитываем матрицу
        matrix_data = calculate_matrix(date_str)
        
        # Отправляем сообщение о начале расчета
        processing_msg = bot.reply_to(message, "🔄 *Рассчитываю вашу матрицу судьбы...*")
        
        # Отправляем результаты по частям
        try:
            # Часть 1: Персональные числа
            bot.send_message(
                message.chat.id,
                f"📅 *РАСЧЕТ МАТРИЦЫ СУДЬБЫ*\n*Дата рождения:* {date_str}\n"
            )
            
            time.sleep(1)
            
            # Часть 2: Детальная информация
            personal_numbers = build_personal_numbers_text(matrix_data)
            bot.send_message(message.chat.id, personal_numbers)
            
            time.sleep(1)
            
            # Часть 3: Матрица
            matrix_info = build_matrix_text(matrix_data)
            bot.send_message(message.chat.id, matrix_info)
            
            time.sleep(1)
            
            # Часть 4: Кармические задачи
            tasks_info = build_tasks_text(matrix_data)
            bot.send_message(message.chat.id, tasks_info)
            
            time.sleep(1)
            
            # Часть 5: Гороскоп
            horoscope = daily_horoscope(matrix_data)
            bot.send_message(message.chat.id, horoscope)
            
            time.sleep(1)
            
            # Часть 6: Рекомендации
            recommendations = build_recommendations(matrix_data)
            bot.send_message(message.chat.id, recommendations)
            
            # Удаляем сообщение о расчете
            bot.delete_message(message.chat.id, processing_msg.message_id)
            
            # Финальное сообщение
            final_text = """
✨ *РАСЧЕТ ЗАВЕРШЕН*

Ваша матрица судьбы содержит уникальную информацию о вашем предназначении, кармических задачах и жизненном пути.

*Что делать дальше:*
1. Сохраните эту информацию
2. Возвращайтесь к ней в важные моменты
3. Используйте рекомендации в повседневной жизни
4. Отслеживайте повторяющиеся ситуации

Для прогноза на конкретный год используйте команду:
/forecast [год] ДД.ММ.ГГГГ
Пример: /forecast 2024 15.05.1990

Желаю вам гармонии и осознанности на вашем пути! 🌟
            """
            bot.send_message(message.chat.id, final_text)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщений: {e}")
            # Если что-то пошло не так, отправляем хотя бы основную информацию
            bot.send_message(
                message.chat.id,
                f"📅 *Дата рождения:* {date_str}\n\n"
                f"{build_personal_numbers_text(matrix_data)}"
            )
            
    except ValueError:
        bot.reply_to(
            message,
            "❌ *Неверный формат даты*\n\n"
            "Пожалуйста, используйте формат: *ДД.ММ.ГГГГ*\n"
            "Пример: *15.05.1990*\n\n"
            "Или используйте команду /help для справки."
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        bot.reply_to(message, "❌ *Произошла ошибка при расчете*\nПожалуйста, попробуйте позже.")

if __name__ == '__main__':
    logger.info("Бот запущен...")
    bot.infinity_polling()
