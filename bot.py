import logging
import os
import traceback
import re
import socket
import atexit
import sys
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

# --- Настройка логирования ---
# Настраиваем базовую конфигурацию для вывода в консоль с поддержкой UTF-8
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding='utf-8'  # Критически важно для Windows, чтобы эмодзи не ломали логи
)

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
PRODUCT_DESCRIPTIONS = {
    "cell_cleanser": {"name": "Пенка для умывания «Нежность орхидеи»", "category": "Энергия клеток", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "cell_cream": {"name": "Крем для лица «Энергия клеток»", "category": "Энергия клеток", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "cell_serum": {"name": "Сыворотка «Энергия клеток»", "category": "Энергия клеток", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "cell_eye_cream": {"name": "Крем для кожи вокруг глаз и губ", "category": "Энергия клеток", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "glow_cream": {"name": "Крем от пигментации", "category": "Сияние кожи", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "glow_serum": {"name": "Сыворотка от пигментации", "category": "Сияние кожи", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "hair_loss_lotion": {"name": "Лосьон от выпадения волос", "category": "Сила волос", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "hair_growth_lotion": {"name": "Лосьон для роста волос", "category": "Сила волос", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
    "collagen": {"name": "Питьевой коллаген с пептидами", "category": "Питьевой коллаген", "description": "...", "ingredients": "...", "usage": "...", "packaging": "..."},
}
PRODUCT_NAME_TO_KEY = {v['name']: k for k, v in PRODUCT_DESCRIPTIONS.items()}

# --- КЛАВИАТУРЫ (Inline) ---
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🛍️ Каталог продуктов", callback_data="catalog"), InlineKeyboardButton("👩‍⚕️ Помощник по подбору", callback_data="start_quiz")],
        [InlineKeyboardButton("💬 Связаться с нами", callback_data="support"), InlineKeyboardButton("🤝 Стать амбассадором", callback_data="ambassador")],
        [InlineKeyboardButton("🔗 Соцсети и магазины", callback_data="social")]
    ]
    return InlineKeyboardMarkup(keyboard)

def product_categories_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💫 Энергия клеток", callback_data="category_Энергия клеток"), InlineKeyboardButton("✨ Сияние кожи", callback_data="category_Сияние кожи")],
        [InlineKeyboardButton("💇‍♀️ Сила волос", callback_data="category_Сила волос"), InlineKeyboardButton("🥤 Питьевой коллаген", callback_data="category_Питьевой коллаген")],
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
    product_key = query.data.split('_', 1)[1]
    product_data = PRODUCT_DESCRIPTIONS.get(product_key)
    logger.info(f"Пользователь {update.effective_user.id} запросил детали о продукте: {product_key}")

    if product_data:
        category_name = product_data.get('category')
        details_text = (
            f"<b>{product_data['name']}</b>\n\n"
            f"<b>Описание:</b>\n{product_data['description']}\n\n"
            f"<b>Состав:</b>\n{product_data['ingredients']}\n\n"
            f"<b>Как использовать:</b>\n{product_data['usage']}\n\n"
            f"<b>Упаковка:</b>\n{product_data['packaging']}"
        )
        keyboard = [
            [InlineKeyboardButton("← Назад к списку продуктов", callback_data=f"category_{category_name}")],
            [InlineKeyboardButton("← Назад к категориям", callback_data="catalog")]
        ]
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=details_text,
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
        "• <a href=\"https://www.letu.ru/brand/primaderma\">Летуаль</a>\n"
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
    context.user_data[STATE] = QUIZ_STATE
    context.user_data[QUIZ_STEP] = 1
    keyboard = [
        [InlineKeyboardButton("Сухая", callback_data="quiz_1_Сухая"), InlineKeyboardButton("Нормальная", callback_data="quiz_1_Нормальная")],
        [InlineKeyboardButton("Жирная", callback_data="quiz_1_Жирная"), InlineKeyboardButton("Комбинированная", callback_data="quiz_1_Комбинированная")],
        [InlineKeyboardButton("← В меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info(f"[DEBUG] Quiz keyboard (Q1): {reply_markup.inline_keyboard}")
    await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Шаг 1/3: Какой у вас тип кожи?",
        reply_markup=reply_markup
    )

async def handle_quiz_answer(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    step, answer = query.data.split('_')[1:]
    step = int(step)

    if step == 1:
        context.user_data['skin_type'] = answer
        context.user_data[QUIZ_STEP] = 2
        keyboard = [
            [InlineKeyboardButton("Морщины", callback_data="quiz_2_Морщины"), InlineKeyboardButton("Пигментация", callback_data="quiz_2_Пигментация")],
            [InlineKeyboardButton("Потеря упругости", callback_data="quiz_2_Потеря упругости"), InlineKeyboardButton("Тусклый цвет", callback_data="quiz_2_Тусклый цвет")],
            [InlineKeyboardButton("← В меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info(f"[DEBUG] Quiz keyboard (Q2): {reply_markup.inline_keyboard}")
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Шаг 2/3: Какая у вас основная проблема кожи?",
            reply_markup=reply_markup
        )
    
    elif step == 2:
        context.user_data['skin_concern'] = answer
        context.user_data[QUIZ_STEP] = 3
        keyboard = [
            [InlineKeyboardButton("Да, регулярно", callback_data="quiz_3_Да"), InlineKeyboardButton("Иногда", callback_data="quiz_3_Иногда")],
            [InlineKeyboardButton("Редко", callback_data="quiz_3_Редко"), InlineKeyboardButton("Нет, никогда", callback_data="quiz_3_Нет")],
            [InlineKeyboardButton("← В меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info(f"[DEBUG] Quiz keyboard (Q3): {reply_markup.inline_keyboard}")
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Шаг 3/3: Используете ли вы сейчас какие-либо уходовые средства для лица?",
            reply_markup=reply_markup
        )
    
    elif step == 3:
        context.user_data['current_routine'] = answer
        skin_type = context.user_data.get('skin_type', 'не указан')
        skin_concern = context.user_data.get('skin_concern', 'не указана')
        
        # Логика рекомендации (упрощенная версия)
        if skin_concern == "Морщины":
            recommended_product_key = "cell_serum"
            recommendation_text = "Для борьбы с морщинами мы рекомендуем нашу сыворотку 'Энергия клеток', которая помогает разглаживать морщины и улучшать текстуру кожи."
        elif skin_concern == "Пигментация":
            recommended_product_key = "glow_serum"
            recommendation_text = "Для коррекции пигментации идеально подойдет наша сыворотка от пигментации, которая осветляет пигментные пятна и выравнивает тон кожи."
        else:
            recommended_product_key = "cell_cream"
            recommendation_text = "Для вашего типа кожи мы рекомендуем наш крем 'Энергия клеток', который обеспечивает интенсивное увлажнение и питание."
        
        final_text = f"На основе ваших ответов, мы рекомендуем вам:\n\n{recommendation_text}"
        product_name = PRODUCT_DESCRIPTIONS[recommended_product_key]['name']
        keyboard = [
            [InlineKeyboardButton(f"Посмотреть «{product_name}»", callback_data=f"product_{recommended_product_key}")],
            [InlineKeyboardButton("← В меню", callback_data="main_menu")]
        ]
        await query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=final_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        context.user_data.clear()



# --- АДМИНКА И ОБРАБОТКА СООБЩЕНИЙ ---
async def dispatch_text_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Ветка 1: Сообщение от Админа, и это ответ на другое сообщение.
    if user.id == int(ADMIN_ID) and update.message.reply_to_message:
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
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"Новый вопрос в поддержку от @{user.username} [user_id={user.id}]:\n\n{text}")
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
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_id, caption=caption)
    elif update.message.document:
        file_id = update.message.document.file_id
        await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption)

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
    logger.error("Произошла ошибка:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Произошла внутренняя ошибка. Попробуйте позже.", reply_markup=main_menu_keyboard())

def is_port_in_use(port: int) -> bool:
    """Проверяет, используется ли порт другим процессом"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def cleanup():
    """Функция для очистки ресурсов при завершении работы"""
    logger.info("Выполнение очистки перед завершением работы...")
    if 'application' in globals():
        logger.info("Остановка приложения...")
        application.stop()

# Глобальная переменная для управления состоянием сервера
httpd = None

def main() -> None:
    # Проверяем, не запущен ли уже бот
    if is_port_in_use(10000):
        logger.error("Другой экземпляр бота уже запущен. Завершение работы.")
        return
        
    if not TOKEN:
        logger.critical("Токен бота не найден! Проверьте файл config.py.")
        return

    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # --- Регистрация обработчиков ---
    application.add_handler(CommandHandler("start", start))
    
    # Навигация и основные действия
    application.add_handler(CallbackQueryHandler(main_menu_nav, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(show_products, pattern="^catalog$"))
    application.add_handler(CallbackQueryHandler(show_product_list_by_category, pattern="^category_"))
    application.add_handler(CallbackQueryHandler(show_product_detail, pattern="^product_"))
    application.add_handler(CallbackQueryHandler(social_and_shops, pattern="^social$"))

    # Запуск диалогов
    application.add_handler(CallbackQueryHandler(start_support_dialog, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(start_ambassador_dialog, pattern="^ambassador$"))
    application.add_handler(CallbackQueryHandler(product_quiz_start, pattern="^start_quiz$"))

    # Обработка ответов в диалогах
    application.add_handler(CallbackQueryHandler(handle_quiz_answer, pattern="^quiz_\\d+"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dispatch_text_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Обработчик неизвестных команд должен быть последним
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    
    # Запускаем бота с обработкой ошибок
    logger.info("Запуск бота с новой архитектурой диалогов...")
    try:
        # Запускаем бота с drop_pending_updates для игнорирования старых сообщений
        application.run_polling(
            drop_pending_updates=True,
            close_loop=False,
            allowed_updates=Update.ALL_TYPES
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        import sys
        sys.exit(1)

from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import signal
import sys

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

# Глобальная переменная для управления состоянием сервера
httpd = None

def run_health_check():
    global httpd
    server_address = ('', int(os.environ.get('PORT', '10000')))
    httpd = HTTPServer(server_address, HealthCheckHandler)
    
    logger.info(f"Запуск health check сервера на порту {server_address[1]}")
    httpd.serve_forever()

def signal_handler(signum, frame):
    logger.info(f"Получен сигнал {signum}, завершение работы...")
    
    # Останавливаем HTTP сервер, если он запущен
    global httpd
    if httpd:
        logger.info("Остановка health check сервера...")
        httpd.shutdown()
        httpd.server_close()
    
    # Останавливаем бота
    if 'application' in globals():
        logger.info("Остановка бота...")
        application.stop()
    
    sys.exit(0)

if __name__ == "__main__":
    # Регистрируем функцию очистки при завершении работы
    atexit.register(cleanup)
    
    # Устанавливаем обработчики сигналов только в основном потоке
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Запуск бота...")
    
    try:
        # Запускаем health check сервер в отдельном потоке
        health_check_thread = threading.Thread(target=run_health_check, daemon=True)
        health_check_thread.start()
        logger.info("Health check сервер запущен")
        
        # Запускаем бота в основном потоке
        main()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        signal_handler(signal.SIGTERM, None)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания с клавиатуры")
        signal_handler(signal.SIGINT, None)
        sys.exit(0)