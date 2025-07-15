import telebot
import os
import json
import pandas as pd
import threading
import time

# Конфигурация бота
API_TOKEN = '7415306603:AAH_8HD2is4BR84yKVpAI5qKIJ-pT7MHLaQ'
bot = telebot.TeleBot(API_TOKEN)

# Пути к директориям и файлам
EXCEL_FILE_DIR   = 'tables'
EXCEL_FILE_PATH  = os.path.join(EXCEL_FILE_DIR, 'uploaded_data.xlsx')
DATE_FILE_PATH   = os.path.join(EXCEL_FILE_DIR, 'date.txt')
AUTH_FILE_PATH   = os.path.join(EXCEL_FILE_DIR, 'authorized_users.json')

# Словарь пользователей, паролей и псевдонимов
USER_PASSWORDS = {
    "Accountant": {"password": "123", "alias": "Accountant"},
    "КДЕ":       {"password": "208", "alias": "КДЕ"},
    "ЩПЮ":      {"password": "210", "alias": "ЩПЮ"},
    "ПАН":      {"password": "212", "alias": "ПАН"},
    "СКН":      {"password": "204", "alias": "СКН"},
    "ИМВ":      {"password": "207", "alias": "ИМВ"},
    "СНВ":      {"password": "158", "alias": "СНВ"},
    "СЦДС":     {"password": "441", "alias": "СЦДС"},
    "САВ":      {"password": "748", "alias": "САВ"},
    "ЭО":       {"password": "283", "alias": "ЭО"},
    "БАЕ":      {"password": "301", "alias": "БАЕ"},
    "ВЕВ":      {"password": "302", "alias": "ВЕВ"},
}

# Хранение состояний (многошаговки)
user_states = {}

# Загрузка/сохранение списка авторизованных
def load_authorized_users():
    if not os.path.exists(AUTH_FILE_PATH):
        return {u: [] for u in USER_PASSWORDS}
    with open(AUTH_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for u in USER_PASSWORDS:
        data.setdefault(u, [])
    return data

def save_authorized_users(data):
    if not os.path.exists(EXCEL_FILE_DIR):
        os.makedirs(EXCEL_FILE_DIR)
    with open(AUTH_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

authorized_users = load_authorized_users()

# Обеспечиваем папку
if not os.path.exists(EXCEL_FILE_DIR):
    os.makedirs(EXCEL_FILE_DIR)

# Отправка временных сообщений
def send_temp_message(chat_id, text, delay=43200):
    msg = bot.send_message(chat_id, text)
    threading.Thread(
        target=delete_message_after_delay,
        args=(chat_id, msg.message_id, delay),
        daemon=True
    ).start()

def delete_message_after_delay(chat_id, message_id, delay):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

# Обработчик /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Бухгалтеру не нужно вводить пароль
    if message.chat.id in authorized_users.get("Accountant", []):
        # Просто шлём ему актуальную таблицу сразу
        send_user_data(message.chat.id, "Accountant")
    else:
        user_states.pop(message.chat.id, None)
        send_temp_message(message.chat.id, "👋 Привет! Введите пароль для доступа:")

# Универсальный текстовый хендлер
@bot.message_handler(func=lambda m: True)
def check_password(message):
    state = user_states.get(message.chat.id, {})
    # Если ожидаем дату или комментарий — передаём дальше
    if state.get('awaiting_date'):
        handle_date_input(message)
        return
    if state.get('awaiting_comment'):
        handle_comment_input(message)
        return

    # Проверяем пароль
    user = next((u for u,c in USER_PASSWORDS.items() if message.text == c['password']), None)
    if not user:
        send_temp_message(message.chat.id, "❌ Неверный пароль!")
        return

    # Успешная авторизация
    user_states[message.chat.id] = {'user': user}
    if message.chat.id not in authorized_users[user]:
        authorized_users[user].append(message.chat.id)
        save_authorized_users(authorized_users)

    send_temp_message(message.chat.id, f"✅ Добро пожаловать, {user}!")

    # Если не бухгалтер — сразу шлём данные
    if user != "Accountant":
        send_user_data(message.chat.id, user)

# Приём Excel от бухгалтера
@bot.message_handler(content_types=['document'])
def handle_document(message):
    # Только бухгалтер
    if message.chat.id not in authorized_users.get("Accountant", []):
        send_temp_message(message.chat.id, "❌ У вас нет прав.")
        return
    try:
        # Переписываем файлы
        if os.path.exists(EXCEL_FILE_PATH): os.remove(EXCEL_FILE_PATH)
        if os.path.exists(DATE_FILE_PATH): os.remove(DATE_FILE_PATH)

        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with open(EXCEL_FILE_PATH, 'wb') as f:
            f.write(downloaded)

        user_states[message.chat.id]['awaiting_date'] = True
        send_temp_message(message.chat.id,
            "✅ Файл получен! Введите дату отчёта (DD.MM.YYYY):"
        )
    except Exception as e:
        send_temp_message(message.chat.id, f"⚠️ Ошибка: {e}")

# Обработка даты отчёта
def handle_date_input(message):
    if message.chat.id not in authorized_users.get("Accountant", []) or \
       not user_states.get(message.chat.id, {}).get('awaiting_date'):
        send_temp_message(message.chat.id, "⚠️ Сначала загрузите файл.")
        return

    date = message.text.strip()
    with open(DATE_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(date)

    user_states[message.chat.id]['awaiting_date'] = False
    send_temp_message(message.chat.id, f"🗓️ Дата {date} сохранена! Всем отправлены уведомления.")

    # === Рассылка уведомлений (кроме бухгалтера) ===
    for role, ids in authorized_users.items():
        if role == "Accountant":
            continue
        for cid in ids:
            send_temp_message(cid,
                f"📢 Бухгалтер обновил таблицу за {date}.\n"
                "Чтобы просмотреть — введите ваш пароль:"
            )

    # Сбрасываем авторизацию в памяти (файл сохраняет список для сброса при рестарте)
    for role in authorized_users:
        if role != "Accountant":
            authorized_users[role].clear()
    save_authorized_users(authorized_users)

# Отправка данных пользователю
def send_user_data(chat_id, user_key):
    alias = USER_PASSWORDS[user_key]['alias']
    # Бухгалтеру полный файл
    if user_key == "Accountant":
        if os.path.exists(EXCEL_FILE_PATH):
            with open(EXCEL_FILE_PATH, 'rb') as f:
                bot.send_document(chat_id, f)
        return

    # Для КДЕ полный, для остальных — фильтр
    if user_key == "КДЕ":
        with open(EXCEL_FILE_PATH, 'rb') as f:
            bot.send_document(chat_id, f)
    else:
        filtered = filter_excel_data_for_user(EXCEL_FILE_PATH, alias)
        with open(filtered, 'rb') as f:
            bot.send_document(chat_id, f)

    # Сообщение с датой
    date = open(DATE_FILE_PATH).read().strip() if os.path.exists(DATE_FILE_PATH) else 'не указана'
    send_temp_message(chat_id, f"📊 Данные за {date} для {alias}.")

    # Кнопки подтверждения
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton('Подтвердить данные', callback_data='confirm_all'),
        telebot.types.InlineKeyboardButton('Подтвердить всё, кроме...', callback_data='confirm_except'),
    )
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# Фильтрация Excel
def filter_excel_data_for_user(file_path, alias):
    df = pd.read_excel(file_path)
    if alias != 'КДЕ':
        for col in ['+', '-']:
            if col in df.columns:
                df.drop(columns=[col], inplace=True)
    df_filtered = df[df['РУК-ЛЬ'] == alias]
    out = os.path.join(EXCEL_FILE_DIR, f"filtered_{alias}.xlsx")
    df_filtered.to_excel(out, index=False)
    return out

# Обработка кнопок
@bot.callback_query_handler(func=lambda c: c.data.startswith('confirm_'))
def confirm_data(call):
    action = call.data
    user_key = user_states.get(call.message.chat.id, {}).get('user')

    if action == 'confirm_all':
        send_temp_message(call.message.chat.id, '👍 Вы подтвердили все данные.')
        # === Обязательно уведомляем бухгалтера ===
        for cid in authorized_users.get("Accountant", []):
            send_temp_message(cid, f"{user_key} подтвердил(а) все данные.")
    else:  # confirm_except
        user_states[call.message.chat.id]['awaiting_comment'] = True
        send_temp_message(call.message.chat.id, '📝 Укажите, что не подтверждаете:')

def handle_comment_input(message):
    if not user_states.get(message.chat.id, {}).get('awaiting_comment'):
        return
    comment = message.text.strip()
    user_key = user_states[message.chat.id]['user']

    send_temp_message(message.chat.id, '📝 Комментарий получен.')
    for cid in authorized_users.get("Accountant", []):
        send_temp_message(cid, f"{user_key} не подтвердил(а): {comment}")

    user_states[message.chat.id]['awaiting_comment'] = False

if __name__ == '__main__':
    bot.infinity_polling()
