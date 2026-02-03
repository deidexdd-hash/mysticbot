import os
import io
import logging
from datetime import datetime
from typing import Optional

import httpx
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, 
    InputFile, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from matrix import calculate_matrix
from horoscope import (
    build_matrix_text,
    build_tasks_text,
    daily_horoscope,
)

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Токен ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не задан в окружении!")
    exit(1)

# --- Инициализация бота и диспетчера ---
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# --- Состояния FSM ---
class UserState(StatesGroup):
    waiting_for_birth_date = State()

# --- Клавиатуры ---
def get_main_keyboard() -> InlineKeyboardMarkup:
    """Создает основную клавиатуру"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="🎲 Рассчитать матрицу",
            callback_data="calculate_matrix"
        ),
        InlineKeyboardButton(
            text="📅 Ввести дату рождения",
            callback_data="enter_birth_date"
        ),
        InlineKeyboardButton(
            text="❓ Помощь",
            callback_data="help"
        ),
        InlineKeyboardButton(
            text="⭐ Отзыв",
            callback_data="feedback"
        )
    )
    builder.adjust(1)
    return builder.as_markup()

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="cancel"
        )
    )
    return builder.as_markup()

# --- Функция безопасной отправки изображения ---
async def send_image_safely(
    chat_id: int,
    url: str,
    caption: str = "",
    parse_mode: Optional[str] = "HTML"
) -> bool:
    """
    Безопасно отправляет изображение
    
    Args:
        chat_id: ID чата
        url: URL изображения
        caption: Подпись к изображению
        parse_mode: Режим парсинга текста
        
    Returns:
        bool: Успешность отправки
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
            # Проверяем, что это действительно изображение
            content_type = resp.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"Получен не изображение: {content_type}")
                return False
                
            image_bytes = io.BytesIO(resp.content)
            image_bytes.name = "oracle_image.png"
            
            await bot.send_photo(
                chat_id=chat_id,
                photo=InputFile(image_bytes),
                caption=caption[:1024],  # Ограничение Telegram
                parse_mode=parse_mode
            )
            return True
            
    except httpx.TimeoutException:
        logger.error(f"Таймаут при загрузке изображения: {url}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Ошибка запроса изображения: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        return False

# --- Обработчик команды /start ---
@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    welcome_text = (
        "🔮 <b>Добро пожаловать в Персональный Оракул!</b>\n\n"
        "Я помогу вам рассчитать <b>Матрицу Судьбы</b> "
        "и получить персональные рекомендации.\n\n"
        "Для начала работы выберите опцию ниже 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# --- Обработчик команды /help ---
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "📚 <b>Справка по использованию бота</b>\n\n"
        "1. <b>Рассчитать матрицу</b> - получить полный расчет\n"
        "2. <b>Ввести дату рождения</b> - для нового расчета\n"
        "3. <b>Формат даты</b>: ДД.ММ.ГГГГ (например, 15.05.1990)\n\n"
        "Матрица Судьбы помогает понять:\n"
        "• Ваши сильные стороны\n• Кармические задачи\n"
        "• Предназначение\n• События дня\n\n"
        "Используйте кнопки ниже для навигации ⬇️"
    )
    
    await message.answer(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# --- Обработчик кнопки "Ввести дату рождения" ---
@router.callback_query(F.data == "enter_birth_date")
async def process_enter_birth_date(callback: CallbackQuery, state: FSMContext):
    """Обработчик ввода даты рождения"""
    await callback.answer()
    
    instruction_text = (
        "📝 <b>Введите дату рождения</b>\n\n"
        "Пожалуйста, отправьте дату в формате:\n"
        "<code>ДД.ММ.ГГГГ</code>\n\n"
        "Например: <code>25.12.1990</code>"
    )
    
    await callback.message.edit_text(
        instruction_text,
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    
    await state.set_state(UserState.waiting_for_birth_date)

# --- Обработчик кнопки "Рассчитать матрицу" ---
@router.callback_query(F.data == "calculate_matrix")
async def process_calculate_matrix(callback: CallbackQuery, state: FSMContext):
    """Обработчик расчета матрицы"""
    await callback.answer()
    
    # Проверяем, есть ли сохраненная дата
    user_data = await state.get_data()
    birth_date = user_data.get('birth_date')
    
    if birth_date:
        await calculate_and_send_matrix(callback.message, birth_date, callback.from_user.id)
    else:
        await callback.message.edit_text(
            "❌ <b>Дата рождения не указана</b>\n\n"
            "Пожалуйста, сначала введите дату рождения.",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )

# --- Обработчик кнопки "Помощь" ---
@router.callback_query(F.data == "help")
async def process_help(callback: CallbackQuery):
    """Обработчик справки"""
    await callback.answer()
    await cmd_help(callback.message)

# --- Обработчик кнопки "Отмена" ---
@router.callback_query(F.data == "cancel")
async def process_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены"""
    await callback.answer("Действие отменено")
    await state.clear()
    await cmd_start(callback.message)

# --- Обработчик кнопки "Отзыв" ---
@router.callback_query(F.data == "feedback")
async def process_feedback(callback: CallbackQuery):
    """Обработчик отзыва"""
    await callback.answer()
    
    feedback_text = (
        "💌 <b>Обратная связь</b>\n\n"
        "Если у вас есть предложения, пожелания или вопросы, "
        "напишите разработчику: @username\n\n"
        "Благодарим за использование бота! 🙏"
    )
    
    await callback.message.edit_text(
        feedback_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# --- Функция расчета и отправки матрицы ---
async def calculate_and_send_matrix(message: Message, date_str: str, user_id: int):
    """Рассчитывает и отправляет матрицу"""
    try:
        # Отправляем сообщение о начале расчета
        processing_msg = await message.answer("🔄 <b>Рассчитываю матрицу...</b>", parse_mode="HTML")
        
        # Рассчитываем матрицу
        matrix_data = calculate_matrix(date_str)
        
        # Формируем текст
        text_parts = [
            f"📅 <b>Дата рождения:</b> <code>{date_str}</code>\n",
            f"🧮 <b>Расчет матрицы:</b>\n\n",
            daily_horoscope(matrix_data),
            "\n\n📋 <b>Кармические задачи:</b>\n",
            build_tasks_text(matrix_data),
            "\n\n🔢 <b>Матрица:</b>\n",
            build_matrix_text(matrix_data)
        ]
        
        full_text = "".join(text_parts)
        
        # Разбиваем текст на части (ограничение Telegram - 4096 символов)
        max_length = 4000
        if len(full_text) > max_length:
            parts = [full_text[i:i + max_length] for i in range(0, len(full_text), max_length)]
            
            # Отправляем первую часть
            await processing_msg.delete()
            await message.answer(parts[0], parse_mode="HTML")
            
            # Отправляем остальные части
            for part in parts[1:]:
                await message.answer(part, parse_mode="HTML")
        else:
            await processing_msg.delete()
            await message.answer(full_text, parse_mode="HTML")
        
        # Отправляем изображение
        image_url = "https://image.pollinations.ai/prompt/mystical%20tarot%20card%20digital%20art.png"
        image_sent = await send_image_safely(
            chat_id=user_id,
            url=image_url,
            caption="🎴 <b>Ваше персональное таро</b>\n\nЭто изображение сгенерировано специально для вас.",
            parse_mode="HTML"
        )
        
        if not image_sent:
            await message.answer(
                "⚠️ <b>Изображение временно недоступно</b>\n\n"
                "Вы можете повторить попытку позже.",
                parse_mode="HTML"
            )
        
        # Предлагаем дополнительные действия
        actions_text = (
            "\n\n✨ <b>Что дальше?</b>\n\n"
            "• Попробуйте рассчитать матрицу для другого человека\n"
            "• Изучите свои кармические задачи подробнее\n"
            "• Следите за ежедневными предсказаниями"
        )
        
        await message.answer(
            actions_text,
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
        
    except ValueError as e:
        logger.error(f"Ошибка валидации даты: {e}")
        await message.answer(
            "❌ <b>Неверный формат даты</b>\n\n"
            "Используйте формат: <code>ДД.ММ.ГГГГ</code>\n"
            "Пример: <code>25.12.1990</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при расчете матрицы: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Произошла ошибка при расчете</b>\n\n"
            "Пожалуйста, попробуйте позже или проверьте формат даты.",
            parse_mode="HTML"
        )

# --- Обработчик текстовых сообщений (даты рождения) ---
@router.message(UserState.waiting_for_birth_date)
async def handle_birth_date_input(message: Message, state: FSMContext):
    """Обработчик ввода даты рождения"""
    try:
        date_str = message.text.strip()
        
        # Валидация даты
        birth_date = datetime.strptime(date_str, "%d.%m.%Y")
        
        # Проверка на будущую дату
        if birth_date > datetime.now():
            await message.answer(
                "❌ <b>Дата из будущего</b>\n\n"
                "Пожалуйста, введите реальную дату рождения.",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем дату в состоянии
        await state.update_data(birth_date=date_str)
        await state.clear()
        
        # Рассчитываем и отправляем матрицу
        await calculate_and_send_matrix(message, date_str, message.from_user.id)
        
    except ValueError:
        await message.answer(
            "❌ <b>Неверный формат даты</b>\n\n"
            "Используйте формат: <code>ДД.ММ.ГГГГ</code>\n"
            "Пример: <code>25.12.1990</code>\n\n"
            "Попробуйте еще раз:",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке даты: {e}")
        await message.answer(
            "❌ <b>Произошла ошибка</b>\n\n"
            "Пожалуйста, попробуйте еще раз.",
            parse_mode="HTML"
        )

# --- Обработчик всех остальных текстовых сообщений ---
@router.message()
async def handle_other_messages(message: Message):
    """Обработчик всех остальных сообщений"""
    # Проверяем, не является ли сообщение датой
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
        # Если это дата, предлагаем использовать кнопку
        await message.answer(
            "📝 <b>Вы ввели дату рождения</b>\n\n"
            "Для расчета матрицы используйте кнопку "
            '"📅 Ввести дату рождения" в меню.',
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    except ValueError:
        # Если не дата, показываем меню
        await cmd_start(message)

# --- Обработка ошибок ---
@router.errors()
async def error_handler(update, exception):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {exception}", exc_info=True)
    
    if update.message:
        await update.message.answer(
            "⚠️ <b>Произошла непредвиденная ошибка</b>\n\n"
            "Пожалуйста, попробуйте позже.",
            parse_mode="HTML"
        )
    
    return True

# --- Основная функция запуска ---
async def main():
    """Основная функция запуска бота"""
    logger.info("Бот запускается...")
    
    # Удаляем вебхук (если был)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем поллинг
    logger.info("Бот запущен и готов к работе!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
