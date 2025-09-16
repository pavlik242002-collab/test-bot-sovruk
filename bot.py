from __future__ import annotations

import os
import json
import logging
import openai
import requests
from typing import Dict, List, Any
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram import InputFile
from urllib.parse import quote
from openai import OpenAI

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
XAI_TOKEN = os.getenv("XAI_TOKEN")

# Проверка токенов
if not all([TELEGRAM_TOKEN, YANDEX_TOKEN, XAI_TOKEN]):
    logger.error("Токены не найдены в .env файле!")
    raise ValueError("Укажите TELEGRAM_TOKEN, YANDEX_TOKEN, XAI_TOKEN в .env")

# Инициализация клиента OpenAI
client = OpenAI(
    base_url="https://api.x.ai/v1",
    api_key=XAI_TOKEN,
)

# Словарь федеральных округов
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

# Функции для работы с администраторами
def load_allowed_admins() -> List[int]:
    """Загружает список ID администраторов из файла."""
    try:
        with open('allowed_admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл allowed_admins.json не найден, используется ID по умолчанию.")
        return [123456789]  # Замени на свой Telegram ID

def save_allowed_admins(allowed_admins: List[int]) -> None:
    """Сохраняет список ID администраторов в файл."""
    with open('allowed_admins.json', 'w') as f:
        json.dump(allowed_admins, f, ensure_ascii=False)

# Функции для работы с пользователями
def load_allowed_users() -> List[int]:
    """Загружает список ID разрешённых пользователей."""
    try:
        with open('allowed_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл allowed_users.json не найден.")
        return []

def save_allowed_users(allowed_users: List[int]) -> None:
    """Сохраняет список ID разрешённых пользователей."""
    with open('allowed_users.json', 'w') as f:
        json.dump(allowed_users, f, ensure_ascii=False)

# Функции для профилей пользователей
def load_user_profiles() -> Dict[int, Dict[str, str]]:
    """Загружает профили пользователей из файла."""
    try:
        with open('user_profiles.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Файл user_profiles.json не найден, возвращается пустой словарь.")
        return {}

def save_user_profiles(profiles: Dict[int, Dict[str, str]]) -> None:
    """Сохраняет профили пользователей в файл."""
    with open('user_profiles.json', 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

# Инициализация глобальных переменных
ALLOWED_ADMINS = load_allowed_admins()
ALLOWED_USERS = load_allowed_users()
USER_PROFILES = load_user_profiles()

# Системный промпт для ИИ
system_prompt = """
Вы — полезный чат-бот, который логически анализирует всю историю переписки, чтобы давать последовательные ответы.
Обязательно используй актуальные данные из поиска в истории сообщений для ответов на вопросы о фактах, организациях или событиях.
Если данные из поиска доступны, основывайся только на них и отвечай подробно, но кратко. Не говори "не знаю" или "уточните" — предоставь информацию на основе данных.
Если данных нет, используй свои знания, но укажи, что это общая информация.
Не упоминать процесс поиска или источники — отвечайте только фактами.
Всегда учитывайте полный контекст разговора перед ответом.
Отвечай кратко и по делу, на русском языке, без лишних объяснений.
"""

# Хранение истории переписки
histories: Dict[int, Dict[str, Any]] = {}

# Функции для работы с Яндекс.Диском
def create_yandex_folder(folder_path: str) -> bool:
    """Создаёт папку на Яндекс.Диске."""
    root_folder = '/regions'
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={quote(root_folder)}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}', 'Content-Type': 'application/json'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            response = requests.put(url, headers=headers)
            if response.status_code not in (201, 409):
                logger.error(f"Ошибка создания корневой папки {root_folder}: код {response.status_code}")
                return False
            logger.info(f"Корневая папка {root_folder} создана.")
        url = f'https://cloud-api.yandex.net/v1/disk/resources?path={quote(folder_path)}'
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            logger.info(f"Папка {folder_path} уже существует.")
            return True
        response = requests.put(url, headers=headers)
        if response.status_code in (201, 409):
            logger.info(f"Папка {folder_path} создана.")
            return True
        logger.error(f"Ошибка создания папки {folder_path}: код {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при создании папки {folder_path}: {str(e)}")
        return False

def list_yandex_disk_files(folder_path: str) -> List[Dict[str, str]]:
    """Возвращает список файлов в папке на Яндекс.Диске."""
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={quote(folder_path)}&fields=items.name,items.type,items.path&limit=100'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json().get('_embedded', {}).get('items', [])
            return [item for item in items if item['type'] == 'file' and item['name'].lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))]
        logger.error(f"Ошибка Яндекс.Диска: код {response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Ошибка при запросе списка файлов: {str(e)}")
        return []

def get_yandex_disk_file(file_path: str) -> str | None:
    """Получает ссылку для скачивания файла с Яндекс.Диска."""
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={quote(file_path)}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get('href')
        logger.error(f"Ошибка Яндекс.Диска: код {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе к Яндекс.Диску: {str(e)}")
        return None

def upload_to_yandex_disk(file_content: bytes, file_name: str, folder_path: str) -> bool:
    """Загружает файл на Яндекс.Диск."""
    file_path = folder_path + file_name
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={quote(file_path)}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            upload_url = response.json().get('href')
            if upload_url:
                upload_response = requests.put(upload_url, data=file_content)
                if upload_response.status_code in (201, 202):
                    logger.info(f"Файл {file_name} загружен в {folder_path}")
                    return True
                logger.error(f"Ошибка загрузки: код {upload_response.status_code}")
                return False
            logger.error("Не получен URL для загрузки")
            return False
        logger.error(f"Ошибка получения URL: код {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при загрузке: {str(e)}")
        return False

def delete_yandex_disk_file(file_path: str) -> bool:
    """Удаляет файл с Яндекс.Диска."""
    url = f'https://cloud-api.yandex.net/v1/disk/resources?path={quote(file_path)}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    try:
        response = requests.delete(url, headers=headers)
        if response.status_code in (204, 202):
            logger.info(f"Файл {file_path} удалён.")
            return True
        logger.error(f"Ошибка удаления файла {file_path}: код {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")
        return False

# Функция веб-поиска
def web_search(query: str) -> str:
    """Выполняет поиск в интернете и кэширует результаты."""
    cache_file = 'search_cache.json'
    try:
        with open(cache_file, 'r') as f:
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
        with open(cache_file, 'w') as f:
            json.dump(cache, f, ensure_ascii=False)
        logger.info(f"Поиск выполнен для запроса: {query}")
        return search_results
    except Exception as e:
        logger.error(f"Ошибка при поиске: {str(e)}")
        return json.dumps({"error": "Не удалось выполнить поиск."}, ensure_ascii=False)

# Обработчик команды /start
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start: регистрация или главное меню."""
    if update.effective_user is None or update.effective_chat is None:
        logger.error("Ошибка: update.effective_user или update.effective_chat is None")
        await update.message.reply_text("Ошибка: не удалось определить пользователя или чат.")
        return

    user_id: int = update.effective_user.id
    chat_id: int = update.effective_chat.id

    # Очистка временных данных
    context.user_data.pop('awaiting_user_id', None)
    context.user_data.pop('awaiting_fio', None)
    context.user_data.pop('awaiting_federal_district', None)
    context.user_data.pop('awaiting_region', None)
    context.user_data.pop('selected_federal_district', None)
    context.user_data.pop('awaiting_delete', None)

    # Проверка доступа
    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        welcome_message = f"Ваш user_id: {user_id}\nИзвините, у вас нет доступа. Передайте user_id администратору."
        await update.message.reply_text(welcome_message, reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался получить доступ.")
        return

    # Проверка профиля
    if user_id not in USER_PROFILES:
        context.user_data["awaiting_fio"] = True
        welcome_message = "Доброго времени суток!\nДля начала работы напишите своё ФИО."
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

# Отображение главного меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню с командами."""
    user_id: int = update.effective_user.id
    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ] if user_id in ALLOWED_ADMINS else [
        ['Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ]
    reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)
    context.user_data['default_reply_markup'] = reply_markup
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# Обработчик команды /getfile
async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /getfile: скачивание файла."""
    if update.effective_user is None or update.effective_chat is None:
        logger.error("Ошибка: update.effective_user или update.effective_chat is None")
        await update.message.reply_text("Ошибка: не удалось определить пользователя или чат.")
        return

    user_id: int = update.effective_user.id
    chat_id: int = update.effective_chat.id

    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался скачать файл.")
        return

    if user_id not in USER_PROFILES:
        await update.message.reply_text("Сначала пройдите регистрацию с /start.")
        return

    if not context.args:
        await update.message.reply_text("Укажите название файла (например, file.pdf).")
        return

    file_name = ' '.join(context.args).strip()
    await search_and_send_file(update, context, file_name)

# Поиск и отправка файла
async def search_and_send_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_name: str) -> None:
    """Ищет и отправляет файл с Яндекс.Диска."""
    user_id: int = update.effective_user.id
    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: регион не определён. Перезапустите /start.")
        logger.error(f"Ошибка: регион не определён для пользователя {user_id}.")
        return

    region_folder = f"/regions/{profile['region']}/"
    if not file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
        await update.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
        logger.error(f"Неподдерживаемый формат файла {file_name} для пользователя {user_id}.")
        return

    files = list_yandex_disk_files(region_folder)
    matching_file = next((item for item in files if item['name'].lower() == file_name.lower()), None)

    if not matching_file:
        await update.message.reply_text(f"Файл '{file_name}' не найден в папке {region_folder}.")
        logger.info(f"Файл '{file_name}' не найден для пользователя {user_id}.")
        return

    file_path = matching_file['path']
    download_url = get_yandex_disk_file(file_path)
    if not download_url:
        await update.message.reply_text("Ошибка: не удалось получить ссылку для скачивания.")
        logger.error(f"Не удалось получить ссылку для файла {file_path}.")
        return

    try:
        file_response = requests.get(download_url)
        if file_response.status_code == 200:
            file_size = len(file_response.content) / (1024 * 1024)
            if file_size > 20:
                await update.message.reply_text("Файл слишком большой (>20 МБ).")
                logger.error(f"Файл {file_name} слишком большой: {file_size} МБ")
                return
            await update.message.reply_document(
                document=InputFile(file_response.content, filename=file_name)
            )
            logger.info(f"Файл {file_name} отправлен пользователю {user_id}.")
        else:
            await update.message.reply_text("Не удалось загрузить файл с Яндекс.Диска.")
            logger.error(f"Ошибка загрузки файла {file_path}: код {file_response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке файла: {str(e)}")
        logger.error(f"Ошибка при отправке файла {file_path}: {str(e)}")

# Обработка загруженных документов
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка загруженных документов."""
    user_id: int = update.effective_user.id
    if not context.user_data.get('awaiting_upload', False):
        await update.message.reply_text("Используйте кнопку 'Загрузить файл' перед отправкой документа.")
        return

    document = update.message.document
    file_name = document.file_name
    if not file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
        await update.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
        return

    file_size = document.file_size / (1024 * 1024)
    if file_size > 50:
        await update.message.reply_text("Файл слишком большой (>50 МБ).")
        return

    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: регион не определён. Обновите профиль с /start.")
        return
    region_folder = f"/regions/{profile['region']}/"

    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        if upload_to_yandex_disk(file_content, file_name, region_folder):
            await update.message.reply_text(f"Файл успешно загружен в папку {region_folder}")
        else:
            await update.message.reply_text("Ошибка при загрузке файла на Яндекс.Диск.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке файла: {str(e)}")
        logger.error(f"Ошибка обработки документа от {user_id}: {str(e)}")

    context.user_data.pop('awaiting_upload', None)
    logger.info(f"Пользователь {user_id} загрузил файл {file_name} в {region_folder}.")

# Отображение списка файлов
async def show_file_list(update: Update, context: ContextTypes.DEFAULT_TYPE, for_deletion: bool = False) -> None:
    """Показывает список файлов в папке региона."""
    user_id: int = update.effective_user.id
    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await update.message.reply_text("Ошибка: регион не определён. Обновите профиль с /start.",
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

    keyboard = []
    for item in files:
        callback_data = f"{'delete' if for_deletion else 'download'}:{item['name']}"
        if len(callback_data.encode('utf-8')) > 64:
            logger.warning(f"callback_data для файла {item['name']} слишком длинное.")
            continue
        keyboard.append([InlineKeyboardButton(item['name'], callback_data=callback_data)])
    if not keyboard:
        await update.message.reply_text("Ошибка: имена файлов слишком длинные.",
                                       reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
        logger.error(f"callback_data для файлов в {region_folder} превышают лимит 64 байта.")
        return
    reply_markup = InlineKeyboardMarkup(keyboard)
    action_text = "Выберите файл для удаления:" if for_deletion else "Список всех файлов:"
    await update.message.reply_text(action_text, reply_markup=reply_markup)
    logger.info(f"Пользователь {user_id} запросил список файлов в {region_folder}.")

# Обработка callback-запросов
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка кнопок для скачивания/удаления файлов."""
    query = update.callback_query
    await query.answer()

    user_id: int = update.effective_user.id
    profile = USER_PROFILES.get(user_id)
    if not profile or "region" not in profile:
        await query.message.reply_text("Ошибка: регион не определён. Перезапустите /start.")
        logger.error(f"Ошибка: регион не определён для пользователя {user_id}.")
        return

    region_folder = f"/regions/{profile['region']}/"

    if query.data.startswith("download:"):
        file_name = query.data.split(":", 1)[1]
        if not file_name.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
            await query.message.reply_text("Поддерживаются только файлы .pdf, .doc, .docx, .xls, .xlsx.")
            logger.error(f"Неподдерживаемый формат файла {file_name} для пользователя {user_id}.")
            return

        files = list_yandex_disk_files(region_folder)
        matching_file = next((item for item in files if item['name'].lower() == file_name.lower()), None)

        if not matching_file:
            await query.message.reply_text(f"Файл '{file_name}' не найден в папке {region_folder}.")
            logger.info(f"Файл '{file_name}' не найден для пользователя {user_id}.")
            return

        file_path = matching_file['path']
        download_url = get_yandex_disk_file(file_path)
        if not download_url:
            await query.message.reply_text("Ошибка: не удалось получить ссылку для скачивания.")
            logger.error(f"Не удалось получить ссылку для файла {file_path}.")
            return

        try:
            file_response = requests.get(download_url)
            if file_response.status_code == 200:
                file_size = len(file_response.content) / (1024 * 1024)
                if file_size > 20:
                    await query.message.reply_text("Файл слишком большой (>20 МБ).")
                    logger.error(f"Файл {file_name} слишком большой: {file_size} МБ")
                    return
                await query.message.reply_document(
                    document=InputFile(file_response.content, filename=file_name)
                )
                logger.info(f"Файл {file_name} отправлен пользователю {user_id}.")
            else:
                await query.message.reply_text("Не удалось загрузить файл с Яндекс.Диска.")
                logger.error(f"Ошибка загрузки файла {file_path}: код {file_response.status_code}")
        except Exception as e:
            await query.message.reply_text(f"Ошибка при отправке файла: {str(e)}")
            logger.error(f"Ошибка при отправке файла {file_path}: {str(e)}")

    elif query.data.startswith("delete:"):
        if user_id not in ALLOWED_ADMINS:
            await query.message.reply_text("Только администраторы могут удалять файлы.",
                                          reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
            logger.info(f"Пользователь {user_id} попытался удалить файл.")
            return

        file_name = query.data.split(":", 1)[1]
        file_path = f"{region_folder}{file_name}"
        if delete_yandex_disk_file(file_path):
            await query.message.reply_text(f"Файл '{file_name}' удалён из папки {region_folder}.",
                                          reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
            logger.info(f"Администратор {user_id} удалил файл {file_name}.")
        else:
            await query.message.reply_text(f"Ошибка при удалении файла '{file_name}'.",
                                          reply_markup=context.user_data.get('default_reply_markup', ReplyKeyboardRemove()))
            logger.error(f"Ошибка при удалении файла {file_name} для пользователя {user_id}.")

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений: регистрация, команды, поиск."""
    if update.effective_user is None or update.effective_chat is None:
        logger.error("Ошибка: update.effective_user или update.effective_chat is None")
        await update.message.reply_text("Ошибка: не удалось определить пользователя или чат.")
        return

    user_id: int = update.effective_user.id
    chat_id: int = update.effective_chat.id
    user_input: str = update.message.text.strip()
    logger.info(f"Получено сообщение от {chat_id} (user_id: {user_id}): {user_input}")

    # Проверка доступа
    if user_id not in ALLOWED_USERS and user_id not in ALLOWED_ADMINS:
        await update.message.reply_text("Извините, у вас нет доступа.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Пользователь {user_id} попытался отправить сообщение.")
        return

    # Проверка профиля и регистрация
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

    # Определение клавиатуры
    admin_keyboard = [
        ['Управление пользователями', 'Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ] if user_id in ALLOWED_ADMINS else [
        ['Скачать файл', 'Загрузить файл', 'Список всех файлов']
    ]
    default_reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)

    # Обработка выбора федерального округа
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

    # Обработка выбора региона
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

    # Обработка ввода имени
    if context.user_data.get("awaiting_name", False):
        profile = USER_PROFILES[user_id]
        profile["name"] = user_input
        save_user_profiles(USER_PROFILES)
        context.user_data["awaiting_name"] = False
        await show_main_menu(update, context)
        reply_markup = context.user_data.get('default_reply_markup', ReplyKeyboardRemove())
        await update.message.reply_text(
            f"Рад знакомству, {user_input}! Задавайте вопросы или напишите имя файла (например, file.pdf).",
            reply_markup=reply_markup
        )
        logger.info(f"Имя пользователя {chat_id} сохранено: {user_input}")
        return

    # Обработка имени файла
    if user_input.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
        await search_and_send_file(update, context, user_input)
        return

    # Обработка команд меню
    if user_input == "Список всех файлов":
        await show_file_list(update, context)
        return

    if user_input == "Управление пользователями":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут управлять пользователями.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался использовать управление пользователями.")
            return
        keyboard = [
            ['Добавить пользователя', 'Добавить администратора'],
            ['Список пользователей', 'Список администраторов'],
            ['Удалить файл'],
            ['Назад']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        logger.info(f"Администратор {user_id} запросил управление пользователями.")
        return

    if user_input == "Скачать файл":
        await update.message.reply_text(
            "Укажите название файла (например, file.pdf).",
            reply_markup=default_reply_markup)
        logger.info(f"Пользователь {user_id} запросил скачивание файла.")
        return

    if user_input == "Загрузить файл":
        profile = USER_PROFILES.get(user_id)
        if not profile or "region" not in profile:
            await update.message.reply_text("Ошибка: регион не определён. Обновите профиль с /start.")
            return
        await update.message.reply_text(
            "Отправьте файл для загрузки.",
            reply_markup=default_reply_markup
        )
        context.user_data['awaiting_upload'] = True
        logger.info(f"Пользователь {user_id} начал загрузку файла.")
        return

    if user_input == "Удалить файл":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут удалять файлы.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался удалить файл.")
            return
        context.user_data['awaiting_delete'] = True
        await show_file_list(update, context, for_deletion=True)
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
                await update.message.reply_text(f"Пользователь с ID {new_id} добавлен!",
                                               reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} добавил пользователя {new_id}.")
            elif context.user_data['awaiting_user_id'] == 'add_admin':
                if new_id in ALLOWED_ADMINS:
                    await update.message.reply_text(f"Пользователь с ID {new_id} уже администратор.",
                                                   reply_markup=default_reply_markup)
                    return
                ALLOWED_ADMINS.append(new_id)
                save_allowed_admins(ALLOWED_ADMINS)
                await update.message.reply_text(f"Пользователь с ID {new_id} назначен администратором!",
                                               reply_markup=default_reply_markup)
                logger.info(f"Администратор {user_id} назначил администратора {new_id}.")
            context.user_data.pop('awaiting_user_id', None)
            return
        except ValueError:
            await update.message.reply_text("Ошибка: user_id должен быть числом.", reply_markup=default_reply_markup)
            logger.error(f"Ошибка: Неверный формат user_id от {user_id}.")
            return

    if user_input == "Добавить пользователя":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут добавлять пользователей.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить пользователя.")
            return
        await update.message.reply_text("Укажите user_id для добавления.",
                                       reply_markup=default_reply_markup)
        context.user_data['awaiting_user_id'] = 'add_user'
        logger.info(f"Администратор {user_id} запросил добавление пользователя.")
        return

    if user_input == "Добавить администратора":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут назначать администраторов.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался добавить администратора.")
            return
        await update.message.reply_text("Укажите user_id для назначения администратором.",
                                       reply_markup=default_reply_markup)
        context.user_data['awaiting_user_id'] = 'add_admin'
        logger.info(f"Администратор {user_id} запросил добавление администратора.")
        return

    if user_input == "Список пользователей":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут просматривать список пользователей.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался просмотреть список пользователей.")
            return
        if not ALLOWED_USERS:
            await update.message.reply_text("Список пользователей пуст.", reply_markup=default_reply_markup)
            return
        users_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_USERS])
        await update.message.reply_text(f"Разрешённые пользователи:\n{users_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список пользователей.")
        return

    if user_input == "Список администраторов":
        if user_id not in ALLOWED_ADMINS:
            await update.message.reply_text("Только администраторы могут просматривать список администраторов.",
                                           reply_markup=default_reply_markup)
            logger.info(f"Пользователь {user_id} попытался просмотреть список администраторов.")
            return
        if not ALLOWED_ADMINS:
            await update.message.reply_text("Список администраторов пуст.", reply_markup=default_reply_markup)
            return
        admins_list = "\n".join([f"ID: {uid}" for uid in ALLOWED_ADMINS])
        await update.message.reply_text(f"Администраторы:\n{admins_list}", reply_markup=default_reply_markup)
        logger.info(f"Администратор {user_id} запросил список администраторов.")
        return

    # Обработка текстового сообщения через API
    if chat_id not in histories:
        histories[chat_id] = {"name": None, "messages": [{"role": "system", "content": system_prompt}]}

    # Проверка необходимости веб-поиска
    need_search = any(word in user_input.lower() for word in [
        "актуальная информация", "последние новости", "найди в интернете", "поиск",
        "что такое", "информация о", "расскажи о", "найди", "поиск по", "детали о",
        "вскс", "спасатели", "корпус спасателей"
    ])

    if need_search:
        logger.info(f"Выполняется поиск для запроса: {user_input}")
        search_results_json = web_search(user_input)
        try:
            results = json.loads(search_results_json)
            if isinstance(results, list):
                extracted_text = "\n".join([f"Источник: {r.get('title', '')}\n{r.get('body', '')}" for r in results if r.get('body')])
            else:
                extracted_text = search_results_json
            histories[chat_id]["messages"].append({"role": "system", "content": f"Актуальные факты: {extracted_text}"})
            logger.info(f"Извлечено из поиска: {extracted_text[:200]}...")
        except json.JSONDecodeError:
            histories[chat_id]["messages"].append({"role": "system", "content": f"Ошибка поиска: {search_results_json}"})

    histories[chat_id]["messages"].append({"role": "user", "content": user_input})
    if len(histories[chat_id]["messages"]) > 20:
        histories[chat_id]["messages"] = histories[chat_id]["messages"][:1] + histories[chat_id]["messages"][-19:]

    messages = histories[chat_id]["messages"]

    # Запрос к API
    models_to_try = ["grok-3-mini", "grok-beta"]
    response_text = "Извините, не удалось получить ответ от API. Проверьте подписку на SuperGrok или X Premium+."

    for model in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                stream=False
            )
            response_text = completion.choices[0].message.content.strip()
            logger.info(f"Ответ модели {model}: {response_text}")
            break
        except openai.AuthenticationError as auth_err:
            logger.error(f"Ошибка авторизации для {model}: {str(auth_err)}")
            response_text = "Ошибка авторизации: неверный API-ключ. Проверьте XAI_TOKEN."
            break
        except openai.APIError as api_err:
            if "403" in str(api_err):
                logger.warning(f"403 Forbidden для {model}. Пробуем следующую модель.")
                continue
            logger.error(f"Ошибка API для {model}: {str(api_err)}")
            response_text = f"Ошибка API: {str(api_err)}"
            break
        except openai.RateLimitError as rate_err:
            logger.error(f"Превышен лимит для {model}: {str(rate_err)}")
            response_text = "Превышен лимит запросов. Попробуйте позже."
            break
        except Exception as e:
            logger.error(f"Неизвестная ошибка для {model}: {str(e)}")
            response_text = f"Неизвестная ошибка: {str(e)}"
            break
    else:
        logger.error("Все модели недоступны (403). Проверьте токен и подписку.")
        response_text = "Все модели недоступны (403). Обновите SuperGrok или X Premium+."

    user_name = USER_PROFILES.get(user_id, {}).get("name", "Друг")
    final_response = f"{user_name}, {response_text}"
    histories[chat_id]["messages"].append({"role": "assistant", "content": response_text})
    await update.message.reply_text(final_response, reply_markup=default_reply_markup)

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ошибок бота."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка, попробуйте позже.")

# Главная функция
def main() -> None:
    """Запуск бота."""
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