import logging
import os
import traceback
import re
import socket
import atexit
import sys
import time
import random
import asyncio
import threading
from flask import Flask
from config import TOKEN, ADMIN_ID
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
    PicklePersistence
)



# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# Global variable for the bot application
application = None

# Create a simple health check endpoint
@app.route('/')
def health_check():
    return "Bot is running!", 200

# Эндпоинт для внешнего пинга (UptimeRobot)
@app.route('/ping')
def ping():
    logger.info("Получен ping-запрос")
    return "pong", 200

def get_public_url():
    """Получаем публичный URL из переменных окружения Render"""
    render_external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if render_external_url:
        return render_external_url
    
    # Если переменной окружения нет, возвращаем URL с localhost (для локальной разработки)
    port = os.environ.get('PORT', '10000')
    return f"http://localhost:{port}"

def run_flask():
    """Run Flask server for health checks"""
    port = int(os.environ.get('PORT', 10000))
    public_url = get_public_url()
    logger.info(f"Starting Flask server on port {port}")
    logger.info(f"Public URL: {public_url}")
    logger.info(f"Health check: {public_url}/")
    logger.info(f"Ping endpoint: {public_url}/ping")
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Добавляем обработчик для записи логов в файл, также с UTF-8
file_handler = logging.FileHandler("primaderma_bot.log", encoding='utf-8')
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(file_handler)

# Уменьшаем "шум" от библиотек HTTP
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Получаем логгер для нашего модуля
logger = logging.getLogger(__name__)
logger.info("Логгирование успешно настроено.")

# --- Константы для состояний ---
STATE = "state"
SUPPORT_STATE = "support"
AMBASSADOR_STATE = "ambassador"
QUIZ_STATE = "quiz"
QUIZ_STEP = "quiz_step"

# --- СТРУКТУРЫ ДАННЫХ ---
from product_data import PRODUCT_DESCRIPTIONS
PRODUCT_NAME_TO_KEY = {v['name']: k for k, v in PRODUCT_DESCRIPTIONS.items()}

# --- КЛАВИАТУРЫ (Inline) ---
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🛍️ Каталог продуктов", callback_data="catalog")],
        [InlineKeyboardButton("👩‍⚕️ Помощник по подбору", callback_data="start_quiz")],
        [InlineKeyboardButton("💬 Связаться с нами", callback_data="support")],
        [InlineKeyboardButton("🤝 Стать амбассадором", callback_data="ambassador")],
        [InlineKeyboardButton("🔗 Соцсети и магазины", callback_data="social")]
    ]
    return InlineKeyboardMarkup(keyboard)

def product_categories_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💫 Энергия клеток", callback_data="category_Энергия клеток")],
        [InlineKeyboardButton("✨ Сияние кожи", callback_data="category_Сияние кожи")],
        [InlineKeyboardButton("💇‍♀️ Сила волос", callback_data="category_Сила волос")],
        [InlineKeyboardButton("🥤 Питьевой коллаген", callback_data="category_Питьевой коллаген")],
        [InlineKeyboardButton("← В меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- ОБРАБОТЧИКИ НАВИГАЦИИ ---
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    logger.info(f"Пользователь {user.id} ({user.username}) запустил бота.")
    welcome_text = (
        "👋 Добро пожаловать в официального бота Primaderma.\n"
        "Я здесь, чтобы помочь с любыми вопросами о наших продуктах, доставке, акциях и не только.\n"
        "Чем могу быть полезен?"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())

async def main_menu_nav(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} вернулся в главное меню.")
    context.user_data.clear()
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Чем могу быть полезен?",
        reply_markup=main_menu_keyboard()
    )

# --- КАТАЛОГ ПРОДУКТОВ ---
async def show_products(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} вошел в каталог продуктов.")
    keyboard = product_categories_keyboard()
    logger.info(f"[DEBUG] Catalog keyboard: {keyboard.inline_keyboard}")
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите интересующую вас категорию:",
        reply_markup=keyboard
    )

async def show_product_list_by_category(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    category_name = query.data.split('_', 1)[1]
    context.user_data['current_category'] = category_name
    logger.info(f"Пользователь {update.effective_user.id} просматривает категорию '{category_name}'.")
    
    products_in_category = [prod["name"] for prod in PRODUCT_DESCRIPTIONS.values() if prod.get("category") == category_name]
    
    if not products_in_category:
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="В этой категории пока нет продуктов.",
            reply_markup=product_categories_keyboard()
        )
        return

    keyboard_buttons = [[InlineKeyboardButton(name, callback_data=f"product_{PRODUCT_NAME_TO_KEY[name]}")] for name in products_in_category]
    keyboard_buttons.append([InlineKeyboardButton("← Назад к категориям", callback_data="catalog")])
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    logger.info(f"[DEBUG] Product list keyboard: {keyboard.inline_keyboard}")
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите продукт:",
        reply_markup=keyboard
    )

async def show_product_detail(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Определяем, откуда пришел пользователь (из квиза или каталога)
    data = query.data
    origin = None
    product_key = None

    if '_origin_' in data:
        product_part, origin_part = data.split('_origin_')
        product_key = product_part.split('_', 1)[1]
        origin = origin_part
    else:
        product_key = data.split('_', 1)[1]

    product_data = PRODUCT_DESCRIPTIONS.get(product_key)
    logger.info(f"Пользователь {update.effective_user.id} запросил детали о продукте: {product_key} (из {origin or 'каталога'})")

    if product_data:
        details_text = (
            f"<b>{product_data.get('name', 'Название не указано')}</b>\n\n"
            f"<b>Описание:</b>\n{product_data.get('description', 'Нет описания')}\n\n"
            f"<b>Состав:</b>\n{product_data.get('ingredients', 'Состав не указан')}\n\n"
            f"<b>Как использовать:</b>\n{product_data.get('usage', 'Инструкция по применению не указана')}\n\n"
            f"<b>Упаковка:</b>\n{product_data.get('packaging', 'Информация об упаковке отсутствует')}"
        )

        if product_data.get('storage_conditions'):
            details_text += f"\n\n<b>Условия хранения:</b>\n{product_data['storage_conditions']}"
        if product_data.get('shelf_life'):
            details_text += f"\n\n<b>Срок годности:</b>\n{product_data['shelf_life']}"
        if product_data.get('gost'):
            details_text += f"\n\n<b>ГОСТ:</b>\n{product_data['gost']}"

        # Создаем клавиатуру в зависимости от контекста
        if origin:
            keyboard = [[InlineKeyboardButton("← Назад (к результатам квиза)", callback_data=f"quiz_result_{origin}")]]
        else:
            category_name = product_data.get('category')
            keyboard = [
                [InlineKeyboardButton("← Назад к списку продуктов", callback_data=f"category_{category_name}")],
                [InlineKeyboardButton("← Назад к категориям", callback_data="catalog")]
            ]

        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=details_text.strip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        logger.warning(f"Продукт с ключом '{product_key}' не найден.")
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Продукт не найден.",
            reply_markup=product_categories_keyboard()
        )

# --- СОЦСЕТИ И МАГАЗИНЫ ---
async def social_and_shops(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} запросил соцсети и магазины.")
    
    # Формируем текст сообщения с HTML-ссылками
    text = (
        "<b>Мы в социальных сетях:</b>\n"
        "• <a href=\"https://www.instagram.com/primaderma.ru?igsh=ZmFiOWF0OWJzM2ti\">Instagram</a>\n"
        "• <a href=\"https://vk.com/dermacare\">ВКонтакте</a>\n"
        "• <a href=\"https://t.me/+AW87XFPmPesyZjZi\">Telegram</a>\n\n"
        "<b>Наши магазины:</b>\n"
        "• <a href=\"https://primaderma.ru/\">Официальный сайт</a>\n"
        "• <a href=\"https://goldapple.ru/brands/primaderma\">Золотое Яблоко</a>\n"
        "• <a href=\"https://letu.ru/brand/primaderma\">Летуаль</a>\n"
        "• <a href=\"https://www.wildberries.ru/brands/310708162-primaderma\">Wildberries</a>\n"
        "• <a href=\"https://www.ozon.ru/seller/dr-gallyamova-132298/?miniapp=seller_132298\">Ozon</a>"
    )
    
    # Создаем клавиатуру только с кнопкой возврата в меню
    keyboard = [
        [InlineKeyboardButton("← В меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Удаляем предыдущее сообщение и отправляем новое
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

# --- ДИАЛОГИ (ПОДДЕРЖКА, АМБАССАДОР) ---
async def start_support_dialog(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} начал диалог поддержки.")
    context.user_data[STATE] = SUPPORT_STATE
    keyboard = [[InlineKeyboardButton("← В меню", callback_data="main_menu")]]
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Напишите свой вопрос — я сразу передам его менеджеру.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_ambassador_dialog(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} хочет стать амбассадором.")
    context.user_data[STATE] = AMBASSADOR_STATE
    keyboard = [[InlineKeyboardButton("← В меню", callback_data="main_menu")]]
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Отлично, вы хотите стать амбассадором Primaderma! Чтобы мы вас рассмотрели, отправьте скриншот статистики вашего аккаунта (охват, подписчики, engagement).",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- КВИЗ (с ручным управлением состоянием) ---
async def product_quiz_start(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} начал квиз.")

    text = (
        "Давайте подберём средство в формате небольшой игры-вопросов.\n\n"
        "Выберите, что вас беспокоит:"
    )

    keyboard = [
        [InlineKeyboardButton("Сухость, потеря упругости", callback_data="quiz_result_cells")],
        [InlineKeyboardButton("Пигментация, неровный тон, постакне", callback_data="quiz_result_glow")],
        [InlineKeyboardButton("Выпадение волос, восстановление волос", callback_data="quiz_result_hair")],
        [InlineKeyboardButton("← В меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Если сообщение было, удаляем. Если нет, отправляем новое.
    if query.message:
        await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup
    )

async def handle_quiz_result(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    choice = query.data.split('_')[-1]
    logger.info(f"Пользователь {user_id} выбрал в квизе: {choice}")

    text = ""
    keyboard = []

    if choice == 'cells':
        text = (
            "Вам подойдёт линия «Энергия клеток».\n\n"
            "• Крем «Энергия клеток»\n"
            "• Сыворотка «Энергия клеток»\n"
            "• Крем для кожи вокруг глаз и губ\n"
            "• Пенка для умывания\n"
            "• Коллаген\n\n"
            "Хотите узнать подробности о каждом?"
        )
        keyboard = [
            [InlineKeyboardButton("Крем для лица", callback_data="product_cell_cream_origin_cells")],
            [InlineKeyboardButton("Сыворотка", callback_data="product_cell_serum_origin_cells")],
            [InlineKeyboardButton("Пенка", callback_data="product_cell_cleanser_origin_cells")],
            [InlineKeyboardButton("Крем для глаз и губ", callback_data="product_cell_eye_cream_origin_cells")],
            [InlineKeyboardButton("Коллаген", callback_data="product_collagen_origin_cells")],
            [InlineKeyboardButton("← Назад (к выбору проблемы)", callback_data="start_quiz")]
        ]
    elif choice == 'glow':
        text = (
            "Линия «Сияние кожи»:\n\n"
            "• Крем от пигментации\n"
            "• Сыворотка от пигментации\n"
            "• Коллаген\n\n"
            "Хотите описание состава и применения?"
        )
        keyboard = [
            [InlineKeyboardButton("Крем от пигментации", callback_data="product_glow_cream_origin_glow")],
            [InlineKeyboardButton("Сыворотка от пигментации", callback_data="product_glow_serum_origin_glow")],
            [InlineKeyboardButton("Коллаген", callback_data="product_collagen_origin_glow")],
            [InlineKeyboardButton("← Назад (к выбору проблемы)", callback_data="start_quiz")]
        ]
    elif choice == 'hair':
        text = (
            "Линия «Сила волос»:\n\n"
            "• Лосьон от выпадения волос\n"
            "• Лосьон для роста волос\n"
            "• Коллаген\n\n"
            "Хотите узнать подробнее?"
        )
        keyboard = [
            [InlineKeyboardButton("Лосьон от выпадения", callback_data="product_hair_loss_lotion_origin_hair")],
            [InlineKeyboardButton("Лосьон для роста", callback_data="product_hair_growth_lotion_origin_hair")],
            [InlineKeyboardButton("Коллаген", callback_data="product_collagen_origin_hair")],
            [InlineKeyboardButton("← Назад (к выбору проблемы)", callback_data="start_quiz")]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup
    )


# --- АДМИНКА И ОБРАБОТКА СООБЩЕНИЙ ---
async def dispatch_text_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Ветка 1: Сообщение от Админа, и это ответ на другое сообщение.
    if user.id == ADMIN_ID and update.message.reply_to_message:
        replied_message = update.message.reply_to_message
        original_user_id = None
        
        # Ищем ID в тексте или подписи к медиа
        text_to_search = replied_message.text or replied_message.caption
        if text_to_search:
            match = re.search(r"\[user_id=(\d+)\]", text_to_search)
            if match:
                original_user_id = int(match.group(1))

        # Если не нашли в тексте, пробуем получить ID из информации о пересылке
        if not original_user_id and replied_message.forward_from:
            original_user_id = replied_message.forward_from.id

        if original_user_id:
            try:
                await context.bot.send_message(
                    chat_id=original_user_id,
                    text=f"💬 Вам поступил ответ от администратора:\n\n{update.message.text}"
                )
                await update.message.reply_text("✅ Сообщение успешно отправлено пользователю.")
            except Exception as e:
                logger.error(f"Не удалось отправить ответ пользователю {original_user_id}: {e}")
                await update.message.reply_text(f"❌ Не удалось отправить сообщение. Ошибка: {e}")
        else:
            logger.warning(f"Не удалось извлечь user_id для ответа администратора. Message ID: {update.message.message_id}")
            await update.message.reply_text("❌ Не удалось определить получателя. Убедитесь, что отвечаете на сообщение с `[user_id=...]`.")
    
    # Ветка 2: Сообщение от обычного пользователя (или админа, но не ответ) в состоянии диалога.
    else:
        user_state = context.user_data.get(STATE)
        if not user_state:
            await unknown(update, context)
            return

        text = update.message.text
        if user_state == SUPPORT_STATE:
            logger.info(f"Получено сообщение для поддержки от {user.id}: {text}")
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"Новый вопрос в поддержку от @{user.username} [user_id={user.id}]:\n\n{text}")
            await update.message.reply_text("Спасибо! Ваше сообщение передано администратору.", reply_markup=main_menu_keyboard())
        
        context.user_data.clear()

async def handle_media_message(update: Update, context: CallbackContext) -> None:
    user_state = context.user_data.get(STATE)
    if user_state != AMBASSADOR_STATE:
        await unknown(update, context)
        return

    user = update.effective_user
    caption = f"Новая заявка на амбассадора от @{user.username} [user_id={user.id}]"
    logger.info(f"Получена заявка на амбассадора от {user.id}")

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=int(ADMIN_ID), photo=file_id, caption=caption)
    elif update.message.document:
        file_id = update.message.document.file_id
        await context.bot.send_document(chat_id=int(ADMIN_ID), document=file_id, caption=caption)

    # Улучшенное ответное сообщение
    response_text = (
        "✅ Спасибо! Ваши данные приняты.\n\n"
        "Наша команда свяжется с вами в течение 48 ч для обсуждения условий сотрудничества.\n\n"
        "Пока мы обрабатываем ваши данные, приглашаем вас погрузиться в мир PRIMADERMA и подобрать для себя идеальный продукт, который подчеркнёт вашу красоту кожи и волос.\n\n"
        "🌐 Ознакомиться с продукцией: https://primaderma.ru/"
    )
    
    await update.message.reply_text(
        text=response_text,
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True
    )
    context.user_data.clear()

async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("Извините, я не понимаю эту команду. Пожалуйста, используйте меню.", reply_markup=main_menu_keyboard())

async def error_handler(update: object, context: CallbackContext) -> None:
    """Обработчик ошибок"""
    logger.error("Произошла ошибка:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла внутренняя ошибка. Попробуйте позже.", 
            reply_markup=main_menu_keyboard()
        )



def register_handlers(application: Application):
    """Registers all the handlers for the bot."""
    logger.info("Registering handlers...")

    # Command handlers
    application.add_handler(CommandHandler("start", start))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(main_menu_nav, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(show_products, pattern="^catalog$"))
    application.add_handler(CallbackQueryHandler(show_product_list_by_category, pattern=r"^category_"))
    application.add_handler(CallbackQueryHandler(show_product_detail, pattern=r"^product_"))
    application.add_handler(CallbackQueryHandler(social_and_shops, pattern="^social$"))
    application.add_handler(CallbackQueryHandler(start_support_dialog, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(start_ambassador_dialog, pattern="^ambassador$"))
    application.add_handler(CallbackQueryHandler(product_quiz_start, pattern="^start_quiz$"))
    application.add_handler(CallbackQueryHandler(handle_quiz_result, pattern=r"^quiz_result_"))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dispatch_text_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media_message))
    
    # Unknown command handler must be last
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    # Error handler
    application.add_error_handler(error_handler)
    logger.info("Handlers registered successfully.")


def main():
    """Основная асинхронная функция для запуска бота"""
    # Запускаем Flask-сервер в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask health check сервер запущен в отдельном потоке")
    logger.info("--- Bot version: v2025.07.04-02.15-FIXED ---") # Ошибка отступа исправлена

    if not TOKEN:
        logger.critical("Токен бота не найден! Проверьте переменную окружения TOKEN.")
        return

    if not ADMIN_ID:
        logger.critical("ID администратора не найден! Проверьте переменную окружения ADMIN_ID.")
        return

    # Создаем приложение с сохранением состояния
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # Регистрируем обработчики
    register_handlers(application)

    # Запускаем бота в режиме опроса.
    # Этот метод автоматически обрабатывает запуск, остановку и корректное завершение.
    logger.info("Запуск бота в режиме опроса...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        # Очищаем ресурсы
        if 'loop' in locals():
            # Отменяем все задачи
            pending = asyncio.all_tasks(loop=loop)
            for task in pending:
                task.cancel()
            
            # Запускаем loop для завершения всех задач
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            # Закрываем loop
            loop.close()
            
        logger.info("Приложение завершило работу")
        sys.exit(0)