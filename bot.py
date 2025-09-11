import os
import json
import logging
import requests
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram import InputFile

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

# Проверка наличия токенов
if not all([TELEGRAM_TOKEN, YANDEX_TOKEN]):
    logger.error("Отсутствуют необходимые токены в .env файле")
    raise ValueError("TELEGRAM_TOKEN и YANDEX_TOKEN должны быть указаны в .env файле")

FIXED_FOLDER = '/documents/'

def load_allowed_admins():
    try:
        with open('allowed_admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл allowed_admins.json не найден, используется стандартный ID")
        return [123456789]  # Замените на ваш user_id

def save_allowed_admins(allowed_admins):
    try:
        with open('allowed_admins.json', 'w') as f:
            json.dump(allowed_admins, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения allowed_admins.json: {str(e)}")

ALLOWED_ADMINS = load_allowed_admins()

def load_allowed_users():
    try:
        with open('allowed_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл allowed_users.json не найден")
        return []

def save_allowed_users(allowed_users):
    try:
        with open('allowed_users.json', 'w') as f:
            json.dump(allowed_users, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения allowed_users.json: {str(e)}")

ALLOWED_USERS = load_allowed_users()

histories = {}

def list_yandex_disk_files(folder_path):
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={folder_path}&fields=items.name,items.type,items.path&limit=100'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json().get('_embedded', {}).get('items', [])
            return [item for item in items if item['type'] == 'file']
        else:
            logger.error(f"Ошибка Яндекс.Диска: код {response.status_code}, текст: {response.text}")
            return []
    except Exception as e:
        logger.error(f"Ошибка при запросе списка файлов: {str(e)}")
        return []

def get_yandex_disk_file(file_path):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={file_path}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get('href')
        else:
            logger.error(f"Ошибка Яндекс.Диска: код {response.status_code}, текст: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к Яндекс.Диску: {str(e)}")
        return None

def upload_to_yandex_disk(file_name, file_content):
    path = FIXED_FOLDER + file_name
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={path}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            upload_url = response.json()['href']
            upload_response = requests.put(upload_url, data=file_content)
            if upload_response.status_code == 201:
                logger.info(f"Файл {file_name} успешно загружен на Яндекс.Диск")
                return True
            else:
                logger.error(f"Ошибка загрузки файла {file_name}: код {upload_response.status_code}")
                return False
        else:
            logger.error(f"Ошибка получения URL для загрузки: код {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла на Яндекс.Диск: {str(e)}")
        return False

async def send_welcome(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    logger.info(f"send_welcome: user_id={user_id}, is_admin={user_id in ALLOWED_ADMINS}")

    context.user_data.clear()
    context.user_data["awaiting_name"] = True

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text(
            f"Ваш user_id: {user_id}\nИзвините, у вас нет доступа к этому боту. Передайте ваш user_id администратору.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"Пользователь {user_id} попытался получить доступ, но не в списке разрешённых")
        return

    keyboard = [
        ['Управление пользователями', 'Скачать файл'],
        ['Загрузить файл']
    ] if user_id in ALLOWED_ADMINS else [['Скачать файл']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    await update.message.reply_text(
        f"Ваш user_id: {user_id}\nПривет! Я бот для работы с файлами на Яндекс.Диске. Как тебя зовут?",
        reply_markup=reply_markup
    )
    if chat_id not in histories:
        histories[chat_id] = {"name": None, "messages": []}
    logger.info(f"Пользователь {chat_id} начал чат с /start. Клавиатура: {keyboard}")

async def get_file(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался скачать файл, но не в списке разрешённых")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите название файла (например, file.pdf).")
        return

    file_name = ' '.join(context.args).strip()
    await search_and_send_file(update, context, file_name)

async def search_and_send_file(update, context, file_name):
    if not (file_name.endswith('.pdf') or file_name.endswith('.doc') or file_name.endswith('.docx')):
        await update.message.reply_text("Пожалуйста, укажите файл формата PDF или Word (.pdf, .doc, .docx).")
        return

    files = list_yandex_disk_files(FIXED_FOLDER)
    matching_file = next((item for item in files if item['name'].lower() == file_name.lower()), None)

    if not matching_file:
        await update.message.reply_text(f"Файл '{file_name}' не найден в папке {FIXED_FOLDER}.")
        return

    file_path = matching_file['path']
    download_url = get_yandex_disk_file(file_path)
    if download_url:
        try:
            file_response = requests.get(download_url)
            if file_response.status_code == 200:
                file_size = len(file_response.content) / (1024 * 1024)  # Размер в МБ
                if file_size > 20:
                    await update.message.reply_text("Файл слишком большой (>20 МБ). Telegram не позволяет отправлять такие файлы.")
                    logger.error(f"Файл {file_name} слишком большой: {file_size} МБ")
                    return
                await update.message.reply_document(
                    document=InputFile(file_response.content, filename=file_name),
                    caption=f"Файл {file_name} из {FIXED_FOLDER}"
                )
                logger.info(f"Файл {file_name} успешно отправлен пользователю {update.effective_user.id}")
            else:
                await update.message.reply_text("Не удалось загрузить файл с Яндекс.Диска.")
                logger.error(f"Ошибка загрузки файла {file_path}: код {file_response.status_code}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка при отправке файла: {str(e)}")
            logger.error(f"Ошибка при отправке файла {file_path}: {str(e)}")
    else:
        await update.message.reply_text("Файл не найден на Яндекс.Диске или произошла ошибка.")
        logger.error(f"Файл {file_path} не найден на Яндекс.Диске")

async def handle_document(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл'],
        ['Загрузить файл']
    ] if user_id in ALLOWED_ADMINS else [['Скачать файл']]
    default_reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True, one_time_keyboard=False)

    if user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, только администраторы могут загружать файлы.", reply_markup=default_reply_markup)
        logger.info(f"Пользователь {user_id} попытался загрузить файл, но не является администратором")
        return

    if not context.user_data.get('awaiting_file', False):
        await update.message.reply_text("Пожалуйста, используйте кнопку 'Загрузить файл' для загрузки.", reply_markup=default_reply_markup)
        return

    document = update.message.document
    file_name = document.file_name
    if not (file_name.endswith('.pdf') or file_name.endswith('.doc') or file_name.endswith('.docx')):
        await update.message.reply_text("Пожалуйста, загружайте файлы только в формате PDF или Word (.pdf, .doc, .docx).", reply_markup=default_reply_markup)
        return

    try:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        success = upload_to_yandex_disk(file_name, file_content)
        if success:
            await update.message.reply_text(f"Файл '{file_name}' успешно загружен в папку {FIXED_FOLDER}.", reply_markup=default_reply_markup)
        else:
            await update.message.reply_text("Ошибка при загрузке файла на Яндекс.Диск.", reply_markup=default_reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке файла: {str(e)}", reply_markup=default_reply_markup)
        logger.error(f"Ошибка при обработке документа: {str(e)}")

    context.user_data.pop('awaiting_file', None)

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    logger.info(f"Получено сообщение от {chat_id} (user_id: {user_id}): {user_input}")

    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл'],
        ['Загрузить файл']
    ] if user_id in ALLOWED_ADMINS else [['Скачать файл']]
    default_reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True, one_time_keyboard=False)

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался отправить сообщение, но не в списке разрешённых")
        return

    if context.user_data.get("awaiting_name", False):
        histories[chat_id]["name"] = user_input
        context.user_data["awaiting_name"] = False
        await update.message.reply_text(
            f"Рад знакомству, {user_input}! Используй кнопки для работы с файлами или задавай вопросы.",
            reply_markup=default_reply_markup
        )
        logger.info(f"Имя пользователя {chat_id} сохранено: {user_input}")
        return

    if user_input == "Управление пользователями":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут управлять пользователями.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался использовать управление пользователями")
            return
        keyboard = [
            ['Добавить пользователя', 'Добавить администратора'],
            ['Список пользователей', 'Список администраторов'],
            ['Назад']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        logger.info(f"Администратор {user_id} запросил управление пользователями")
        return

    if user_input == "Скачать файл":
        await update.message.reply_text("Укажите название файла (например, file.pdf).", reply_markup=default_reply_markup)
        logger.info(f"Пользователь {user_id} запросил скачивание файла")
        return

    if user_input == "Загрузить файл":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут загружать файлы.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался загрузить файл")
            return
        context.user_data['awaiting_file'] = True
        await update.message.reply_text("Отправьте файл для загрузки (PDF, DOC или DOCX).", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил загрузку файла")
        return

    if user_input == "Назад":
        await update.message.reply_text("Возвращение в главное меню.", reply_markup=default_reply_markup)
        logger.info(f"Пользователь {user_id} вернулся в главное меню")
        return

    if context.user_data.get('awaiting_user_id'):
        try:
            new_id = int(user_input)
            if context.user_data['awaiting_user_id'] == 'add_user':
                if new_id in ALLOWED_USERS:
                    await update.message.reply_text(f"Пользователь с ID {new_id} уже имеет доступ.", reply_markup=default_reply_markup)
                    return
                ALLOWED_USERS.append(new_id)
                save_allowed_users(ALLOWED_USERS)
                await update.message.reply_text(f"Пользователь с ID {new_id} добавлен!", reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} добавил пользователя {new_id}")
            elif context.user_data['awaiting_user_id'] == 'add_admin':
                if new_id in ALLOWED_ADMINS:
                    await update.message.reply_text(f"Пользователь с ID {new_id} уже администратор.", reply_markup=default_reply_markup)
                    return
                ALLOWED_ADMINS.append(new_id)
                save_allowed_admins(ALLOWED_ADMINS)
                await update.message.reply_text(f"Пользователь с ID {new_id} назначен администратором!", reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} назначил администратора {new_id}")
            context.user_data.pop('awaiting_user_id')
        except ValueError:
            await update.message.reply_text("Ошибка: user_id должен быть числом.", reply_markup=default_reply_markup)
            logger.error(f"Неверный формат user_id от {user_id}")
        return

    if user_input == "Добавить пользователя":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут добавлять пользователей.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить пользователя")
            return
        context.user_data['awaiting_user_id'] = 'add_user'
        await update.message.reply_text("Укажите user_id для добавления.", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил добавление пользователя")
        return

    if user_input == "Добавить администратора":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут назначать администраторов.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить администратора")
            return
        context.user_data['awaiting_user_id'] = 'add_admin'
        await update.message.reply_text("Укажите user_id для назначения администратором.", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил добавление администратора")
        return

    if user_input == "Список пользователей":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут просматривать список пользователей.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался просмотреть список пользователей")
            return
        if not ALLOWED_USERS:
            await update.message.reply_text("Список пользователей пуст.", reply_markup=default_reply_markup)
            return
        users_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_USERS])
        await update.message.reply_text(f"Разрешённые пользователи:\n{users_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список пользователей")
        return

    if user_input == "Список администраторов":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут просматривать список администраторов.", reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался просмотреть список администраторов")
            return
        if not ALLOWED_ADMINS:
            await update.message.reply_text("Список администраторов пуст.", reply_markup=default_reply_markup)
            return
        admins_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_ADMINS])
        await update.message.reply_text(f"Администраторы:\n{admins_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список администраторов")
        return

    if user_input.lower().endswith(('.pdf', '.doc', '.docx')):
        await search_and_send_file(update, context, user_input)
        return

    user_name = histories[chat_id]["name"] or "Друг"
    await update.message.reply_text(
        f"{user_name}, я получил твое сообщение: '{user_input}'. Используй кнопки для работы с файлами.",
        reply_markup=default_reply_markup
    )

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка, попробуйте позже.")

def main():
    logger.info("Запуск Telegram бота...")
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", send_welcome))
        app.add_handler(CommandHandler("getfile", get_file))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.DOCUMENT, handle_document))
        app.add_error_handler(error_handler)
        app.run_polling()
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {str(e)}")
        raise

if __name__ == "__main__":
    main()