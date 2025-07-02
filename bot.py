import logging
import os
import traceback
import re
from config import TOKEN, ADMIN_ID

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)

# --- Настройка логирования ---
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.FileHandler("primaderma_bot.log"),
        logging.StreamHandler()
    ]
)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

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
    await query.edit_message_text(text="Чем могу быть полезен?", reply_markup=main_menu_keyboard())

# --- КАТАЛОГ ПРОДУКТОВ ---
async def show_products(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} вошел в каталог продуктов.")
    await query.edit_message_text(text="Выберите интересующую вас категорию:", reply_markup=product_categories_keyboard())

async def show_product_list_by_category(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    category_name = query.data.split('_', 1)[1]
    context.user_data['current_category'] = category_name
    logger.info(f"Пользователь {update.effective_user.id} просматривает категорию '{category_name}'.")
    
    products_in_category = [prod["name"] for prod in PRODUCT_DESCRIPTIONS.values() if prod.get("category") == category_name]
    
    if not products_in_category:
        await query.edit_message_text(text="В этой категории пока нет продуктов.", reply_markup=product_categories_keyboard())
        return

    keyboard_buttons = [[InlineKeyboardButton(name, callback_data=f"product_{PRODUCT_NAME_TO_KEY[name]}")] for name in products_in_category]
    keyboard_buttons.append([InlineKeyboardButton("← Назад к категориям", callback_data="catalog")])
    await query.edit_message_text(text="Выберите продукт:", reply_markup=InlineKeyboardMarkup(keyboard_buttons))

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
            f"<b>Способ применения:</b>\n{product_data['usage']}\n\n"
            f"<b>Упаковка:</b>\n{product_data['packaging']}"
        )
        keyboard = [
            [InlineKeyboardButton("← Назад к списку продуктов", callback_data=f"category_{category_name}")],
            [InlineKeyboardButton("← Назад к категориям", callback_data="catalog")]
        ]
        await query.edit_message_text(text=details_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        logger.warning(f"Продукт с ключом '{product_key}' не найден.")
        await query.edit_message_text(text="Продукт не найден.", reply_markup=product_categories_keyboard())

# --- СОЦСЕТИ И МАГАЗИНЫ ---
async def social_and_shops(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} запросил соцсети и магазины.")
    text = "Подписывайтесь на нас в социальных сетях и покупайте нашу продукцию в лучших магазинах!"
    keyboard = [
        [InlineKeyboardButton("Instagram", url="https://instagram.com/primaderma")],
        [InlineKeyboardButton("Telegram-канал", url="https://t.me/primaderma_channel")],
        [InlineKeyboardButton("Wildberries", url="https://www.wildberries.ru/brands/primaderma")],
        [InlineKeyboardButton("Ozon", url="https://www.ozon.ru/seller/primaderma-289547/")],
        [InlineKeyboardButton("← В меню", callback_data="main_menu")]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- ДИАЛОГИ (ПОДДЕРЖКА, АМБАССАДОР) ---
async def start_support_dialog(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} начал диалог поддержки.")
    context.user_data[STATE] = SUPPORT_STATE
    keyboard = [[InlineKeyboardButton("← В меню", callback_data="main_menu")]]
    await query.edit_message_text(text="Опишите ваш вопрос, и мы скоро свяжемся с вами.", reply_markup=InlineKeyboardMarkup(keyboard))



async def start_ambassador_dialog(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    logger.info(f"Пользователь {update.effective_user.id} хочет стать амбассадором.")
    context.user_data[STATE] = AMBASSADOR_STATE
    keyboard = [[InlineKeyboardButton("← В меню", callback_data="main_menu")]]
    await query.edit_message_text(text="Пожалуйста, отправьте ваше фото или резюме.", reply_markup=InlineKeyboardMarkup(keyboard))





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
    await query.edit_message_text(text="Шаг 1/3: Какой у вас тип кожи?", reply_markup=InlineKeyboardMarkup(keyboard))

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
        await query.edit_message_text(text="Шаг 2/3: Какая проблема вас больше всего беспокоит?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif step == 2:
        context.user_data['concern'] = answer
        context.user_data[QUIZ_STEP] = 3
        keyboard = [
            [InlineKeyboardButton("До 25", callback_data="quiz_3_До 25"), InlineKeyboardButton("25-35", callback_data="quiz_3_25-35")],
            [InlineKeyboardButton("35-45", callback_data="quiz_3_35-45"), InlineKeyboardButton("45+", callback_data="quiz_3_45+")],
            [InlineKeyboardButton("← В меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(text="Шаг 3/3: Укажите ваш возраст.", reply_markup=InlineKeyboardMarkup(keyboard))
    elif step == 3:
        context.user_data['age_range'] = answer
        concern = context.user_data.get('concern')
        recommendation_text, recommended_product_key = ("Наш универсальный продукт - <b>Питьевой коллаген</b>.", "collagen")
        if concern in ["Пигментация", "Тусклый цвет"]:
            recommendation_text, recommended_product_key = ("Линейку <b>«Сияние кожи»</b>.", "glow_serum")
        elif concern in ["Морщины", "Потеря упругости"]:
            recommendation_text, recommended_product_key = ("Линейку <b>«Энергия клеток»</b>.", "cell_serum")
        
        final_text = f"На основе ваших ответов, мы рекомендуем вам:\n\n{recommendation_text}"
        product_name = PRODUCT_DESCRIPTIONS[recommended_product_key]['name']
        keyboard = [
            [InlineKeyboardButton(f"Посмотреть «{product_name}»", callback_data=f"product_{recommended_product_key}")],
            [InlineKeyboardButton("← В меню", callback_data="main_menu")]
        ]
        await query.edit_message_text(text=final_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
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

    await update.message.reply_text("Спасибо за вашу заявку! Мы скоро с вами свяжемся.", reply_markup=main_menu_keyboard())
    context.user_data.clear()

async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("Извините, я не понимаю эту команду. Пожалуйста, используйте меню.", reply_markup=main_menu_keyboard())

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Произошла ошибка:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Произошла внутренняя ошибка. Попробуйте позже.", reply_markup=main_menu_keyboard())

def main() -> None:
    if not TOKEN:
        logger.critical("Токен бота не найден! Проверьте файл config.py.")
        return

    application = Application.builder().token(TOKEN).build()

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
    application.add_handler(CallbackQueryHandler(handle_quiz_answer, pattern="^quiz_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dispatch_text_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media_message))
    application.add_error_handler(error_handler)
    
    # Обработчик неизвестных команд должен быть последним
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Запуск бота с новой архитектурой диалогов...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()