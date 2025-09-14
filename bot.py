import os
import json
import logging
import requests
import random
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from duckduckgo_search import DDGS
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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

# Словарь федеральных округов и их регионов
FEDERAL_DISTRICTS = {
    "Центральный федеральный округ": [
        "Белгородская область", "Брянская область", "Владимирская область", "Воронежская область",
        "Ивановская область", "Калужская область", "Костромская область", "Курская область",
        "Липецкая область", "Московская область", "Орловская область", "Рязанская область",
        "Смоленская область", "Тамбовская область", "Тверская область", "Тульская область",
        "Ярославская область", "Москва"
    ],
    "Северо-Западный федеральный округ": [
        "Республика Карелия", "Республика Коми", "Архангельская область", "Вологодская область",
        "Ленинградская область", "Мурманская область", "Новгородская область", "Псковская область",
        "Калининградская область", "Ненецкий автономный округ", "Санкт-Петербург"
    ],
    "Южный федеральный округ": [
        "Республика Адыгея", "Республика Калмыкия", "Республика Крым", "Краснодарский край",
        "Астраханская область", "Волгоградская область", "Ростовская область", "Севастополь"
    ],
    "Северо-Кавказский федеральный округ": [
        "Республика Дагестан", "Республика Ингушетия", "Кабардино-Балкарская Республика",
        "Карачаево-Черкесская Республика", "Республика Северная Осетия — Алания",
        "Чеченская Республика", "Ставропольский край"
    ],
    "Приволжский федеральный округ": [
        "Республика Башкортостан", "Республика Марий Эл", "Республика Мордовия", "Республика Татарстан",
        "Удмуртская Республика", "Чувашская Республика", "Кировская область", "Нижегородская область",
        "Оренбургская область", "Пензенская область", "Пермский край", "Самарская область",
        "Саратовская область", "Ульяновская область"
    ],
    "Уральский федеральный округ": [
        "Курганская область", "Свердловская область", "Тюменская область", "Ханты-Мансийский автономный округ — Югра",
        "Челябинская область", "Ямало-Ненецкий автономный округ"
    ],
    "Сибирский федеральный округ": [
        "Республика Алтай", "Республика Тыва", "Республика Хакасия", "Алтайский край",
        "Красноярский край", "Иркутская область", "Кемеровская область", "Новосибирская область",
        "Омская область", "Томская область", "Забайкальский край"
    ],
    "Дальневосточный федеральный округ": [
        "Республика Саха (Якутия)", "Приморский край", "Хабаровский край", "Амурская область",
        "Камчатский край", "Магаданская область", "Сахалинская область", "Еврейская автономная область",
        "Чукотский автономный округ"
    ]
}


def load_allowed_admins():
    try:
        with open('allowed_admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return [123456789]  # Замените на ваш user_id


def save_allowed_admins(allowed_admins):
    with open('allowed_admins.json', 'w') as f:
        json.dump(allowed_admins, f, ensure_ascii=False)


ALLOWED_ADMINS = load_allowed_admins()


def load_allowed_users():
    try:
        with open('allowed_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_allowed_users(allowed_users):
    with open('allowed_users.json', 'w') as f:
        json.dump(allowed_users, f, ensure_ascii=False)


ALLOWED_USERS = load_allowed_users()


def load_user_profiles():
    try:
        with open('user_profiles.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_user_profiles(profiles):
    with open('user_profiles.json', 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


USER_PROFILES = load_user_profiles()


def load_qa_database():
    try:
        with open('qa_database.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл qa_database.json не найден. QA-функция отключена.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка чтения qa_database.json: {str(e)}")
        return {}


def find_qa_match(user_input, qa_db):
    user_lower = user_input.lower()
    for question, answers in qa_db.items():
        question_lower = question.lower()
        user_words = set(user_lower.split())
        question_words = set(question_lower.split())
        if user_words.intersection(question_words):
            return random.choice(answers)
    return None


system_prompt = """
Вы — полезный чат-бот, который логически анализирует всю историю переписки, чтобы давать последовательные ответы.
Если вопрос пользователя требует актуальной информации или данных, которых у вас нет, используйте функцию web_search для поиска в интернете.
Всегда учитывайте полный контекст разговора перед ответом.
Отвечайте кратко и по делу, на русском языке.
"""

histories = {}
qa_database = load_qa_database()


def create_yandex_folder(folder_path):
    root_folder = '/regions'
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={root_folder}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}', 'Content-Type': 'application/json'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            response = requests.put(url, headers=headers)
            if response.status_code not in (201, 409):
                logger.error(
                    f"Ошибка создания корневой папки {root_folder}: код {response.status_code}, текст: {response.text}")
                return False
            logger.info(f"Корневая папка {root_folder} успешно создана.")

        url = f'https://cloud-api.yandex.net/v1/disk/resources?path={folder_path}'
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            logger.info(f"Папка {folder_path} уже существует.")
            return True
        response = requests.put(url, headers=headers)
        if response.status_code in (201, 409):
            logger.info(f"Папка {folder_path} успешно создана.")
            return True
        else:
            logger.error(f"Ошибка создания папки {folder_path}: код {response.status_code}, текст: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при создании папки {folder_path}: {str(e)}")
        return False


def list_yandex_disk_files(folder_path):
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={folder_path}&fields=items.name,items.type,items.path&limit=100'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json().get('_embedded', {}).get('items', [])
            return [item for item in items if item['type'] == 'file' and item['name'].lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))]
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


def upload_to_yandex_disk(file_content, file_name, folder_path):
    file_path = folder_path + file_name
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={file_path}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            upload_url = response.json().get('href')
            if upload_url:
                upload_response = requests.put(upload_url, data=file_content)
                if upload_response.status_code in (201, 202):
                    logger.info(f"Файл {file_name} успешно загружен на Яндекс.Диск в {folder_path}")
                    return True
                else:
                    logger.error(
                        f"Ошибка загрузки на Яндекс.Диск: код {upload_response.status_code}, текст: {upload_response.text}")
                    return False
            else:
                logger.error("Не получен URL для загрузки")
                return False
        else:
            logger.error(f"Ошибка получения URL загрузки: код {response.status_code}, текст: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при загрузке на Яндекс.Диск: {str(e)}")
        return False


def web_search(query):
    cache_file = 'search_cache.json'
    try:
        with open('search_cache.json', 'r') as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}
    if query in cache:
        logger.info(f"Использую кэш для запроса: {query}")
        return cache[query]
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
        search_results = json.dumps(results, ensure_ascii=False, indent=2)
        cache[query] = search_results
        with open('search_cache.json', 'w') as f:
            json.dump(cache, f, ensure_ascii=False)
        logger.info(f"Поиск выполнен для запроса: {query}")
        return search_results
    except Exception as e:
        logger.error(f"Ошибка при поиске в интернете: {str(e)}")
        return json.dumps({"error": "Не удалось выполнить поиск."}, ensure_ascii=False)


async def send_welcome(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    context.user_data.pop('awaiting_user_id', None)
    context.user_data.pop('awaiting_fio', None)
    context.user_data.pop('awaiting_federal_district', None)
    context.user_data.pop('awaiting_region', None)
    context.user_data.pop('selected_federal_district', None)

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        welcome_message = f"Ваш user_id: {user_id}\nИзвините, у вас нет доступа к этому боту. Передайте ваш user_id администратору для получения доступа."
        await update.message.reply_text(welcome_message, reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался получить доступ, но не в списке разрешённых.")
        return

    if user_id not in USER_PROFILES:
        context.user_data["awaiting_fio"] = True
        welcome_message = "Доброго времени суток!\nДля начала работы необходимо пройти регистрацию, напишите свое ФИО."
        await update.message.reply_text(welcome_message, reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {chat_id} начал регистрацию.")
        return

    profile = USER_PROFILES[user_id]
    if profile.get("name") is None:
        context.user_data["awaiting_name"] = True
        await update.message.reply_text("Как я могу к Вам обращаться (кратко для удобства)?",
                                       reply_markup=ReplyKeyboardRemove())
    else:
        await show_main_menu(update, context)


async def show_main_menu(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ] if user_id in ALLOWED_ADMINS else [
        ['Скачать файл', 'Список всех файлов']
    ]
    reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)
    context.user_data['default_reply_markup'] = reply_markup
    # Клавиатура отображается без текста


async def get_file(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался скачать файл, но не в списке разрешённых.")
        return

    if user_id not in USER_PROFILES:
        await update.message.reply_text("Сначала пройдите регистрацию с /start.")
        return

    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, укажите название файла (например, file.pdf). Файл будет искаться в вашей региональной папке.")
        return

    file_name = ' '.join(context.args).strip()
    await search_and_send_file(update, context, file_name)


async def search_and_send_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str):
    user_id = update.effective_user.id
    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: регион не определён. Перезапустите /start.")
        logger.error(f"Ошибка: регион не определён для пользователя {user_id}.")
        return

    region_folder = f"/regions/{profile['region']}/"
    if not (file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))):
        await update.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
        logger.error(f"Неподдерживаемый формат файла {file_name} для пользователя {user_id}.")
        return

    files = list_yandex_disk_files(region_folder)
    matching_file = next((item for item in files if item['name'].lower() == file_name.lower()), None)

    if not matching_file:
        await update.message.reply_text(f"Файл '{file_name}' не найден в папке {region_folder}.")
        logger.info(f"Файл '{file_name}' не найден для пользователя {user_id} в {region_folder}.")
        return

    file_path = matching_file['path']
    download_url = get_yandex_disk_file(file_path)
    if not download_url:
        await update.message.reply_text("Ошибка: не удалось получить ссылку для скачивания файла с Яндекс.Диска.")
        logger.error(f"Не удалось получить ссылку для файла {file_path}.")
        return

    try:
        file_response = requests.get(download_url)
        if file_response.status_code == 200:
            file_size = len(file_response.content) / (1024 * 1024)
            if file_size > 20:
                await update.message.reply_text(
                    "Файл слишком большой (>20 МБ). Telegram не позволяет отправлять такие файлы.")
                logger.error(f"Файл {file_name} слишком большой: {file_size} МБ")
                return
            await update.message.reply_document(
                document=InputFile(file_response.content, filename=file_name)
            )
            logger.info(f"Файл {file_name} успешно отправлен пользователю {user_id} из {region_folder}")
        else:
            await update.message.reply_text("Не удалось загрузить файл с Яндекс.Диска.")
            logger.error(
                f"Ошибка загрузки файла {file_path}: код {file_response.status_code}, текст: {file_response.text}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке файла: {str(e)}")
        logger.error(f"Ошибка при отправке файла {file_path}: {str(e)}")


async def handle_document(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_ADMINS:
        logger.info(f"Пользователь {user_id} отправил документ, но не является администратором.")
        return

    if not context.user_data.get('awaiting_upload', False):
        await update.message.reply_text("Пожалуйста, используйте кнопку 'Загрузить файл' перед отправкой документа.")
        return

    document = update.message.document
    file_name = document.file_name
    if not (file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))):
        await update.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
        return

    file_size = document.file_size / (1024 * 1024)
    if file_size > 50:
        await update.message.reply_text("Файл слишком большой (>50 МБ).")
        return

    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: у вас не определён регион. Обновите профиль с /start.")
        return
    region_folder = f"/regions/{profile['region']}/"

    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        if upload_to_yandex_disk(file_content, file_name, region_folder):
            await update.message.reply_text("Файл успешно загружен в папку")
        else:
            await update.message.reply_text("Ошибка при загрузке файла на Яндекс.Диск.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке файла: {str(e)}")
        logger.error(f"Ошибка обработки документа от {user_id}: {str(e)}")

    context.user_data.pop('awaiting_upload', None)
    logger.info(f"Администратор {user_id} загрузил файл {file_name} в {region_folder}.")


async def show_file_list(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: у вас не определён регион. Обновите профиль с /start.",
                                       reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
        logger.error(f"Ошибка: регион не определён для пользователя {user_id}.")
        return

    region_folder = f"/regions/{profile['region']}/"
    files = list_yandex_disk_files(region_folder)

    if not files:
        await update.message.reply_text(f"В папке {region_folder} нет файлов.",
                                       reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
        logger.info(f"Папка {region_folder} пуста для пользователя {user_id}.")
        return

    # Создаём инлайн-кнопки для каждого файла
    keyboard = []
    for item in files:
        callback_data = f"download:{item['name']}"
        if len(callback_data.encode('utf-8')) > 64:
            logger.warning(f"callback_data для файла {item['name']} слишком длинное: {len(callback_data.encode('utf-8'))} байт")
            continue
        keyboard.append([InlineKeyboardButton(item['name'], callback_data=callback_data)])
    if not keyboard:
        await update.message.reply_text("Ошибка: имена файлов слишком длинные для отображения.",
                                       reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
        logger.error(f"Все callback_data для файлов в {region_folder} превышают лимит 64 байта.")
        return
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Список всех файлов:",
        reply_markup=reply_markup
    )
    logger.info(f"Пользователь {user_id} запросил список файлов в {region_folder}.")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    if query.data.startswith("download:"):
        file_name = query.data.split(":", 1)[1]
        profile = USER_PROFILES.get(user_id)
        if not profile or "region" not in profile:
            await query.message.reply_text("Ошибка: регион не определён. Перезапустите /start.")
            logger.error(f"Ошибка: регион не определён для пользователя {user_id}.")
            return

        region_folder = f"/regions/{profile['region']}/"
        if not (file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))):
            await query.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
            logger.error(f"Неподдерживаемый формат файла {file_name} для пользователя {user_id}.")
            return

        files = list_yandex_disk_files(region_folder)
        matching_file = next((item for item in files if item['name'].lower() == file_name.lower()), None)

        if not matching_file:
            await query.message.reply_text(f"Файл '{file_name}' не найден в папке {region_folder}.")
            logger.info(f"Файл '{file_name}' не найден для пользователя {user_id} в {region_folder}.")
            return

        file_path = matching_file['path']
        download_url = get_yandex_disk_file(file_path)
        if not download_url:
            await query.message.reply_text("Ошибка: не удалось получить ссылку для скачивания файла с Яндекс.Диска.")
            logger.error(f"Не удалось получить ссылку для файла {file_path}.")
            return

        try:
            file_response = requests.get(download_url)
            if file_response.status_code == 200:
                file_size = len(file_response.content) / (1024 * 1024)
                if file_size > 20:
                    await query.message.reply_text(
                        "Файл слишком большой (>20 МБ). Telegram не позволяет отправлять такие файлы.")
                    logger.error(f"Файл {file_name} слишком большой: {file_size} МБ")
                    return
                await query.message.reply_document(
                    document=InputFile(file_response.content, filename=file_name)
                )
                logger.info(f"Файл {file_name} успешно отправлен пользователю {user_id} из {region_folder}")
            else:
                await query.message.reply_text("Не удалось загрузить файл с Яндекс.Диска.")
                logger.error(
                    f"Ошибка загрузки файла {file_path}: код {file_response.status_code}, текст: {file_response.text}")
        except Exception as e:
            await query.message.reply_text(f"Ошибка при отправке файла: {str(e)}")
            logger.error(f"Ошибка при отправке файла {file_path}: {str(e)}")


async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    logger.info(f"Получено сообщение от {chat_id} (user_id: {user_id}): {user_input}")

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался отправить сообщение, но не в списке разрешённых.")
        return

    if user_id not in USER_PROFILES:
        if context.user_data.get("awaiting_fio", False):
            USER_PROFILES[user_id] = {"fio": user_input, "name": None, "region": None}
            save_user_profiles(USER_PROFILES)
            context.user_data["awaiting_fio"] = False
            context.user_data["awaiting_federal_district"] = True
            keyboard = [[district] for district in FEDERAL_DISTRICTS.keys()]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Выберите федеральный округ:", reply_markup=reply_markup)
            return
        else:
            await update.message.reply_text("Сначала пройдите регистрацию с /start.")
            return

    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ] if user_id in ALLOWED_ADMINS else [
        ['Скачать файл', 'Список всех файлов']
    ]
    default_reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)

    if context.user_data.get("awaiting_federal_district", False):
        if user_input in FEDERAL_DISTRICTS:
            context.user_data["selected_federal_district"] = user_input
            context.user_data["awaiting_federal_district"] = False
            context.user_data["awaiting_region"] = True
            regions = FEDERAL_DISTRICTS[user_input]
            keyboard = [[region] for region in regions]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text("Выберите регион:", reply_markup=reply_markup)
            return
        else:
            await update.message.reply_text("Пожалуйста, выберите из предложенных округов.")
            return

    if context.user_data.get("awaiting_region", False):
        selected_district = context.user_data.get("selected_federal_district")
        regions = FEDERAL_DISTRICTS.get(selected_district, [])
        if user_input in regions:
            USER_PROFILES[user_id]["region"] = user_input
            save_user_profiles(USER_PROFILES)
            region_folder = f"/regions/{user_input}/"
            create_yandex_folder(region_folder)
            context.user_data.pop("awaiting_region", None)
            context.user_data.pop("selected_federal_district", None)
            context.user_data["awaiting_name"] = True
            await update.message.reply_text("Как я могу к Вам обращаться (кратко для удобства)?",
                                           reply_markup=ReplyKeyboardRemove())
            logger.info(f"Пользователь {user_id} зарегистрирован с регионом {user_input}.")
            return
        else:
            await update.message.reply_text("Пожалуйста, выберите из предложенных регионов.")
            return

    if context.user_data.get("awaiting_name", False):
        profile = USER_PROFILES[user_id]
        profile["name"] = user_input
        save_user_profiles(USER_PROFILES)
        context.user_data["awaiting_name"] = False
        await show_main_menu(update, context)
        reply_markup = context.user_data.get('default_reply_markup', ReplyKeyboardRemove())
        await update.message.reply_text(
            f"Рад знакомству, {user_input}! Задавай свои вопросы или просто напиши имя файла для скачивания (например, file.pdf).",
            reply_markup=reply_markup
        )
        logger.info(f"Имя пользователя {chat_id} сохранено: {user_input}")
        return

    if user_input.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
        await search_and_send_file(update, context, user_input)
        return

    if user_input == "Список всех файлов":
        await show_file_list(update, context)
        return

    if user_input == "Управление пользователями":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут управлять пользователями.",
                                           reply_markup=default_reply_markup)
            logger.info(
                f"Пользователь {user_id} попытался использовать управление пользователями, но не является администратором.")
            return
        keyboard = [
            ['Добавить пользователя', 'Добавить администратора'],
            ['Список пользователей', 'Список администраторов'],
            ['Назад']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        logger.info(f"Администратор {user_id} запросил управление пользователями.")
        return

    if user_input == "Скачать файл":
        await update.message.reply_text(
            "Укажите название файла (например, file.pdf). Я поищу его в вашей региональной папке.",
            reply_markup=default_reply_markup)
        logger.info(f"Пользователь {user_id} запросил скачивание файла.")
        return

    if user_input == "Загрузить файл":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут загружать файлы.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался загрузить файл, но не является администратором.")
            return
        profile = USER_PROFILES.get(user_id)
        if not profile or "region" not in profile:
            await update.message.reply_text("Ошибка: у вас не определён регион. Обновите профиль с /start.")
            return
        await update.message.reply_text(
            "Отправьте файл, который нужно загрузить в папку",
            reply_markup=default_reply_markup
        )
        context.user_data['awaiting_upload'] = True
        logger.info(f"Администратор {user_id} начал процесс загрузки файла.")
        return

    if user_input == "Назад":
        await show_main_menu(update, context)
        return

    if context.user_data.get('awaiting_user_id'):
        try:
            new_id = int(user_input)
            if context.user_data['awaiting_user_id'] == 'add_user':
                if new_id in ALLOWED_USERS:
                    await update.message.reply_text(f"Пользователь с ID {new_id} уже имеет доступ.",
                                                   reply_markup=default_reply_markup)
                    return
                ALLOWED_USERS.append(new_id)
                save_allowed_users(ALLOWED_USERS)
                await update.message.reply_text(f"Пользователь с ID {new_id} успешно добавлен!",
                                               reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} добавил пользователя {new_id} в список разрешённых.")
            elif context.user_data['awaiting_user_id'] == 'add_admin':
                if new_id in ALLOWED_ADMINS:
                    await update.message.reply_text(f"Пользователь с ID {new_id} уже является администратором.",
                                                   reply_markup=default_reply_markup)
                    return
                ALLOWED_ADMINS.append(new_id)
                save_allowed_admins(ALLOWED_ADMINS)
                await update.message.reply_text(f"Пользователь с ID {new_id} успешно назначен администратором!",
                                               reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} назначил пользователя {new_id} администратором.")
            context.user_data.pop('awaiting_user_id', None)
            return
        except ValueError:
            await update.message.reply_text("Ошибка: user_id должен быть числом.", reply_markup=default_reply_markup)
            logger.error(f"Ошибка: Неверный формат user_id от {user_id}.")
            return

    if user_input == "Добавить пользователя":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут добавлять новых пользователей.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить пользователя, но не является администратором.")
            return
        await update.message.reply_text("Пожалуйста, укажите user_id для добавления.",
                                       reply_markup=default_reply_markup)
        context.user_data['awaiting_user_id'] = 'add_user'
        logger.info(f"Администратор {user_id} запросил добавление пользователя.")
        return

    if user_input == "Добавить администратора":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут назначать новых администраторов.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить администратора, но не является администратором.")
            return
        await update.message.reply_text("Пожалуйста, укажите user_id для назначения администратором.",
                                       reply_markup=default_reply_markup)
        context.user_data['awaiting_user_id'] = 'add_admin'
        logger.info(f"Администратор {user_id} запросил добавление администратора.")
        return

    if user_input == "Список пользователей":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Извините, только администраторы могут просматривать список пользователей.",
                                           reply_markup=default_reply_markup)
            logger.info(
                f"Пользователь {user_id} попытался просмотреть список пользователей, но не является администратором.")
            return
        if not ALLOWED_USERS:
            await update.message.reply_text("Список разрешённых пользователей пуст.", reply_markup=default_reply_markup)
            return
        users_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_USERS])
        await update.message.reply_text(f"Разрешённые пользователи:\n{users_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список разрешённых пользователей.")
        return

    if user_input == "Список администраторов":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text(
                "Извините, только администраторы могут просматривать список администраторов.",
                reply_markup=default_reply_markup)
            logger.info(
                f"Пользователь {user_id} попытался просмотреть список администраторов, но не является администратором.")
            return
        if not ALLOWED_ADMINS:
            await update.message.reply_text("Список администраторов пуст.", reply_markup=default_reply_markup)
            return
        admins_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_ADMINS])
        await update.message.reply_text(f"Администраторы:\n{admins_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список администраторов.")
        return

    qa_match = find_qa_match(user_input, qa_database)
    if qa_match:
        user_name = USER_PROFILES.get(user_id, {}).get("name", "Друг")
        final_response = f"{user_name}, {qa_match}"
        await update.message.reply_text(final_response, reply_markup=default_reply_markup)
        logger.info(f"Ответ из QA-базы для запроса: {user_input}")
        return

    if chat_id not in histories:
        histories[chat_id] = {"name": None, "messages": [{"role": "system", "content": system_prompt}]}

    histories[chat_id]["messages"].append({"role": "user", "content": user_input})
    if len(histories[chat_id]["messages"]) > 20:
        histories[chat_id]["messages"] = histories[chat_id]["messages"][:1] + histories[chat_id]["messages"][-19:]

    need_search = any(word in user_input.lower() for word in
                      ["актуальная информация", "последние новости", "найди в интернете", "поиск"])
    if need_search:
        logger.info(f"Выполняется поиск для запроса: {user_input}")
        search_results = web_search(user_input)
        histories[chat_id]["messages"].append({"role": "assistant", "content": f"Результаты поиска: {search_results}"})

    messages = histories[chat_id]["messages"]

    try:
        client = InferenceClient(model="mistralai/Mixtral-8x7B-Instruct-v0.1", token=HF_TOKEN)
        response = client.chat.completions.create(
            messages=messages,
            max_tokens=150,
            temperature=0.5,
            top_p=0.8
        )
        response_text = response.choices[0].message.content.strip()
        logger.info(f"Ответ модели: {response_text}")
    except Exception as e:
        logger.error(f"Ошибка при вызове модели: {str(e)}")
        response_text = f"Извините, произошла ошибка: {str(e)}"

    user_name = USER_PROFILES.get(user_id, {}).get("name", "Друг")
    final_response = f"{user_name}, {response_text}"
    histories[chat_id]["messages"].append({"role": "assistant", "content": response_text})
    await update.message.reply_text(final_response, reply_markup=default_reply_markup)


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
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        app.add_error_handler(error_handler)
        app.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")


if __name__ == "__main__":
    main()