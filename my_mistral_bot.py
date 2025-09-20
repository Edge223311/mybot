import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters.state import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 🔑 Твой токен и ID админа
TOKEN = '8296841853:AAGKqsoUJfA4Yr3A63vnNq4EyZ1gWtadeHc'
ADMIN_ID = 5545026621  # твой Telegram ID

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class GameStates(StatesGroup):
    waiting = State()
    playing = State()
    withdraw_amount = State()
    set_name = State()
    give_ar_user = State()  # Для ввода ника/username
    give_ar_amount = State()  # Для ввода количества Ар

# -------------------- БАЗА ДАННЫХ --------------------

def init_db():
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  custom_name TEXT,
                  points INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests
                 (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount INTEGER,
                  status TEXT DEFAULT 'pending',
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_or_update_user(user_id, username):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, custom_name, points) VALUES (?, ?, ?, 0)",
              (user_id, username, None))
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

def get_user_points(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_points(user_id, increment):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (increment, user_id))
    conn.commit()
    conn.close()

def get_user_custom_name(user_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT custom_name FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_user_custom_name(user_id, custom_name):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (custom_name, user_id))
    conn.commit()
    conn.close()

def find_user_by_name(name):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    # Ищем по custom_name или username (без @ для username)
    name = name.lstrip('@')
    c.execute("SELECT user_id, custom_name, username FROM users WHERE custom_name = ? OR username = ?",
              (name, name))
    result = c.fetchone()
    conn.close()
    return result  # (user_id, custom_name, username) или None

def create_withdraw_request(user_id, amount):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("INSERT INTO withdraw_requests (user_id, amount) VALUES (?, ?)", (user_id, amount))
    request_id = c.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_requests(status_filter='all'):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    query = """
        SELECT r.request_id, r.user_id, u.custom_name, u.username, r.amount, r.status, r.timestamp
        FROM withdraw_requests r
        JOIN users u ON r.user_id = u.user_id
    """
    if status_filter != 'all':
        query += " WHERE r.status = ?"
        c.execute(query, (status_filter,))
    else:
        c.execute(query)
    results = c.fetchall()
    conn.close()
    return results

def update_request_status(request_id, status):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("UPDATE withdraw_requests SET status = ? WHERE request_id = ?", (status, request_id))
    conn.commit()
    conn.close()

def get_request_user_id(request_id):
    conn = sqlite3.connect('game.db')
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM withdraw_requests WHERE request_id = ?", (request_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (None, None)

# -------------------- УСТАНОВКА КОМАНД --------------------

async def set_bot_commands():
    commands = [
        BotCommand(command="/start", description="Начать игру"),
        BotCommand(command="/profile", description="Посмотреть профиль и Ар"),
        BotCommand(command="/setname", description="Сменить ник"),
        BotCommand(command="/withdraw", description="Запросить вывод Ар"),
        BotCommand(command="/info", description="Информация об игре"),
        BotCommand(command="/help", description="Показать список команд")
    ]
    admin_commands = commands + [
        BotCommand(command="/requests", description="Текущие запросы на вывод (админ)"),
        BotCommand(command="/requests_list", description="Все запросы на вывод (админ)"),
        BotCommand(command="/give_ar", description="Выдать Ар пользователю (админ)")
    ]
    await bot.set_my_commands(commands)
    await bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(chat_id=ADMIN_ID))

# -------------------- ХЕНДЛЕРЫ --------------------

@dp.message(Command('start'))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    add_or_update_user(user_id, username)

    custom_name = get_user_custom_name(user_id)
    if not custom_name:
        await message.answer("👋 Привет! Укажи, как тебя называть в игре (введи свой ник):")
        await state.set_state(GameStates.set_name)
        return

    points = get_user_points(user_id)
    await message.answer(
        f"🎲 Привет, {custom_name}! Добро пожаловать в игру 'Угадай кубик'!\n\n"
        "Правила:\n"
        "- Игра стоит 1 Ар 💎 за попытку.\n"
        "- Напиши число от 1 до 6.\n"
        "- Если угадаешь, Ар не снимается и ты получаешь +1 Ар!\n\n"
        f"Твои Ар: {points} 💎\n\n"
        "Введи число, чтобы начать!"
    )
    await state.set_state(GameStates.waiting)

@dp.message(Command('profile'))
async def profile_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    add_or_update_user(user_id, username)

    custom_name = get_user_custom_name(user_id) or "❌ не задан"
    points = get_user_points(user_id)

    await message.answer(
        f"📊 Твой профиль:\n"
        f"Имя (ник): {custom_name}\n"
        f"Telegram: {username}\n"
        f"Ар: {points} 💎\n\n"
        "Измени ник: /setname"
    )

@dp.message(Command('info'))
async def info_handler(message: Message):
    info_text = (
        "🎲 Добро пожаловать в игру «Угадай кубик»!\n\n"
        "Разработан и поддерживает - Arti55_PrOFi228\n\n"
        "Это исключительно игровой проект для сервера Axolotl.\n"
        "Вся валюта, которую вы выигрываете или проигрываете, — виртуальная и существует только на сервере Minecraft.\n\n"
        "Выигрыши начисляются на ваш игровой счет на сервере.\n\n"
        "Никаких реальных денежных переводов или выигрышей здесь нет.\n\n"
        "Играйте и получайте удовольствие в рамках игрового мира!\n\n"
        "Удачи! Надеемся увидеть вас в игре! ✨"
    )
    await message.answer(info_text)

@dp.message(Command('help'))
async def help_handler(message: Message):
    help_text = (
        "🆘 Помощь по боту:\n\n"
        "/start - Начать игру.\n"
        "/profile - Посмотреть свой профиль и Ар.\n"
        "/setname - Сменить ник.\n"
        "/withdraw - Запросить вывод Ар.\n"
        "/info - Информация об игре.\n"
        "/help - Показать список команд.\n\n"
        "В игре: Введи число от 1 до 6, чтобы угадать кубик 🎲\n"
        "Игра стоит 1 Ар за попытку, но если угадаешь, Ар не снимается и добавляется +1!"
    )
    if message.from_user.id == ADMIN_ID:
        help_text += (
            "\n\nАдмин-команды:\n"
            "/requests - Показать текущие запросы на вывод (pending).\n"
            "/requests_list - Показать все запросы на вывод (с фильтрами).\n"
            "/give_ar - Выдать Ар пользователю."
        )
    await message.answer(help_text)

@dp.message(Command('setname'))
async def change_name_handler(message: Message, state: FSMContext):
    await message.answer("✏️ Введи новый ник (от 3 до 20 символов):")
    await state.set_state(GameStates.set_name)

@dp.message(StateFilter(GameStates.set_name))
async def set_name_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    custom_name = message.text.strip()

    if len(custom_name) < 3 or len(custom_name) > 20:
        await message.answer("⚠️ Ник должен быть от 3 до 20 символов. Попробуй снова:")
        return

    set_user_custom_name(user_id, custom_name)
    points = get_user_points(user_id)
    await message.answer(
        f"✅ Отлично! Твой ник теперь: {custom_name}\n\n"
        f"У тебя {points} 💎 Ар.\n"
        "Введи число от 1 до 6, чтобы играть 🎲"
    )
    await state.set_state(GameStates.waiting)

@dp.message(Command('withdraw'))
async def withdraw_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    points = get_user_points(user_id)
    if points <= 0:
        await message.answer("😔 У тебя нет Ар для вывода!")
        return

    await message.answer(
        f"💰 Вывод Ар:\n"
        f"Твои Ар: {points} 💎\n"
        f"Введи количество Ар, которое хочешь вывести:"
    )
    await state.set_state(GameStates.withdraw_amount)

@dp.message(Command('give_ar'))
async def give_ar_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        return

    await message.answer("👤 Введи ник или Telegram-username (с @ или без) пользователя:")
    await state.set_state(GameStates.give_ar_user)

@dp.message(StateFilter(GameStates.give_ar_user))
async def give_ar_user_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        await state.clear()
        return

    name = message.text.strip()
    user_data = find_user_by_name(name)
    if not user_data:
        await message.answer("❌ Пользователь с таким ником или username не найден! Попробуй снова:")
        return

    user_id, custom_name, username = user_data
    await state.update_data(give_ar_user_id=user_id, give_ar_custom_name=custom_name or username)
    await message.answer(f"✅ Найден пользователь: {custom_name or username}\nВведи количество Ар для выдачи:")
    await state.set_state(GameStates.give_ar_amount)

@dp.message(StateFilter(GameStates.give_ar_amount))
async def give_ar_amount_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        await state.clear()
        return

    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ Количество должно быть положительным!")
            return
    except ValueError:
        await message.answer("❌ Это не число! Введи целое число.")
        return

    data = await state.get_data()
    user_id = data.get('give_ar_user_id')
    custom_name = data.get('give_ar_custom_name')

    if not user_id:
        await message.answer("❌ Ошибка: пользователь не выбран. Начни заново с /give_ar.")
        await state.clear()
        return

    update_points(user_id, amount)
    new_points = get_user_points(user_id)

    try:
        await bot.send_message(
            user_id,
            f"🎉 Администрация выдала тебе {amount} Ар! Теперь у тебя {new_points} 💎."
        )
    except:
        pass  # Игнорируем, если пользователь заблокировал бота

    await message.answer(
        f"✅ Выдано {amount} Ар пользователю {custom_name}!\n"
        f"Их текущий баланс: {new_points} 💎"
    )
    await state.clear()

@dp.message(Command('requests'))
async def requests_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        return

    pending_requests = get_requests(status_filter='pending')
    if not pending_requests:
        await message.answer("📭 Нет активных запросов на вывод.")
        return

    for req in pending_requests:
        request_id, user_id, custom_name, username, amount, status, timestamp = req
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{request_id}")
            ]
        ])
        await message.answer(
            f"🔔 Запрос #{request_id}:\n"
            f"Игрок: {custom_name or '—'}\n"
            f"Telegram: @{username if username else '—'} (ID: {user_id})\n"
            f"Сумма: {amount} 💎\n"
            f"Время: {timestamp}\n",
            reply_markup=keyboard
        )

@dp.message(Command('requests_list'))
async def requests_list_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Pending", callback_data="filter_pending"),
            InlineKeyboardButton(text="Approved", callback_data="filter_approved"),
            InlineKeyboardButton(text="Rejected", callback_data="filter_rejected"),
            InlineKeyboardButton(text="All", callback_data="filter_all")
        ]
    ])
    await message.answer(
        "📋 Выбери фильтр для списка запросов на вывод:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith('filter_'))
async def process_filter_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Доступ запрещен!")
        return

    filter_type = callback_query.data.split('_')[1]
    requests = get_requests(status_filter=filter_type)

    if not requests:
        await callback_query.message.answer(f"📭 Нет запросов со статусом '{filter_type}'.")
        await callback_query.answer()
        return

    for req in requests:
        request_id, user_id, custom_name, username, amount, status, timestamp = req
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{request_id}")
            ]
        ]) if status == 'pending' else None
        await callback_query.message.answer(
            f"📋 Запрос #{request_id}:\n"
            f"Игрок: {custom_name or '—'}\n"
            f"Telegram: @{username if username else '—'} (ID: {user_id})\n"
            f"Сумма: {amount} 💎\n"
            f"Статус: {status}\n"
            f"Время: {timestamp}\n",
            reply_markup=keyboard
        )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('approve_') or c.data.startswith('reject_'))
async def process_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Доступ запрещен!")
        return

    data = callback_query.data
    if data.startswith('approve_'):
        request_id = int(data.split('_')[1])
        status = 'approved'
    elif data.startswith('reject_'):
        request_id = int(data.split('_')[1])
        status = 'rejected'
    else:
        return

    user_id, amount = get_request_user_id(request_id)
    if not user_id:
        await callback_query.answer("❌ Запрос не найден!")
        return

    update_request_status(request_id, status)

    if status == 'approved':
        update_points(user_id, -amount)
        user_notification = f"✅ Ваш запрос на вывод {amount} Ар одобрен администрацией!"
    else:
        user_notification = f"❌ Ваш запрос на вывод {amount} Ар отклонен администрацией."

    try:
        await bot.send_message(user_id, user_notification)
    except:
        pass  # Игнорируем, если пользователь заблокировал бота

    await callback_query.answer(f"Запрос #{request_id} обновлен: {status}.")
    await bot.edit_message_reply_markup(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        reply_markup=None
    )

@dp.message(StateFilter(GameStates.waiting))
async def guess_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    add_or_update_user(user_id, message.from_user.username or message.from_user.first_name)

    try:
        user_guess = int(message.text.strip())
        if user_guess < 1 or user_guess > 6:
            await message.answer("❌ Введи число от 1 до 6!")
            return
    except ValueError:
        await message.answer("❌ Это не число! Введи число от 1 до 6.")
        return

    points = get_user_points(user_id)
    if points < 1:
        await message.answer("😔 Недостаточно Ар для игры! Нужно минимум 1 Ар 💎.")
        return

    # Снимаем 1 Ар за игру
    update_points(user_id, -1)
    await state.set_state(GameStates.playing)

    dice_message = await bot.send_dice(chat_id=message.chat.id, emoji="🎲")
    await asyncio.sleep(5)
    dice_value = dice_message.dice.value

    points_before = get_user_points(user_id)
    custom_name = get_user_custom_name(user_id) or "Игрок"
    if user_guess == dice_value:
        # Если угадал, возвращаем Ар за игру и добавляем +1
        update_points(user_id, 2)  # +1 за игру, +1 за победу
        new_points = points_before + 2
        result = (
            f"🎉 {custom_name}, ты угадал!\n"
            f"Твое число: {user_guess}\n"
            f"Выпало: {dice_value}\n"
            f"Ар за игру не снят, +1 Ар! Теперь у тебя {new_points} 💎"
        )
    else:
        new_points = points_before
        result = (
            f"😔 {custom_name}, не угадал!\n"
            f"Твое число: {user_guess}\n"
            f"Выпало: {dice_value}\n"
            f"Снят 1 Ар за игру. Твои Ар: {new_points} 💎\n"
            "Попробуй снова!"
        )

    await message.answer(result)
    await state.set_state(GameStates.waiting)

@dp.message(StateFilter(GameStates.withdraw_amount))
async def withdraw_amount_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    custom_name = get_user_custom_name(user_id) or "Игрок"
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ Количество должно быть положительным!")
            return
    except ValueError:
        await message.answer("❌ Это не число! Введи целое число.")
        return

    points = get_user_points(user_id)
    if amount > points:
        await message.answer(f"❌ У тебя только {points} Ар!")
        return

    request_id = create_withdraw_request(user_id, amount)

    username = message.from_user.username or "—"
    await bot.send_message(
        ADMIN_ID,
        f"🔔 Новый запрос #{request_id}:\n"
        f"Игрок: {custom_name}\n"
        f"Telegram: @{username} (ID: {user_id})\n"
        f"Сумма: {amount} 💎\n\n"
        "Используй /requests или /requests_list для обработки."
    )

    await message.answer(
        f"✅ Запрос на вывод {amount} Ар отправлен! Жди подтверждения.\n"
        f"Твои Ар пока: {points} 💎"
    )
    await state.set_state(GameStates.waiting)

@dp.message(StateFilter(GameStates.playing))
async def busy_handler(message: Message):
    await message.answer("⏳ Подожди, кубик ещё крутится!")

@dp.message()
async def default_handler(message: Message):
    await message.answer("🤔 Используй /start для начала игры или /help для справки.")

# -------------------- ЗАПУСК --------------------

async def main():
    init_db()
    await set_bot_commands()  # Устанавливаем команды при запуске
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())