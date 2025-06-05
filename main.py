import json
import time
import telebot
import os
import requests
import urllib.parse
import re
from telebot import types
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from dotenv import load_dotenv
from datetime import datetime
from translations import translations
from bs4 import BeautifulSoup
import threading

# Путь до файла
REQUESTS_FILE = "requests.json"
ACCESS_FILE = "access.json"

# Глобальный словарь всех запросов пользователей
user_requests = {}

# Множество для отслеживания уже проверенных автомобилей
checked_ids = set()

# Словарь переводов цветов для KbChaChaCha
KBCHACHA_COLOR_TRANSLATIONS = {
    "검정색": {"ru": "Чёрный", "code": "006001"},
    "흰색": {"ru": "Белый", "code": "006002"},
    "은색": {"ru": "Серебристый", "code": "006003"},
    "진주색": {"ru": "Жемчужный", "code": "006004"},
    "회색": {"ru": "Серый", "code": "006005"},
    "빨간색": {"ru": "Красный", "code": "006006"},
    "파란색": {"ru": "Синий", "code": "006007"},
    "주황색": {"ru": "Оранжевый", "code": "006008"},
    "갈색": {"ru": "Коричневый", "code": "006009"},
    "초록색": {"ru": "Зелёный", "code": "006010jn"},
    "노란색": {"ru": "Жёлтый", "code": "006011"},
    "보라색": {"ru": "Фиолетовый", "code": "006012"},
    "Любой": {"ru": "Любой", "code": ""},
}

# Словарь переводов цветов для KCar
KCAR_COLOR_TRANSLATIONS = {
    "흰색": "Белый",
    "진주색": "Жемчужный",
    "검정색": "Чёрный",
    "검정투톤": "Чёрный (двухцветный)",
    "쥐색": "Тёмно-серый",
    "은색": "Серебристый",
    "은회색": "Серо-серебристый",
    "은색투톤": "Серебристый (двухцветный)",
    "흰색투톤": "Белый (двухцветный)",
    "진주투톤": "Жемчужный (двухцветный)",
    "은하색": "Галактический серый",
    "명은색": "Светло-серебристый",
    "빨간색": "Красный",
    "주황색": "Оранжевый",
    "자주색": "Бордовый",
    "보라색": "Фиолетовый",
    "분홍색": "Розовый",
    "노란색": "Жёлтый",
    "갈대색": "Коричневато-серый",
    "연금색": "Светло-золотистый",
    "갈색": "Коричневый",
    "갈색투톤": "Коричневый (двухцветный)",
    "금색": "Золотистый",
    "금색투톤": "Золотистый (двухцветный)",
    "청색": "Синий",
    "하늘색": "Голубой",
    "담녹색": "Тёмно-зелёный",
    "녹색": "Зелёный",
    "연두색": "Салатовый",
    "청옥색": "Бирюзовый",
    "기타": "Другой",
    "Любой": "Любой",
}


def load_access():
    if os.path.exists(ACCESS_FILE):
        try:
            with open(ACCESS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"⚠️ Не удалось загрузить access.json: {e}")
            return set()
    return set()


def save_access():
    try:
        with open(ACCESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ACCESS), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка при сохранении access.json: {e}")


MANAGER = 56022406

COLOR_TRANSLATIONS = {
    "검정색": "Чёрный",
    "쥐색": "Тёмно-серый",
    "은색": "Серебристый",
    "은회색": "Серо-серебристый",
    "흰색": "Белый",
    "은하색": "Галактический серый",
    "명은색": "Светло-серебристый",
    "갈대색": "Коричневато-серый",
    "연금색": "Светло-золотистый",
    "청색": "Синий",
    "하늘색": "Голубой",
    "담녹색": "Тёмно-зелёный",
    "청옥색": "Бирюзовый",
}

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# FSM-хранилище
state_storage = StateMemoryStorage()

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN, state_storage=state_storage)
user_search_data = {}

# Загружаем список пользователей с доступом сразу при старте
ACCESS = load_access()
print(f"📋 Загружен список доступа: {ACCESS}")


# Проверка на то может ли человек пользоваться ботом или нет
def is_authorized(user_id):
    global ACCESS

    # Добавляем список фиксированных ID пользователей, которые всегда имеют доступ
    always_allowed = [728438182, 6624693060, 6526086431]

    # Если пользователь в списке always_allowed, но его нет в ACCESS, добавляем
    if user_id in always_allowed and user_id not in ACCESS:
        ACCESS.add(user_id)
        save_access()
        print(f"✅ Пользователь {user_id} автоматически добавлен в список доступа")

    return user_id in ACCESS


def translate_phrase(phrase):
    words = phrase.split()
    translated_words = [translations.get(word, word) for word in words]
    return " ".join(translated_words)


# Кэш для отсортированных ключей словаря переводов
_sorted_translation_keys = None


def translate_smartly(text):
    """
    Интеллектуально переводит текст с использованием словаря translations.
    Сначала ищет более длинные совпадения, чтобы избежать частичных замен.

    Args:
        text: Исходный текст для перевода

    Returns:
        Переведенный текст или оригинал, если перевод не найден
    """
    global _sorted_translation_keys

    if not text or not isinstance(text, str):
        return text

    # Если текст точно совпадает с ключом в словаре, сразу возвращаем перевод
    if text in translations:
        return translations[text]

    # Инициализируем отсортированные ключи при первом вызове
    if _sorted_translation_keys is None:
        _sorted_translation_keys = sorted(translations.keys(), key=len, reverse=True)

    # Заменяем все вхождения ключей на соответствующие переводы
    result = text
    for key in _sorted_translation_keys:
        if key in result:
            result = result.replace(key, translations[key])

    return result


def load_requests():
    global user_requests
    if os.path.exists(REQUESTS_FILE):
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                user_requests = json.load(f)
        except Exception as e:
            print(f"⚠️ Не удалось загрузить запросы: {e}")
            user_requests = {}
    else:
        user_requests = {}


def save_requests(new_data):
    global user_requests
    try:
        if os.path.exists(REQUESTS_FILE):
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                existing_data = json.loads(content) if content else {}
        else:
            existing_data = {}

        for user_id, new_requests in new_data.items():
            # Убедимся, что user_id — строка
            user_id_str = str(user_id)
            existing_data[user_id_str] = new_requests

        user_requests = existing_data  # Обновляем глобальные данные

        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_requests, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения запросов: {e}")


# FSM: Состояния формы
class CarForm(StatesGroup):
    brand = State()
    model = State()
    generation = State()
    trim = State()
    color = State()
    mileage_from = State()
    mileage_to = State()


def get_manufacturers():
    url = "https://encar-proxy.habsida.net/api/nav?count=true&q=(And.Hidden.N._.SellType.%EC%9D%BC%EB%B0%98._.CarType.A.)&inav=%7CMetadata%7CSort"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        manufacturers = (
            data.get("iNav", {})
            .get("Nodes", [])[2]
            .get("Facets", [])[0]
            .get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        manufacturers.sort(key=lambda x: x.get("Metadata", {}).get("EngName", [""])[0])
        return manufacturers
    except Exception as e:
        print("Ошибка при получении марок:", e)
        return []


def get_models_by_brand(manufacturer):
    url = f"https://encar-proxy.habsida.net/api/nav?count=true&q=(And.Hidden.N._.SellType.%EC%9D%BC%EB%B0%98._.(C.CarType.A._.Manufacturer.{manufacturer}.))&inav=%7CMetadata%7CSort"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        all_manufacturers = (
            data.get("iNav", {})
            .get("Nodes", [])[2]
            .get("Facets", [])[0]
            .get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_manufacturer = next(
            (item for item in all_manufacturers if item.get("IsSelected")), None
        )
        if selected_manufacturer:
            return (
                selected_manufacturer.get("Refinements", {})
                .get("Nodes", [])[0]
                .get("Facets", [])
            )
        return []
    except Exception as e:
        print(f"Ошибка при получении моделей для {manufacturer}:", e)
        return []


def get_generations_by_model(manufacturer, model_group):
    url = f"https://encar-proxy.habsida.net/api/nav?count=true&q=(And.Hidden.N._.SellType.%EC%9D%BC%EB%B0%98._.(C.CarType.A._.(C.Manufacturer.{manufacturer}._.ModelGroup.{model_group}.)))&inav=%7CMetadata%7CSort"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        all_manufacturers = (
            data.get("iNav", {})
            .get("Nodes", [])[2]
            .get("Facets", [])[0]
            .get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_manufacturer = next(
            (item for item in all_manufacturers if item.get("IsSelected")), None
        )
        if not selected_manufacturer:
            return []
        model_group_data = (
            selected_manufacturer.get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_model = next(
            (item for item in model_group_data if item.get("IsSelected")), None
        )
        if not selected_model:
            return []
        return (
            selected_model.get("Refinements", {}).get("Nodes", [])[0].get("Facets", [])
        )
    except Exception as e:
        print(f"Ошибка при получении поколений для {manufacturer}, {model_group}:", e)
        return []


def get_trims_by_generation(manufacturer, model_group, model):
    url = f"https://encar-proxy.habsida.net/api/nav?count=true&q=(And.Hidden.N._.(C.CarType.A._.(C.Manufacturer.{manufacturer}._.(C.ModelGroup.{model_group}._.Model.{model}.))))&inav=%7CMetadata%7CSort"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        all_manufacturers = (
            data.get("iNav", {})
            .get("Nodes", [])[1]
            .get("Facets", [])[0]
            .get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_manufacturer = next(
            (item for item in all_manufacturers if item.get("IsSelected")), None
        )
        if not selected_manufacturer:
            return []
        model_group_data = (
            selected_manufacturer.get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_model_group = next(
            (item for item in model_group_data if item.get("IsSelected")), None
        )
        if not selected_model_group:
            return []
        model_data = (
            selected_model_group.get("Refinements", {})
            .get("Nodes", [])[0]
            .get("Facets", [])
        )
        selected_model = next(
            (item for item in model_data if item.get("IsSelected")), None
        )
        if not selected_model:
            return []
        return (
            selected_model.get("Refinements", {}).get("Nodes", [])[0].get("Facets", [])
        )
    except Exception as e:
        print(
            f"Ошибка при получении комплектаций для {manufacturer}, {model_group}, {model}:",
            e,
        )
        return []


@bot.message_handler(commands=["start"])
def start_handler(message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ У вас нет доступа к этому боту.")
        return

    # Главные кнопки
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🔍 Найти авто", callback_data="search_car"),
    )
    # markup.add(
    #     types.InlineKeyboardButton(
    #         "🧮 Рассчитать по ссылке", url="https://t.me/eightytwoautobot"
    #     ),
    # )
    markup.add(
        types.InlineKeyboardButton(
            "📋 Список моих запросов", callback_data="my_requests"
        )
    )
    markup.add(
        types.InlineKeyboardButton(
            "🧹 Удалить все запросы", callback_data="delete_all_requests"
        )
    )

    # Дополнительные кнопки
    markup.add(
        types.InlineKeyboardButton(
            "📱 TikTok", url="https://www.tiktok.com/@unitradingkr"
        ),
        types.InlineKeyboardButton(
            "📺 YouTube", url="https://youtube.com/@unitradingkr"
        ),
        types.InlineKeyboardButton(
            "📸 Instagram", url="https://www.instagram.com/uni.trading.kr"
        ),
    )

    welcome_text = (
        "👋 Добро пожаловать бот от *UniTrading*!\n\n"
        "С помощью этого бота вы можете:\n"
        "• 🔍 Найти интересующий вас автомобиль\n"
        "• 🧮 Получить расчёт стоимости авто по ссылке\n"
        "• 📬 Подписаться на соцсети и быть в курсе\n\n"
        "*Выберите действие ниже:*"
    )
    bot.send_message(
        message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup
    )


@bot.message_handler(commands=["add-user"])
def handle_add_user(message):
    if message.from_user.id != MANAGER:
        bot.reply_to(message, "❌ У вас нет прав для добавления пользователей.")
        return

    msg = bot.send_message(
        message.chat.id, "Введите ID пользователя для разрешения доступа к боту:"
    )
    bot.register_next_step_handler(msg, process_user_id_input)


def process_user_id_input(message):
    try:
        new_user_id = int(message.text.strip())
        ACCESS.add(new_user_id)
        save_access()
        bot.send_message(
            message.chat.id,
            f"✅ Пользователю с ID {new_user_id} разрешён доступ к боту.",
        )
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Введите корректный числовой ID.")


@bot.callback_query_handler(func=lambda call: call.data == "start")
def handle_start_callback(call):
    if not is_authorized(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ У вас нет доступа к этому боту.")
        return

    start_handler(call.message)


@bot.callback_query_handler(func=lambda call: call.data == "my_requests")
def handle_my_requests(call):
    if not is_authorized(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ У вас нет доступа к боту.")
        return

    user_id = str(call.from_user.id)
    requests_list = user_requests.get(user_id, [])
    load_requests()

    if not requests_list:
        bot.answer_callback_query(call.id, "У вас пока нет сохранённых запросов.")
        return

    for idx, req in enumerate(requests_list, 1):
        # Проверяем наличие необходимых ключей и используем значения по умолчанию
        year_from = req.get("year_from", "Н/Д")
        year_to = req.get("year_to", "Н/Д")
        mileage_from = req.get("mileage_from", "Н/Д")
        mileage_to = req.get("mileage_to", "Н/Д")
        color = req.get("color", "Н/Д")

        text = (
            f"📌 *Запрос #{idx}:*\n"
            f"{req.get('manufacturer', 'Н/Д')} / {req.get('model_group', 'Н/Д')} / {req.get('model', 'Н/Д')} / {req.get('trim', 'Н/Д')}\n"
            f"Год: {year_from}-{year_to}, Пробег: {mileage_from}–{mileage_to} км\n"
            f"Цвет: {color}"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                f"🗑 Удалить запрос #{idx}", callback_data=f"delete_request_{idx - 1}"
            )
        )
        bot.send_message(
            call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_request_"))
def handle_delete_request(call):
    user_id = str(call.from_user.id)
    index = int(call.data.split("_")[2])
    if user_id not in user_requests or index >= len(user_requests[user_id]):
        bot.answer_callback_query(call.id, "⚠️ Запрос не найден.")
        return

    removed = user_requests[user_id].pop(index)

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🏠 Вернуться в главное меню", callback_data="start")
    )
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✅ Запрос успешно удалён.",
        reply_markup=markup,
    )

    print(f"🗑 Удалён запрос пользователя {user_id}: {removed}")
    save_requests(user_requests)
    load_requests()


@bot.callback_query_handler(func=lambda call: call.data == "delete_all_requests")
def handle_delete_all_requests(call):
    user_id = str(call.from_user.id)
    if user_id in user_requests:
        user_requests[user_id] = []
        save_requests(user_requests)
        load_requests()
        bot.send_message(call.message.chat.id, "✅ Все ваши запросы успешно удалены.")
    else:
        bot.send_message(call.message.chat.id, "⚠️ У вас нет сохранённых запросов.")


@bot.callback_query_handler(func=lambda call: call.data == "search_car")
def handle_search_car(call):
    # Создаем клавиатуру с выбором площадок
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Encar", callback_data="platform_encar"),
        types.InlineKeyboardButton("KbChaChaCha", callback_data="platform_kbchachacha"),
        types.InlineKeyboardButton("KCar", callback_data="platform_kcar"),
    )

    bot.send_message(
        call.message.chat.id, "Выберите площадку для поиска:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("platform_"))
def handle_platform_selection(call):
    platform = call.data.split("_")[1]

    if platform == "encar":
        handle_encar_search(call)
    elif platform == "kbchachacha":
        handle_kbchachacha_search(call)
    elif platform == "kcar":
        handle_kcar_search(call)


def handle_encar_search(call):
    manufacturers = get_manufacturers()
    if not manufacturers:
        bot.answer_callback_query(call.id, "Не удалось загрузить марки.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in manufacturers:  # Удалено ограничение [:10]
        kr_name = item.get("DisplayValue", "Без названия")
        eng_name = item.get("Metadata", {}).get("EngName", [""])[0]
        callback_data = f"brand_{eng_name}_{kr_name}"
        display_text = f"{eng_name}"
        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    bot.send_message(
        call.message.chat.id, "Выбери марку автомобиля:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("brand_"))
def handle_brand_selection(call):
    _, eng_name, kr_name = call.data.split("_", 2)
    models = get_models_by_brand(kr_name)
    if not models:
        bot.answer_callback_query(call.id, "Не удалось загрузить модели.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in models:
        model_kr = item.get("DisplayValue", "Без названия")
        model_eng = item.get("Metadata", {}).get("EngName", [""])[0]
        callback_data = f"model_{model_eng}_{model_kr}"
        display_text = f"{model_eng}"
        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    bot.edit_message_text(
        f"Марка: {eng_name} ({kr_name})\nТеперь выбери модель:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("model_"))
def handle_model_selection(call):
    _, model_eng, model_kr = call.data.split("_", 2)
    message_text = call.message.text
    # Получаем марку из предыдущего текста сообщения
    brand_line = next(
        (line for line in message_text.split("\n") if "Марка:" in line), ""
    )
    brand_part = brand_line.replace("Марка:", "").strip()
    if " (" in brand_part:
        brand_eng, brand_kr = brand_part.split(" (")
        brand_kr = brand_kr.rstrip(")")
    else:
        brand_eng = brand_part
        brand_kr = ""

    generations = get_generations_by_model(brand_kr, model_kr)
    if not generations:
        bot.answer_callback_query(call.id, "Не удалось загрузить поколения.")
        return

    # Отладочный вывод данных о поколениях
    print(f"⚙️ DEBUG [handle_model_selection] - Полученные поколения:")
    for idx, item in enumerate(generations[:3]):  # Ограничимся первыми 3 для краткости
        gen_kr = item.get("DisplayValue", "Без названия")
        gen_eng = item.get("Metadata", {}).get("EngName", [""])[0]
        print(f"  Поколение {idx+1}: gen_kr='{gen_kr}', gen_eng='{gen_eng}'")

    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in generations:
        gen_kr = item.get("DisplayValue", "Без названия")
        gen_eng = item.get("Metadata", {}).get("EngName", [""])[0]

        start_raw = str(item.get("Metadata", {}).get("ModelStartDate", [""])[0])
        end_raw = str(item.get("Metadata", {}).get("ModelEndDate", [""])[0])

        def format_date(date_str):
            if len(date_str) == 6:
                return f"{date_str[4:6]}.{date_str[0:4]}"
            return ""

        start_date = format_date(start_raw)
        end_date = format_date(end_raw) if len(end_raw) > 0 else "н.в."

        period = f"({start_date} — {end_date})" if start_date else ""

        callback_data = f"generation_{gen_eng}_{gen_kr}"
        translated_gen_kr = translate_smartly(gen_kr)
        translated_gen_eng = translate_smartly(gen_eng)

        # Отладочная информация о переводе
        print(
            f"⚙️ DEBUG [handle_model_selection] - Перевод: '{gen_kr}' -> '{translated_gen_kr}'"
        )

        # Используем английское название с периодом, без корейского текста
        display_text = f"{gen_eng} {translated_gen_kr} {period}".strip()
        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    bot.edit_message_text(
        f"Марка: {brand_eng.strip()} ({brand_kr})\nМодель: {model_eng} ({model_kr})\nТеперь выбери поколение:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("generation_"))
def handle_generation_selection(call):
    _, generation_eng, generation_kr = call.data.split("_", 2)
    message_text = call.message.text

    # Выводим оригинальные данные для отладки
    print(
        f"🔍 DEBUG [handle_generation_selection] - generation_eng: '{generation_eng}'"
    )
    print(f"🔍 DEBUG [handle_generation_selection] - generation_kr: '{generation_kr}'")

    # Получаем информацию о марке и модели из сообщения
    brand_line = next(
        (line for line in message_text.split("\n") if "Марка:" in line), ""
    )
    model_line = next(
        (line for line in message_text.split("\n") if "Модель:" in line), ""
    )

    # Парсим информацию о марке
    brand_info = brand_line.replace("Марка:", "").strip()
    if " (" in brand_info and ")" in brand_info:
        brand_eng, brand_kr = brand_info.split(" (", 1)
        brand_kr = brand_kr.rstrip(")")
    else:
        brand_eng = brand_info
        brand_kr = ""

    # Парсим информацию о модели
    model_info = model_line.replace("Модель:", "").strip()
    if " (" in model_info and ")" in model_info:
        model_eng, model_kr = model_info.split(" (", 1)
        model_kr = model_kr.rstrip(")")
    else:
        model_eng = model_info
        model_kr = ""

    # Логгируем извлеченные данные
    print(
        f"🔍 DEBUG [handle_generation_selection] - brand_eng: '{brand_eng}', brand_kr: '{brand_kr}'"
    )
    print(
        f"🔍 DEBUG [handle_generation_selection] - model_eng: '{model_eng}', model_kr: '{model_kr}'"
    )

    # Получаем поколения для определения дат
    generations = get_generations_by_model(brand_kr, model_kr)
    if not generations:
        print(f"❌ DEBUG [handle_generation_selection] - Не удалось получить поколения")
        bot.answer_callback_query(call.id, "Не удалось определить поколение.")
        return

    # Ищем информацию о данном поколении среди полученных
    selected_generation = next(
        (
            g
            for g in generations
            if (g.get("DisplayValue") == generation_kr)
            or (generation_kr in g.get("DisplayValue", ""))
            or (generation_eng in g.get("Metadata", {}).get("EngName", [""])[0])
        ),
        None,
    )

    # Инициализируем переменные для хранения годов
    start_year, end_year = None, None
    current_year = datetime.now().year

    # Вывод информации о данных из API для отладки
    print(f"🔍 DEBUG [handle_generation_selection] - ENCAR API generation data:")
    if selected_generation:
        metadata = selected_generation.get("Metadata", {})
        for key, value in metadata.items():
            print(f"    {key}: {value}")

    # ПРИОРИТЕТ #1: Получение данных из API Encar
    if selected_generation:
        print(f"🔍 DEBUG [handle_generation_selection] - Найдено поколение в API")

        # Выводим все метаданные для отладки
        metadata = selected_generation.get("Metadata", {})
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        # Получаем даты из API
        start_raw = str(metadata.get("ModelStartDate", [""])[0])
        end_raw = str(metadata.get("ModelEndDate", [""])[0] or "")

        print(
            f"🔍 DEBUG [handle_generation_selection] - API даты: start_raw='{start_raw}', end_raw='{end_raw}'"
        )

        # Преобразуем даты в годы (формат API: YYYYMM)
        if start_raw and len(start_raw) >= 4 and start_raw[:4].isdigit():
            start_year = int(start_raw[:4])
            print(
                f"🔍 DEBUG [handle_generation_selection] - API start_year: {start_year}"
            )

        # Обработка конечной даты: нули или None означают "по настоящее время"
        if (
            end_raw
            and end_raw.lower() != "none"
            and end_raw != ""
            and len(end_raw) >= 4
            and end_raw[:4].isdigit()
        ):
            end_year = int(end_raw[:4])
            print(f"🔍 DEBUG [handle_generation_selection] - API end_year: {end_year}")
        else:
            # Если ModelEndDate нет или равен null, это значит "по настоящее время"
            end_year = current_year
            print(
                f"🔍 DEBUG [handle_generation_selection] - API end_year: текущий год ({current_year})"
            )

    # ПРИОРИТЕТ #2: Получение годов из названия поколения
    if start_year is None or end_year is None:
        print(
            f"🔍 DEBUG [handle_generation_selection] - Ищем годы в названии поколения: '{generation_eng}'"
        )
        date_pattern = r"\(?(\d{2}\.\d{4}|\d{4})\s*[—–\-~]\s*(\d{2}\.\d{4}|\d{4})\)?"
        match = re.search(date_pattern, generation_eng)

        if match:
            start_date_str, end_date_str = match.groups()
            print(
                f"🔍 DEBUG [handle_generation_selection] - Найдены даты: {start_date_str} - {end_date_str}"
            )

            # Извлекаем год из даты (может быть в формате MM.YYYY или YYYY)
            extracted_start_year = None
            extracted_end_year = None

            if "." in start_date_str:
                extracted_start_year = int(start_date_str.split(".")[-1])
            else:
                extracted_start_year = int(start_date_str)

            if "." in end_date_str:
                extracted_end_year = int(end_date_str.split(".")[-1])
            else:
                extracted_end_year = int(end_date_str)

            # Используем извлеченные годы только если не были найдены в API
            if start_year is None:
                start_year = extracted_start_year
                print(
                    f"🔍 DEBUG [handle_generation_selection] - Установлен start_year из названия: {start_year}"
                )

            if end_year is None:
                end_year = extracted_end_year
                print(
                    f"🔍 DEBUG [handle_generation_selection] - Установлен end_year из названия: {end_year}"
                )

    # ПРИОРИТЕТ #3: Проверяем DisplayValue на наличие годов
    if (start_year is None or end_year is None) and selected_generation:
        display_value = selected_generation.get("DisplayValue", "")
        print(
            f"🔍 DEBUG [handle_generation_selection] - DisplayValue: '{display_value}'"
        )

        # Ищем годы в формате (YYYY-YYYY)
        year_pattern = r"\(?(\d{4})\s*[-~]\s*(\d{4})\)?"
        match = re.search(year_pattern, display_value)

        if match:
            extracted_start_year = int(match.group(1))
            extracted_end_year = int(match.group(2))

            if start_year is None:
                start_year = extracted_start_year
                print(
                    f"🔍 DEBUG [handle_generation_selection] - Установлен start_year из DisplayValue: {start_year}"
                )

            if end_year is None:
                end_year = extracted_end_year
                print(
                    f"🔍 DEBUG [handle_generation_selection] - Установлен end_year из DisplayValue: {end_year}"
                )

    # ПРИОРИТЕТ #4: Проверяем специальные модели (как Hyundai Grandeur IG)
    if generation_eng.lower().find("ig") > -1 and (
        "grandeur" in generation_eng.lower() or "그랜저" in generation_kr
    ):
        print("🔍 DEBUG [handle_generation_selection] - Обнаружена модель Grandeur IG")
        # Для Hyundai Grandeur IG рекомендуемые годы 2016-2022
        if start_year is None or start_year > 2016:
            start_year = 2016
            print(
                f"🔍 DEBUG [handle_generation_selection] - Установлен start_year для Grandeur IG: {start_year}"
            )

        if end_year is None or end_year < 2022:
            end_year = 2022
            print(
                f"🔍 DEBUG [handle_generation_selection] - Установлен end_year для Grandeur IG: {end_year}"
            )

    # ПРИОРИТЕТ #5: Используем значения по умолчанию, если ничего не найдено
    if start_year is None:
        start_year = current_year - 7  # Типичный период выпуска
        print(
            f"🔍 DEBUG [handle_generation_selection] - Используем дефолтный start_year: {start_year}"
        )

    if end_year is None:
        end_year = current_year
        print(
            f"🔍 DEBUG [handle_generation_selection] - Используем дефолтный end_year: {end_year}"
        )

    # Проверяем корректность и актуальность диапазона годов
    # Если год начала в будущем, корректируем
    if start_year > current_year:
        print(
            f"⚠️ DEBUG [handle_generation_selection] - Некорректный год начала: {start_year} > {current_year}"
        )
        start_year = current_year - 5

    # Если год окончания меньше года начала
    if end_year < start_year:
        print(
            f"⚠️ DEBUG [handle_generation_selection] - Некорректный год окончания: {end_year} < {start_year}"
        )
        end_year = current_year

    # Если год окончания в далеком будущем (более 2 лет)
    if end_year > current_year + 2:
        print(
            f"⚠️ DEBUG [handle_generation_selection] - Год окончания слишком далеко: {end_year} > {current_year + 2}"
        )
        # В данном случае НЕ модифицируем end_year - т.к. это может быть корректным для новой модели
        # Например, Hyundai Grandeur GN7 выпускается с 2022 и будет до 2030

    print(
        f"✅ DEBUG [handle_generation_selection] - Итоговый диапазон годов: {start_year}-{end_year}"
    )

    # Получаем комплектации
    trims = get_trims_by_generation(brand_kr, model_kr, generation_kr)
    if not trims:
        bot.answer_callback_query(call.id, "Не удалось загрузить комплектации.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in trims:
        trim_kr = item.get("DisplayValue", "")
        trim_eng = item.get("Metadata", {}).get("EngName", [""])[0]
        callback_data = f"trim_{trim_eng}_{trim_kr}"

        # Используем translate_smartly для перевода названия комплектации
        translated_trim_kr = translate_smartly(trim_kr)
        display_text = translated_trim_kr

        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем данные о модели и годах
    user_search_data[user_id].update(
        {
            "manufacturer": brand_kr.strip(),
            "model_group": model_kr.strip(),
            "model": generation_kr.strip(),
            "year_from": start_year,
            "year_to": end_year,
        }
    )

    print(
        f"✅ DEBUG [handle_generation_selection] - Сохраненные годы в user_search_data: {start_year}-{end_year}"
    )

    # Используем translate_smartly для перевода названий поколений
    translated_generation_eng = translate_smartly(generation_eng)
    translated_generation_kr = translate_smartly(generation_kr)

    # Отображаем переведенные названия поколений в тексте сообщения
    bot.edit_message_text(
        f"Марка: {brand_eng.strip()} ({brand_kr})\nМодель: {model_eng} ({model_kr})\nПоколение: {translated_generation_eng} ({translated_generation_kr})\nВыберите комплектацию:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("trim_"))
def handle_trim_selection(call):
    parts = call.data.split("_", 2)
    trim_eng = parts[1]
    trim_kr = parts[2] if len(parts) > 2 else parts[1]

    print(f"✅ DEBUG [handle_trim_selection] - raw data:")
    print(f"trim_eng: {trim_eng}")
    print(f"trim_kr: {trim_kr}")

    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Используем фиксированный диапазон годов - от 2000 до текущего года
    current_year = datetime.now().year
    start_year = 2000
    end_year = current_year

    # Отладочная информация о годах
    print(
        f"✅ DEBUG [handle_trim_selection] - Используем фиксированный диапазон годов: {start_year}-{end_year}"
    )

    # Сохраняем trim и годы
    user_search_data[user_id]["trim"] = trim_kr.strip()
    user_search_data[user_id]["year_from"] = start_year
    user_search_data[user_id]["year_to"] = end_year

    print(
        f"✅ DEBUG [handle_trim_selection] - Обновленные данные после добавления trim:"
    )
    print(json.dumps(user_search_data[user_id], indent=2, ensure_ascii=False))

    year_markup = types.InlineKeyboardMarkup(row_width=4)

    # Формируем кнопки с годами для выбора - от 2000 до текущего
    # Отображаем каждый год без пропусков
    year_range = list(range(start_year, end_year + 1))

    print(
        f"✅ DEBUG [handle_trim_selection] - Формируем кнопки для годов: {year_range}"
    )

    # Формируем кнопки с годами для выбора
    for y in year_range:
        year_markup.add(
            types.InlineKeyboardButton(str(y), callback_data=f"year_from_{y}")
        )

    # Получаем информацию о выбранном автомобиле для отображения
    message_text = call.message.text
    brand_line = next(
        (line for line in message_text.split("\n") if "Марка:" in line), ""
    )
    model_line = next(
        (line for line in message_text.split("\n") if "Модель:" in line), ""
    )
    generation_line = next(
        (line for line in message_text.split("\n") if "Поколение:" in line), ""
    )

    # Парсим информацию из текста сообщения
    brand_info = brand_line.replace("Марка:", "").strip()
    if " (" in brand_info and ")" in brand_info:
        brand_eng, brand_kr = brand_info.split(" (", 1)
        brand_kr = brand_kr.rstrip(")")
    else:
        brand_eng = brand_info
        brand_kr = ""

    model_info = model_line.replace("Модель:", "").strip()
    if " (" in model_info and ")" in model_info:
        model_eng, model_kr = model_info.split(" (", 1)
        model_kr = model_kr.rstrip(")")
    else:
        model_eng = model_info
        model_kr = ""

    generation_info = generation_line.replace("Поколение:", "").strip()
    if "(" in generation_info and ")" in generation_info:
        parts = generation_info.rsplit("(", 1)
        generation_eng = parts[0].strip()
        generation_kr = parts[1].replace(")", "").strip()
    else:
        generation_eng = generation_info
        generation_kr = ""

    # Используем translate_smartly для перевода названий комплектаций
    translated_trim_eng = translate_smartly(trim_eng)
    translated_trim_kr = translate_smartly(trim_kr)

    # Формируем информационный текст о периоде выпуска
    year_period_text = f"Доступный период поиска: {start_year}-{end_year}"

    bot.edit_message_text(
        f"Марка: {brand_eng.strip()} ({brand_kr})\nМодель: {model_eng} ({model_kr})\nПоколение: {generation_eng} ({generation_kr})\nКомплектация: {translated_trim_eng} ({translated_trim_kr})\n{year_period_text}\n\nВыберите начальный год выпуска:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=year_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("year_from_"))
def handle_year_from_selection(call):
    year_from = int(call.data.split("_")[2])
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем год начала, сохраняя остальные данные
    user_search_data[user_id].update({"year_from": year_from})

    print(f"✅ DEBUG [handle_year_from_selection] - Выбран год начала: {year_from}")
    print(f"✅ DEBUG [handle_year_from_selection] - Данные user_search_data:")
    print(json.dumps(user_search_data[user_id], indent=2, ensure_ascii=False))

    # Показываем выбор месяца для начального года
    month_markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем опцию "Любой месяц"
    month_markup.add(
        types.InlineKeyboardButton(
            "Любой месяц", callback_data=f"month_from_{year_from}_0"
        )
    )

    # Добавляем все месяцы (1-12)
    for month in range(1, 13):
        month_name = [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        ][month - 1]
        month_markup.add(
            types.InlineKeyboardButton(
                f"{month_name}", callback_data=f"month_from_{year_from}_{month}"
            )
        )

    # Сообщение о выборе месяца
    bot.edit_message_text(
        f"Выбран начальный год: {year_from}\nВыберите начальный месяц:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=month_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("month_from_"))
def handle_month_from_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_")
    year_from = int(parts[2])
    month_from = int(parts[3])

    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем месяц начала
    user_search_data[user_id]["month_from"] = month_from

    # Используем фиксированный период - с выбранного года до текущего
    current_year = datetime.now().year
    end_year = current_year

    print(f"✅ DEBUG [handle_month_from_selection] - Выбран месяц начала: {month_from}")
    print(
        f"✅ DEBUG [handle_month_from_selection] - Используем фиксированный конечный год: {end_year}"
    )

    # Формируем диапазон лет от выбранного года до текущего года
    year_markup = types.InlineKeyboardMarkup(row_width=4)

    # Если выбранный год начала > текущего года, показываем только текущий год
    if year_from > current_year:
        print(
            f"⚠️ DEBUG [handle_month_from_selection] - Выбранный год начала ({year_from}) > текущего года ({current_year}), корректируем"
        )
        year_range = [current_year]
    else:
        # Отображаем каждый год от выбранного начального до текущего без пропусков
        year_range = list(range(year_from, current_year + 1))

    print(
        f"✅ DEBUG [handle_month_from_selection] - Предлагаемые годы для выбора to: {list(year_range)}"
    )

    for y in year_range:
        year_markup.add(
            types.InlineKeyboardButton(str(y), callback_data=f"year_to_{year_from}_{y}")
        )

    # Отображаем информацию о выбранном месяце в сообщении
    month_name = (
        "любой"
        if month_from == 0
        else [
            "январь",
            "февраль",
            "март",
            "апрель",
            "май",
            "июнь",
            "июль",
            "август",
            "сентябрь",
            "октябрь",
            "ноябрь",
            "декабрь",
        ][month_from - 1]
    )

    # Добавляем информацию о периоде поиска
    period_info = f"Доступный период поиска: 2000-{current_year}"

    bot.edit_message_text(
        f"Начальная дата: {year_from} год, {month_name}\n{period_info}\nТеперь выберите конечный год:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=year_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("year_to_"))
def handle_year_to_selection(call):
    year_from = int(call.data.split("_")[2])
    year_to = int(call.data.split("_")[3])
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Проверяем корректность выбранного года
    current_year = datetime.now().year
    if year_to > current_year:
        year_to = current_year
        print(
            f"⚠️ DEBUG [handle_year_to_selection] - Скорректирован год окончания на текущий: {year_to}"
        )

    # Сохраняем год окончания
    user_search_data[user_id]["year_to"] = year_to

    print(f"✅ DEBUG [handle_year_to_selection] - Выбран конечный год: {year_to}")
    print(f"✅ DEBUG [handle_year_to_selection] - Данные user_search_data:")
    print(json.dumps(user_search_data[user_id], indent=2, ensure_ascii=False))

    # Показываем выбор месяца для конечного года
    month_markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем опцию "Любой месяц"
    month_markup.add(
        types.InlineKeyboardButton(
            "Любой месяц", callback_data=f"month_to_{year_from}_{year_to}_0"
        )
    )

    # Добавляем все месяцы (1-12)
    for month in range(1, 13):
        month_name = [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        ][month - 1]
        month_markup.add(
            types.InlineKeyboardButton(
                f"{month_name}", callback_data=f"month_to_{year_from}_{year_to}_{month}"
            )
        )

    # Добавляем информацию о периоде поиска
    period_info = f"Доступный период поиска: 2000-{current_year}"

    bot.edit_message_text(
        f"Начальный год: {year_from}\nКонечный год: {year_to}\n{period_info}\nВыберите конечный месяц:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=month_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("month_to_"))
def handle_month_to_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_")
    year_from = int(parts[2])
    year_to = int(parts[3])
    month_to = int(parts[4])

    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем месяц окончания
    user_search_data[user_id]["month_to"] = month_to

    # Получаем данные о начальном месяце
    month_from = user_search_data[user_id].get("month_from", 0)

    # Проверяем корректность конечного года
    current_year = datetime.now().year
    if year_to > current_year:
        year_to = current_year
        user_search_data[user_id]["year_to"] = year_to
        print(
            f"⚠️ DEBUG [handle_month_to_selection] - Скорректирован год окончания на текущий: {year_to}"
        )

    # Преобразуем названия месяцев для отображения
    month_from_name = (
        "любой"
        if month_from == 0
        else [
            "январь",
            "февраль",
            "март",
            "апрель",
            "май",
            "июнь",
            "июль",
            "август",
            "сентябрь",
            "октябрь",
            "ноябрь",
            "декабрь",
        ][month_from - 1]
    )

    month_to_name = (
        "любой"
        if month_to == 0
        else [
            "январь",
            "февраль",
            "март",
            "апрель",
            "май",
            "июнь",
            "июль",
            "август",
            "сентябрь",
            "октябрь",
            "ноябрь",
            "декабрь",
        ][month_to - 1]
    )

    # Показываем выбор пробега
    mileage_markup = types.InlineKeyboardMarkup(row_width=4)
    for value in range(0, 200001, 10000):
        mileage_markup.add(
            types.InlineKeyboardButton(
                f"{value} км", callback_data=f"mileage_from_{value}"
            )
        )

    # Отображаем полный выбранный диапазон дат
    date_range_text = (
        f"с {year_from} года ({month_from_name}) по {year_to} год ({month_to_name})"
    )

    # Добавляем информацию о полном доступном периоде поиска
    period_info = f"Доступный период поиска: 2000-{current_year}"

    bot.edit_message_text(
        f"Выбран диапазон дат: {date_range_text}\n{period_info}\nТеперь выберите минимальный пробег:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=mileage_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("mileage_from_"))
def handle_mileage_from(call):
    mileage_from = int(call.data.split("_")[2])

    # Сохраняем выбранный минимальный пробег в данных пользователя
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем минимальный пробег
    user_search_data[user_id]["mileage_from"] = mileage_from

    print(f"✅ DEBUG user_search_data before mileage_from selection:")
    print(
        json.dumps(
            user_search_data.get(call.from_user.id, {}), indent=2, ensure_ascii=False
        )
    )

    mileage_markup = types.InlineKeyboardMarkup(row_width=4)
    for value in range(mileage_from + 10000, 200001, 10000):
        mileage_markup.add(
            types.InlineKeyboardButton(
                f"{value} км", callback_data=f"mileage_to_{mileage_from}_{value}"
            )
        )

    bot.send_message(
        call.message.chat.id,
        f"Минимальный пробег: {mileage_from} км\nТеперь выберите максимальный пробег:",
        reply_markup=mileage_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("mileage_to_"))
def handle_mileage_to(call):
    mileage_from = int(call.data.split("_")[2])
    mileage_to = int(call.data.split("_")[3])

    # Сохраняем выбранный максимальный пробег в данных пользователя
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Сохраняем максимальный пробег
    user_search_data[user_id]["mileage_to"] = mileage_to

    print(f"✅ DEBUG user_search_data before mileage_to selection:")
    print(
        json.dumps(
            user_search_data.get(call.from_user.id, {}), indent=2, ensure_ascii=False
        )
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    # Добавляем кнопку "Любой цвет"
    markup.add(types.InlineKeyboardButton("Любой", callback_data="color_all"))

    # Добавляем остальные цвета
    for kr, ru in COLOR_TRANSLATIONS.items():
        markup.add(types.InlineKeyboardButton(ru, callback_data=f"color_{kr}"))

    bot.send_message(
        call.message.chat.id,
        f"Пробег: от {mileage_from} км до {mileage_to} км\nТеперь выберите цвет автомобиля:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("color_"))
def handle_color_selection(call):
    selected_color_kr = call.data.split("_", 1)[1]
    message_text = call.message.text
    selected_color_ru = (
        "Любой"
        if selected_color_kr == "all"
        else COLOR_TRANSLATIONS.get(selected_color_kr, "Неизвестно")
    )

    user_id = call.from_user.id
    user_data = user_search_data.get(user_id, {})
    print(f"✅ DEBUG user_data before color selection: {user_data}")

    # Проверяем наличие всех необходимых данных
    required_fields = [
        "manufacturer",
        "model_group",
        "model",
        "trim",
        "year_from",
        "year_to",
    ]
    missing_fields = [field for field in required_fields if field not in user_data]

    if missing_fields:
        print(f"❌ Отсутствуют необходимые поля: {missing_fields}")
        bot.send_message(
            call.message.chat.id,
            "⚠️ Произошла ошибка: не все данные были сохранены. Пожалуйста, начните поиск заново.",
        )
        return

    # Сохраняем выбранный цвет
    user_search_data[user_id]["color"] = selected_color_kr

    # Получаем необходимые данные
    manufacturer = user_data["manufacturer"]
    model_group = user_data["model_group"]
    model = user_data["model"]
    trim = user_data["trim"]
    year_from = user_data["year_from"]
    year_to = user_data["year_to"]

    # Проверяем наличие данных о пробеге в сохраненных данных
    if "mileage_from" not in user_data or "mileage_to" not in user_data:
        # Если данных нет, то пытаемся извлечь из сообщения как запасной вариант
        mileage_line = next(
            (line for line in message_text.split("\n") if "Пробег:" in line), ""
        )
        if mileage_line:
            try:
                mileage_from = int(mileage_line.split("от")[1].split("км")[0].strip())
                mileage_to = int(mileage_line.split("до")[1].split("км")[0].strip())
                # Сохраняем извлеченные значения
                user_search_data[user_id]["mileage_from"] = mileage_from
                user_search_data[user_id]["mileage_to"] = mileage_to
            except:
                print(
                    "⚠️ DEBUG [handle_color_selection] - Ошибка при извлечении пробега из текста"
                )
                # Устанавливаем значения по умолчанию
                mileage_from = 0
                mileage_to = 100000
                user_search_data[user_id]["mileage_from"] = mileage_from
                user_search_data[user_id]["mileage_to"] = mileage_to
        else:
            print(
                "⚠️ DEBUG [handle_color_selection] - Не найдена информация о пробеге, устанавливаем значения по умолчанию"
            )
            mileage_from = 0
            mileage_to = 100000
            user_search_data[user_id]["mileage_from"] = mileage_from
            user_search_data[user_id]["mileage_to"] = mileage_to
    else:
        # Используем сохраненные данные
        mileage_from = user_data["mileage_from"]
        mileage_to = user_data["mileage_to"]

    print("⚙️ Данные для поиска:")
    print(f"manufacturer: {manufacturer}")
    print(f"model_group: {model_group}")
    print(f"model: {model}")
    print(f"trim: {trim}")
    print(f"year_from: {year_from}")
    print(f"year_to: {year_to}")
    print(f"color: {selected_color_kr}")
    print(f"mileage_from: {mileage_from}")
    print(f"mileage_to: {mileage_to}")

    # Показываем выбор минимальной цены
    markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем кнопку "Любая" для минимальной цены
    markup.add(types.InlineKeyboardButton("Любая", callback_data="price_from_any"))

    # Добавляем кнопки с диапазоном цен от 1 до 100 млн вон
    price_ranges = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100]
    buttons = []
    for price in price_ranges:
        price_param = price * 100  # Конвертация в параметр API (1 млн = 100)
        buttons.append(
            types.InlineKeyboardButton(
                f"{price} млн", callback_data=f"price_from_{price_param}"
            )
        )

    # Добавляем кнопки группами по 3
    for i in range(0, len(buttons), 3):
        row = buttons[i : i + 3]
        markup.row(*row)

    bot.edit_message_text(
        f"Марка: {manufacturer} ({model_group})\n"
        f"Модель: {model} ({trim})\n"
        f"Год выпуска: {year_from}-{year_to}\n"
        f"Пробег: от {mileage_from} до {mileage_to} км\n"
        f"Цвет: {selected_color_ru}\n\n"
        f"Выберите минимальную цену:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.message_handler(state=CarForm.brand)
def handle_brand(message):
    bot.send_message(message.chat.id, "Отлично! Теперь введи модель:")
    bot.set_state(message.from_user.id, CarForm.model, message.chat.id)


# Обработчик модели
@bot.message_handler(state=CarForm.model)
def handle_model(message):
    bot.send_message(message.chat.id, "Укажи поколение:")
    bot.set_state(message.from_user.id, CarForm.generation, message.chat.id)


def build_encar_url(
    manufacturer,
    model_group,
    model,
    trim,
    year_from,
    year_to,
    mileage_from,
    mileage_to,
    color,
    user_id=None,  # Добавляем user_id как параметр
    price_from=None,  # Добавляем параметр минимальной цены
    price_to=None,  # Добавляем параметр максимальной цены
):
    if not all(
        [manufacturer.strip(), model_group.strip(), model.strip(), trim.strip()]
    ):
        print("❌ Не переданы необходимые параметры для построения URL")
        return ""

    # Всегда выводим диагностическую информацию для отладки
    print(f"🔧 DEBUG [build_encar_url] - Исходные годы: from={year_from}, to={year_to}")
    print(f"🔧 DEBUG [build_encar_url] - Используем user_id: {user_id}")
    print(f"🔧 DEBUG [build_encar_url] - Цена: от={price_from}, до={price_to}")

    # Объявляем переменные сразу для дальнейшего логирования
    month_from = 0
    month_to = 0

    # Пытаемся получить месяцы из данных пользователя
    if user_id is not None and user_id in user_search_data:
        month_from = user_search_data[user_id].get("month_from", 0)
        month_to = user_search_data[user_id].get("month_to", 0)

        print(
            f"🔧 DEBUG [build_encar_url] - Месяцы из данных пользователя: from={month_from}, to={month_to}"
        )
    else:
        print("🔧 DEBUG [build_encar_url] - Не удалось получить данные пользователя")

    # ВСЕГДА форматируем с месяцами (даже если user_id не найден)
    # Эта секция кода будет выполняться независимо от наличия user_id
    if month_from == 0:  # Any month selected for start
        year_from_formatted = f"{year_from}00"
    else:
        # Используем двузначное представление месяца
        year_from_formatted = f"{year_from}{month_from:02d}"

    if month_to == 0:  # Any month selected for end
        year_to_formatted = f"{year_to}12"
    else:
        # Используем двузначное представление месяца
        year_to_formatted = f"{year_to}{month_to:02d}"

    # Проверяем финальный результат
    print(
        f"🔧 DEBUG [build_encar_url] - Отформатированные даты: от {year_from_formatted} до {year_to_formatted}"
    )

    # Подготавливаем имя модели в соответствии с рабочим примером
    # Используем + для пробелов, но НЕ добавляем + перед скобкой
    if "(" in model and ")" in model:
        base_name, code_part = model.rsplit("(", 1)
        code = code_part.rstrip(")")
        # Заменяем пробелы на +, но НЕ добавляем + перед скобкой
        base_name = base_name.strip()
        model_formatted = f"{base_name.replace(' ', '+')}({code}_)"
    else:
        model_formatted = model.replace(" ", "+")

    # Обрабатываем trim (BadgeGroup), используем + для пробелов
    trim_formatted = trim.replace(" ", "+")

    # Кодируем только корейские символы, оставляя + и другие ASCII символы
    def safe_quote(text):
        # Кодируем только не-ASCII символы
        result = ""
        for char in text:
            if ord(char) > 127:  # Не-ASCII символ (корейский)
                result += urllib.parse.quote(char)
            else:
                result += char
        return result

    manufacturer_encoded = safe_quote(manufacturer)
    model_group_encoded = safe_quote(model_group)
    model_formatted_encoded = safe_quote(model_formatted)
    trim_encoded = safe_quote(trim_formatted)

    # Строим URL в соответствии с РАБОЧЕЙ структурой:
    # (And.(And.Hidden.N._.(C.CarType.A._.(C.Manufacturer._.(C.ModelGroup._.(C.Model._.BadgeGroup.))))_.Year.range()._.Mileage.range())_.AdType.A.)

    # Внутренний And блок: СНАЧАЛА иерархия машины, БЕЗ SellType и Badge
    car_hierarchy = (
        f"Hidden.N._.(C.CarType.A._."
        f"(C.Manufacturer.{manufacturer_encoded}._."
        f"(C.ModelGroup.{model_group_encoded}._."
        f"(C.Model.{model_formatted_encoded}._.BadgeGroup.{trim_encoded}.))))"
    )

    # Фильтры по году и пробегу идут ПОСЛЕ иерархии
    filters = [
        f"_.Year.range({year_from_formatted}..{year_to_formatted})",
    ]

    # Пробег: если mileage_from = 0, то используем формат "..максимум" как в рабочем примере
    if mileage_from == 0 or mileage_from is None:
        filters.append(f"._.Mileage.range(..{mileage_to})")
    else:
        filters.append(f"._.Mileage.range({mileage_from}..{mileage_to})")

    # Добавляем фильтр по цене, если указан
    if price_from is not None and price_to is not None:
        filters.append(f"._.Price.range({price_from}..{price_to})")
    elif price_from is not None:
        filters.append(f"._.Price.range({price_from}..)")
    elif price_to is not None:
        filters.append(f"._.Price.range(..{price_to})")

    # Собираем внутренний And блок
    inner_and = f"(And.{car_hierarchy}{''.join(filters)}.)"

    # Добавляем цвет если есть (как отдельный фильтр снаружи)
    if color and color.strip():
        color_encoded = safe_quote(color)
        color_filter = f"_.Color.{color_encoded}"
    else:
        color_filter = ""

    # Финальная структура - ВОЗВРАЩАЕМ _.AdType.A. как в рабочем примере!
    query = f"(And.{inner_and}{color_filter}_.AdType.A.)"

    # Формируем окончательный URL
    url = (
        f"https://encar-proxy.habsida.net/api/catalog?count=true&q={query}"
        f"&sr=%7CModifiedDate%7C0%7C1"
    )

    print(f"📡 Сформирован URL: {url}")
    return url


def check_for_new_cars(
    user_id,  # Переименовываем параметр в user_id
    chat_id,  # Добавляем отдельный параметр chat_id для отправки сообщений
    manufacturer,
    model_group,
    model,
    trim,
    year_from,
    year_to,
    mileage_from,
    mileage_to,
    color,
    price_from=None,
    price_to=None,
):
    url = build_encar_url(
        manufacturer,
        model_group,
        model,
        trim,
        year_from,
        year_to,
        mileage_from,
        mileage_to,
        color,
        user_id=user_id,  # Используем user_id для получения параметров
        price_from=price_from,
        price_to=price_to,
    )

    while True:
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

            if response.status_code != 200:
                print(f"❌ API вернул статус {response.status_code}: {response.text}")
                time.sleep(300)
                continue

            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Ошибка парсинга JSON: {json_err}")
                print(f"Ответ: {response.text}")
                time.sleep(300)
                continue

            cars = data.get("SearchResults", [])
            new_cars = [car for car in cars if car["Id"] not in checked_ids]

            for car in new_cars:
                checked_ids.add(car["Id"])
                details_url = f"https://api.encar.com/v1/readside/vehicle/{car['Id']}"
                details_response = requests.get(
                    details_url, headers={"User-Agent": "Mozilla/5.0"}
                )

                if details_response.status_code == 200:
                    details_data = details_response.json()
                    specs = details_data.get("spec", {})
                    displacement = specs.get("displacement", "Не указано")

                    # Получаем и переводим дополнительные данные
                    fuel_type = translate_smartly(specs.get("fuelType", ""))
                    transmission = translate_smartly(specs.get("transmission", ""))
                    options = specs.get("options", [])
                    translated_options = (
                        [translate_smartly(opt) for opt in options[:5]]
                        if options
                        else []
                    )

                    options_text = ", ".join(translated_options)
                    options_display = (
                        f"\n🔧 Опции: {options_text}" if options_text else ""
                    )

                    extra_text = f"\n🏎️ Объём двигателя: {displacement}cc{options_display}\n\n👉 <a href='https://fem.encar.com/cars/detail/{car['Id']}'>Ссылка на автомобиль</a>"
                else:
                    extra_text = "\nℹ️ Не удалось получить подробности о машине."

                name = f'{car.get("Manufacturer", "")} {car.get("Model", "")} {car.get("Badge", "")}'
                # Переводим название автомобиля
                translated_name = translate_smartly(name)
                price = car.get("Price", 0)
                mileage = car.get("Mileage", 0)
                year = car.get("FormYear", "")

                def format_number(n):
                    return f"{int(n):,}".replace(",", " ")

                formatted_mileage = format_number(mileage)
                formatted_price = format_number(price * 10000)

                text = (
                    f"✅ Новое поступление по вашему запросу!\n\n<b>{translated_name}</b> {year} г.\nПробег: {formatted_mileage} км\nЦена: ₩{formatted_price}"
                    + extra_text
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        "➕ Добавить новый автомобиль в поиск",
                        callback_data="search_car",
                    )
                )
                markup.add(
                    types.InlineKeyboardButton(
                        "🏠 Вернуться в главное меню",
                        callback_data="start",
                    )
                )
                bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

            time.sleep(300)
        except Exception as e:
            print(f"🔧 Общая ошибка при проверке новых авто: {e}")
            time.sleep(300)


# Добавленный код для команд userlist и remove_user
@bot.message_handler(commands=["userlist"])
def handle_userlist_command(message):
    if message.from_user.id not in [728438182, 6624693060, 6526086431]:
        bot.reply_to(message, "❌ У вас нет доступа к этой команде.")
        return

    if not ACCESS:
        bot.reply_to(message, "❌ В списке доступа пока нет пользователей.")
        return

    access_list = list(ACCESS)
    text = "📋 Список пользователей с доступом к боту:\n\n"
    for user_id in access_list:
        text += f"• <code>{user_id}</code>\n"

    text += "\nЧтобы удалить пользователя, отправьте команду:\n/remove_user [ID]"

    bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.message_handler(commands=["remove_user"])
def handle_remove_user(message):
    if message.from_user.id not in [728438182, 6624693060, 6526086431]:
        bot.reply_to(message, "❌ У вас нет доступа к этой команде.")
        return

    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Используйте формат: /remove_user [ID]")
            return

        user_id_to_remove = int(parts[1])
        if user_id_to_remove in ACCESS:
            ACCESS.remove(user_id_to_remove)
            save_access()
            bot.reply_to(
                message, f"✅ Пользователь {user_id_to_remove} удалён из доступа."
            )
        else:
            bot.reply_to(message, "⚠️ Этот пользователь не найден в списке доступа.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {e}")


# Функции для работы с KbChaChaCha
def get_kbchachacha_manufacturers():
    """Получение списка производителей с KbChaChaCha"""
    url = (
        "https://www.kbchachacha.com/public/search/carMaker.json?page=1&sort=-orderDate"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        # Получаем список как импортных, так и корейских производителей
        import_manufacturers = data.get("result", {}).get(
            "수입", []
        )  # 수입 = импортные
        korean_manufacturers = data.get("result", {}).get(
            "국산", []
        )  # 국산 = корейские

        # Объединяем списки
        all_manufacturers = korean_manufacturers + import_manufacturers

        # Сортируем по имени производителя
        all_manufacturers.sort(key=lambda x: x.get("makerName", ""))

        return all_manufacturers
    except Exception as e:
        print("Ошибка при получении марок из KbChaChaCha:", e)
        return []


def get_kbchachacha_models(maker_code):
    """Получение списка моделей по ID производителя с KbChaChaCha"""
    url = f"https://www.kbchachacha.com/public/search/carClass.json?makerCode={maker_code}&page=1&sort=-orderDate"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        models = data.get("result", {}).get("code", [])
        # Сортируем по имени модели
        models.sort(key=lambda x: x.get("className", ""))
        return models
    except Exception as e:
        print(f"Ошибка при получении моделей с KbChaChaCha для {maker_code}:", e)
        return []


def get_kbchachacha_generations(maker_code, class_code):
    """Получение списка поколений по коду марки и модели с KbChaChaCha"""
    url = f"https://www.kbchachacha.com/public/search/carName.json?makerCode={maker_code}&page=1&sort=-orderDate&classCode={class_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        generations = data.get("result", {}).get("code", [])
        # Сортируем по порядку поколений
        generations.sort(key=lambda x: x.get("carOrder", 999))
        return generations
    except Exception as e:
        print(
            f"Ошибка при получении поколений с KbChaChaCha для {maker_code}/{class_code}:",
            e,
        )
        return []


def get_kbchachacha_trims(maker_code, class_code, car_code):
    """Получение списка конфигураций по коду марки, модели и поколения с KbChaChaCha"""
    url = f"https://www.kbchachacha.com/public/search/carModel.json?makerCode={maker_code}&page=1&sort=-orderDate&classCode={class_code}&carCode={car_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        trims = data.get("result", {}).get("codeModel", [])
        # Сортируем по порядку конфигураций
        trims.sort(key=lambda x: x.get("modelOrder", 999))
        return trims
    except Exception as e:
        print(
            f"Ошибка при получении конфигураций с KbChaChaCha для {maker_code}/{class_code}/{car_code}:",
            e,
        )
        return []


def handle_kbchachacha_search(call):
    # Получаем список производителей
    manufacturers = get_kbchachacha_manufacturers()
    if not manufacturers:
        bot.answer_callback_query(call.id, "Не удалось загрузить марки из KbChaChaCha.")
        return

    # Создаем клавиатуру с марками
    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in manufacturers:
        maker_name = item.get("makerName", "Без названия")
        maker_code = item.get("makerCode", "")

        # Добавляем перевод названия марки, если оно есть в словаре переводов
        translated_name = translate_smartly(maker_name)

        # Формируем текст для отображения
        display_name = translated_name
        if maker_name != translated_name and translated_name != maker_name:
            display_name = f"{translated_name} ({maker_name})"

        # Используем специальный префикс для отличия от других площадок
        callback_data = f"kbcha_brand_{maker_code}_{maker_name}"
        markup.add(
            types.InlineKeyboardButton(display_name, callback_data=callback_data)
        )

    bot.send_message(
        call.message.chat.id,
        "Выберите марку автомобиля:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_brand_"))
def handle_kbcha_brand_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    maker_code = parts[2]
    maker_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранную марку у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_maker_code"] = maker_code
    user_search_data[user_id]["kbcha_maker_name"] = maker_name

    # Получаем перевод названия марки с помощью функции translate_smartly
    translated_maker_name = translate_smartly(maker_name)

    # Получаем список моделей для выбранной марки
    models = get_kbchachacha_models(maker_code)
    if not models:
        bot.send_message(
            call.message.chat.id,
            f"Не удалось загрузить модели для {translated_maker_name}",
        )
        return

    # Создаем клавиатуру с моделями
    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in models:
        class_name = item.get("className", "Без названия")
        class_code = item.get("classCode", "")

        # Добавляем перевод названия модели с использованием функции translate_smartly
        translated_name = translate_smartly(class_name)

        # Формируем текст для отображения
        display_name = translated_name
        if class_name != translated_name and translated_name != class_name:
            display_name = f"{translated_name} ({class_name})"

        callback_data = f"kbcha_model_{class_code}_{class_name}"
        markup.add(
            types.InlineKeyboardButton(display_name, callback_data=callback_data)
        )

    # Отображаем имя марки - либо переведенное, либо с переводом в скобках
    display_maker_name = translated_maker_name
    if maker_name != translated_maker_name and translated_maker_name != maker_name:
        display_maker_name = f"{translated_maker_name} ({maker_name})"

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nВыберите модель:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_model_"))
def handle_kbcha_model_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    class_code = parts[2]
    class_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранную модель у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_class_code"] = class_code
    user_search_data[user_id]["kbcha_class_name"] = class_name

    # Получаем перевод названия модели, если оно есть
    translated_class_name = translations.get(class_name, class_name)

    # Получаем информацию о марке
    maker_name = user_search_data[user_id].get("kbcha_maker_name", "")
    maker_code = user_search_data[user_id].get("kbcha_maker_code", "")
    translated_maker_name = translations.get(maker_name, maker_name)

    # Получаем список поколений для выбранной модели
    generations = get_kbchachacha_generations(maker_code, class_code)
    if not generations:
        bot.send_message(
            call.message.chat.id, f"Не удалось загрузить поколения для {class_name}"
        )
        return

    # Создаем клавиатуру с поколениями
    markup = types.InlineKeyboardMarkup(row_width=1)
    for item in generations:
        car_name = item.get("carName", "Без названия")
        car_code = item.get("carCode", "")
        from_year = item.get("fromYear", "")
        to_year = item.get("toYear", "")

        # Форматируем период производства
        year_period = f"({from_year}-{to_year})" if from_year and to_year else ""
        if to_year == "현재":  # 현재 = "настоящее время" по-корейски
            year_period = f"({from_year}-н.в.)"

        # Используем translate_smartly для перевода названия поколения, которая разбивает текст на слова
        # и переводит каждое слово отдельно, что позволяет корректно переводить такие фразы как "가솔린 1.0 터보"
        translated_name = translate_smartly(car_name)

        # Используем формат: "Оригинальное название (Перевод) Период" или "Оригинальное название Период"
        if car_name != translated_name:
            display_text = f"{car_name} ({translated_name}) {year_period}"
        else:
            display_text = f"{car_name} {year_period}"

        callback_data = f"kbcha_gen_{car_code}_{car_name}"
        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    # Форматируем отображаемые названия марки и модели с переводами, если они доступны
    display_maker_name = (
        f"{maker_name} ({translated_maker_name})"
        if maker_name != translated_maker_name
        else maker_name
    )
    display_class_name = (
        f"{class_name} ({translated_class_name})"
        if class_name != translated_class_name
        else class_name
    )

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_class_name}\nВыберите поколение:",
        reply_markup=markup,
    )


def search_kbchachacha_cars(
    maker_code,
    class_code,
    car_code,
    model_code,
    year_from=None,
    year_to=None,
    mileage_from=None,
    mileage_to=None,
    color_code=None,
):
    """
    Поиск автомобилей на KbChaChaCha
    """
    # Базовый URL для поиска
    url = f"https://www.kbchachacha.com/public/search/list.empty?makerCode={maker_code}&page=1&sort=-orderDate&classCode={class_code}&carCode={car_code}&modelCode={model_code}"

    # Добавляем дополнительные параметры, если они указаны
    if year_from and year_to:
        url += f"&regiDay={year_from},{year_to}"

    if mileage_from is not None and mileage_to is not None:
        url += f"&km={mileage_from},{mileage_to}"

    if color_code:
        url += f"&color={color_code}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        print(f"DEBUG: Отправка запроса на URL: {url}")
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        # Ищем все блоки с автомобилями
        car_areas = soup.select("div.list-in.type-wd-list div.area")

        results = []
        for area in car_areas[:5]:  # Ограничиваем до 5 результатов
            try:
                # Извлекаем данные об автомобиле
                car_seq = area.get("data-car-seq", "")
                car_link = f"https://www.kbchachacha.com/public/car/detail.kbc?carSeq={car_seq}"

                # Извлекаем название автомобиля
                car_title = area.select_one("div.con div.item strong.tit")
                title = car_title.text.strip() if car_title else "Неизвестно"
                # Переводим название автомобиля
                translated_title = translate_smartly(title)

                # Извлекаем данные о годе, пробеге и регионе
                data_line = area.select_one("div.con div.item div.data-line")
                details = (
                    [span.text.strip() for span in data_line.select("span")]
                    if data_line
                    else []
                )
                year = details[0] if len(details) > 0 else "Неизвестно"
                mileage = details[1] if len(details) > 1 else "Неизвестно"
                region = details[2] if len(details) > 2 else "Неизвестно"
                # Переводим регион
                translated_region = translate_smartly(region)

                # Извлекаем цену
                price_elem = area.select_one(
                    "div.con div.item div.sort-wrap strong.pay span.price"
                )
                price = price_elem.text.strip() if price_elem else "Неизвестно"

                # Получаем ссылку на изображение
                img_elem = area.select_one("div.thumnail a.item span.item__img img")
                img_url = img_elem.get("src", "") if img_elem else ""

                results.append(
                    {
                        "title": translated_title,
                        "original_title": title,
                        "year": year,
                        "mileage": mileage,
                        "region": translated_region,
                        "original_region": region,
                        "price": price,
                        "link": car_link,
                        "img_url": img_url,
                    }
                )
            except Exception as e:
                print(f"Ошибка при парсинге автомобиля: {e}")
                continue

        return results
    except Exception as e:
        print(f"Ошибка при поиске автомобилей на KbChaChaCha: {e}")
        return []


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_gen_"))
def handle_kbcha_generation_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    car_code = parts[2]
    car_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранное поколение у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_car_code"] = car_code
    user_search_data[user_id]["kbcha_car_name"] = car_name

    # Получаем перевод названия поколения используя функцию translate_phrase
    # которая разбивает текст на слова и переводит каждое слово отдельно
    translated_car_name = translate_smartly(car_name)

    # Получаем информацию о марке и модели
    maker_name = user_search_data[user_id].get("kbcha_maker_name", "")
    maker_code = user_search_data[user_id].get("kbcha_maker_code", "")
    class_name = user_search_data[user_id].get("kbcha_class_name", "")
    class_code = user_search_data[user_id].get("kbcha_class_code", "")

    # Получаем переводы названий марки и модели, если они есть
    translated_maker_name = translations.get(maker_name, maker_name)
    translated_class_name = translations.get(class_name, class_name)

    # Получаем список конфигураций для выбранного поколения
    trims = get_kbchachacha_trims(maker_code, class_code, car_code)
    if not trims:
        bot.send_message(
            call.message.chat.id, f"Не удалось загрузить конфигурации для {car_name}"
        )
        return

    # Создаем клавиатуру с конфигурациями
    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in trims:
        model_name = item.get("modelName", "Без названия")
        model_code = item.get("modelCode", "")

        # Добавляем перевод названия конфигурации используя translate_phrase
        # которая разбивает текст на слова и переводит каждое слово отдельно
        translated_name = translate_smartly(model_name)

        # Используем формат: "Оригинальное название (Перевод)" или просто "Оригинальное название", если перевода нет
        display_name = (
            f"{model_name} ({translated_name})"
            if model_name != translated_name
            else model_name
        )

        callback_data = f"kbcha_trim_{model_code}_{model_name}"
        markup.add(
            types.InlineKeyboardButton(display_name, callback_data=callback_data)
        )

    # Форматируем отображаемые названия с переводами, если они доступны
    display_maker_name = (
        f"{maker_name} ({translated_maker_name})"
        if maker_name != translated_maker_name
        else maker_name
    )
    display_class_name = (
        f"{class_name} ({translated_class_name})"
        if class_name != translated_class_name
        else class_name
    )
    display_car_name = (
        f"{car_name} ({translated_car_name})"
        if car_name != translated_car_name
        else car_name
    )

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_class_name}\nПоколение: {display_car_name}\nВыберите конфигурацию:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_trim_"))
def handle_kbcha_trim_selection(call):
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    model_code = parts[2]
    model_name = parts[3] if len(parts) > 3 else "Неизвестно"

    print(f"✅ DEBUG kbcha_trim_selection - raw data:")
    print(f"model_code: {model_code}")
    print(f"model_name: {model_name}")

    # Сохраняем выбранную конфигурацию у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_model_code"] = model_code
    user_search_data[user_id]["kbcha_model_name"] = model_name

    # Получаем перевод названия конфигурации, используя translate_phrase
    translated_model_name = translate_smartly(model_name)

    # Получаем информацию о предыдущих выборах пользователя
    maker_name = user_search_data[user_id].get("kbcha_maker_name", "")
    maker_code = user_search_data[user_id].get("kbcha_maker_code", "")
    class_name = user_search_data[user_id].get("kbcha_class_name", "")
    class_code = user_search_data[user_id].get("kbcha_class_code", "")
    car_name = user_search_data[user_id].get("kbcha_car_name", "")
    car_code = user_search_data[user_id].get("kbcha_car_code", "")

    # Получаем переводы названий, если они есть
    translated_maker_name = translations.get(maker_name, maker_name)
    translated_class_name = translations.get(class_name, class_name)
    translated_car_name = translate_smartly(car_name)

    # Определяем начальный год для поколения
    # Отладочная информация о названии поколения и извлечении года
    print(f"⚙️ DEBUG kbcha_trim_selection - car_name: '{car_name}'")

    # По умолчанию используем значения
    start_year = datetime.now().year - 5  # По умолчанию 5 лет назад
    end_year = datetime.now().year  # По умолчанию текущий год

    # Пытаемся найти информацию о периоде выпуска поколения в его названии
    if "(" in car_name and ")" in car_name:
        period_part = car_name.split("(")[1].split(")")[0].strip()
        print(f"⚙️ DEBUG kbcha_trim_selection - period_part: '{period_part}'")

        # Проверяем разные форматы разделителей
        if "—" in period_part:
            parts = period_part.split("—")
        elif "-" in period_part:
            parts = period_part.split("-")
        else:
            parts = []

        print(f"⚙️ DEBUG kbcha_trim_selection - split parts: {parts}")

        if len(parts) == 2:
            start_date = parts[0].strip()
            end_date = parts[1].strip()
            print(
                f"⚙️ DEBUG kbcha_trim_selection - start_date: '{start_date}', end_date: '{end_date}'"
            )

            # Извлекаем год из начальной даты (формат может быть "03.2020" или "2020")
            if "." in start_date:
                start_year_str = start_date.split(".")[-1]
                print(
                    f"⚙️ DEBUG kbcha_trim_selection - parsed start_year_str: '{start_year_str}'"
                )
                if start_year_str.isdigit() and len(start_year_str) == 4:
                    start_year = int(start_year_str)
            elif start_date.isdigit() and len(start_date) == 4:
                start_year = int(start_date)

            # Извлекаем год из конечной даты
            if "." in end_date:
                end_year_str = end_date.split(".")[-1]
                print(
                    f"⚙️ DEBUG kbcha_trim_selection - parsed end_year_str: '{end_year_str}'"
                )
                if end_year_str.isdigit() and len(end_year_str) == 4:
                    end_year = int(end_year_str)
            elif end_date.isdigit() and len(end_date) == 4:
                end_year = int(end_date)

    print(
        f"⚙️ DEBUG kbcha_trim_selection - final start_year: {start_year}, end_year: {end_year}"
    )

    # Гарантируем, что start_year не больше текущего года
    current_year = datetime.now().year
    if start_year > current_year:
        start_year = current_year - 5

    # Если end_year < start_year (ошибочные данные), используем current_year
    if end_year < start_year:
        end_year = current_year

    # Сохраняем определенные годы для использования в дальнейшем
    user_search_data[user_id]["kbcha_generation_start_year"] = start_year
    user_search_data[user_id]["kbcha_generation_end_year"] = end_year

    # Формируем список годов для выбора
    markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем года от начала производства поколения до его конца или текущего года
    for year in range(start_year, min(end_year, current_year) + 1):
        markup.add(
            types.InlineKeyboardButton(
                f"{year}", callback_data=f"kbcha_year_from_{year}"
            )
        )

    # Форматируем отображаемые названия с переводами, если они доступны
    display_maker_name = (
        f"{maker_name} ({translated_maker_name})"
        if maker_name != translated_maker_name
        else maker_name
    )
    display_class_name = (
        f"{class_name} ({translated_class_name})"
        if class_name != translated_class_name
        else class_name
    )
    display_car_name = (
        f"{car_name} ({translated_car_name})"
        if car_name != translated_car_name
        else car_name
    )
    display_model_name = (
        f"{model_name} ({translated_model_name})"
        if model_name != translated_model_name
        else model_name
    )

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_class_name}\nПоколение: {display_car_name}\nКонфигурация: {display_model_name}\n\nВыберите начальный год выпуска:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_year_from_"))
def handle_kbcha_year_from_selection(call):
    # Парсим выбранный год
    year_from = call.data.split("_")[3]

    # Сохраняем выбранный год начала
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_year_from"] = year_from

    # Получаем год окончания производства поколения
    end_year = user_search_data[user_id].get(
        "kbcha_generation_end_year", datetime.now().year
    )
    current_year = datetime.now().year
    year_from_int = int(year_from)

    # Формируем диапазон годов от выбранного года до конца производства поколения или текущего года
    markup = types.InlineKeyboardMarkup(row_width=3)
    for year in range(year_from_int, min(end_year, current_year) + 1):
        markup.add(
            types.InlineKeyboardButton(f"{year}", callback_data=f"kbcha_year_to_{year}")
        )

    bot.send_message(
        call.message.chat.id,
        f"Выбран начальный год: {year_from}\nТеперь выберите конечный год выпуска:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_year_to_"))
def handle_kbcha_year_to_selection(call):
    # Парсим выбранный год
    year_to = call.data.split("_")[3]

    # Сохраняем выбранный год конца
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_year_to"] = year_to

    # Показываем выбор пробега от
    markup = types.InlineKeyboardMarkup(row_width=3)
    for mileage in [0, 10000, 20000, 30000, 50000, 70000, 100000]:
        markup.add(
            types.InlineKeyboardButton(
                f"{mileage} км", callback_data=f"kbcha_mileage_from_{mileage}"
            )
        )

    bot.send_message(
        call.message.chat.id,
        f"Выбран диапазон годов: {user_search_data[user_id]['kbcha_year_from']}-{year_to}\nТеперь выберите минимальный пробег:",
        reply_markup=markup,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("kbcha_mileage_from_")
)
def handle_kbcha_mileage_from_selection(call):
    # Парсим выбранный пробег
    mileage_from = call.data.split("_")[3]

    # Сохраняем выбранный минимальный пробег
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_mileage_from"] = mileage_from

    # Показываем выбор пробега до
    markup = types.InlineKeyboardMarkup(row_width=3)
    mileage_from_int = int(mileage_from)

    for mileage in [50000, 100000, 150000, 200000, 250000, 300000]:
        if mileage > mileage_from_int:
            markup.add(
                types.InlineKeyboardButton(
                    f"{mileage} км", callback_data=f"kbcha_mileage_to_{mileage}"
                )
            )

    bot.send_message(
        call.message.chat.id,
        f"Выбран минимальный пробег: {mileage_from} км\nТеперь выберите максимальный пробег:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_mileage_to_"))
def handle_kbcha_mileage_to_selection(call):
    # Парсим выбранный пробег
    mileage_to = call.data.split("_")[3]

    # Сохраняем выбранный максимальный пробег
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kbcha_mileage_to"] = mileage_to

    # Показываем выбор цвета
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Добавляем вариант "Любой"
    markup.add(types.InlineKeyboardButton("Любой", callback_data="kbcha_color_Любой"))

    # Добавляем доступные цвета
    for kr_name, info in KBCHACHA_COLOR_TRANSLATIONS.items():
        if kr_name != "Любой":  # Исключаем "Любой", так как мы его уже добавили выше
            markup.add(
                types.InlineKeyboardButton(
                    info["ru"], callback_data=f"kbcha_color_{kr_name}"
                )
            )

    bot.send_message(
        call.message.chat.id,
        f"Выбран диапазон пробега: {user_search_data[user_id]['kbcha_mileage_from']}-{mileage_to} км\nТеперь выберите цвет автомобиля:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kbcha_color_"))
def handle_kbcha_color_selection(call):
    # Парсим выбранный цвет
    color_kr = call.data.split("_")[2]

    # Сохраняем выбранный цвет
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    # Получаем русское название и код цвета
    color_info = KBCHACHA_COLOR_TRANSLATIONS.get(
        color_kr, {"ru": "Неизвестно", "code": ""}
    )
    color_ru = color_info["ru"]
    color_code = color_info["code"]

    user_search_data[user_id]["kbcha_color_kr"] = color_kr
    user_search_data[user_id]["kbcha_color_ru"] = color_ru
    user_search_data[user_id]["kbcha_color_code"] = color_code

    # Получаем информацию о предыдущих выборах пользователя
    maker_name = user_search_data[user_id].get("kbcha_maker_name", "")
    maker_code = user_search_data[user_id].get("kbcha_maker_code", "")
    class_name = user_search_data[user_id].get("kbcha_class_name", "")
    class_code = user_search_data[user_id].get("kbcha_class_code", "")
    car_name = user_search_data[user_id].get("kbcha_car_name", "")
    car_code = user_search_data[user_id].get("kbcha_car_code", "")
    model_name = user_search_data[user_id].get("kbcha_model_name", "")
    model_code = user_search_data[user_id].get("kbcha_model_code", "")
    year_from = user_search_data[user_id].get("kbcha_year_from", "")
    year_to = user_search_data[user_id].get("kbcha_year_to", "")
    mileage_from = user_search_data[user_id].get("kbcha_mileage_from", "")
    mileage_to = user_search_data[user_id].get("kbcha_mileage_to", "")

    # Получаем переводы для всех параметров
    translated_maker_name = translate_smartly(maker_name)
    translated_class_name = translate_smartly(class_name)
    translated_car_name = translate_smartly(car_name)
    translated_model_name = translate_smartly(model_name)

    # Отправляем сообщение о начале поиска
    bot.send_message(
        call.message.chat.id,
        f"🔍 Ищем {translated_maker_name} {translated_class_name} {translated_car_name} {translated_model_name}, год: {year_from}-{year_to}, пробег: {mileage_from}-{mileage_to} км, цвет: {color_ru}...",
    )

    # Ищем автомобили с выбранными параметрами
    cars = search_kbchachacha_cars(
        maker_code,
        class_code,
        car_code,
        model_code,
        year_from,
        year_to,
        mileage_from,
        mileage_to,
        color_code if color_code else None,
    )

    if not cars:
        # Отправляем сообщение, если автомобили не найдены
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "➕ Добавить новый автомобиль в поиск", callback_data="search_car"
            )
        )
        markup.add(
            types.InlineKeyboardButton(
                "🏠 Вернуться в главное меню", callback_data="start"
            )
        )

        bot.send_message(
            call.message.chat.id,
            f"😔 К сожалению, по вашему запросу ничего не найдено.\n\n"
            f"Марка: {translated_maker_name}\n"
            f"Модель: {translated_class_name}\n"
            f"Поколение: {translated_car_name}\n"
            f"Конфигурация: {translated_model_name}\n"
            f"Год: {year_from}-{year_to}\n"
            f"Пробег: {mileage_from}-{mileage_to} км\n"
            f"Цвет: {color_ru}",
            reply_markup=markup,
        )
        return

    # Отправляем только первый найденный автомобиль
    car = cars[0]
    caption = (
        f"🚗 <b>{car['title']}</b>\n"
        f"📆 Год: {car['year']}\n"
        f"🏁 Пробег: {car['mileage']}\n"
        f"📍 Регион: {car['region']}\n"
        f"💰 Цена: {car['price']}만원\n\n"
        f"🔗 <a href='{car['link']}'>Подробнее на KbChaChaCha</a>"
    )

    # Отправляем изображение если есть, или текст если изображения нет
    if car["img_url"] and car["img_url"] != "":
        try:
            bot.send_photo(
                call.message.chat.id, car["img_url"], caption=caption, parse_mode="HTML"
            )
        except Exception:
            # Если не удалось отправить фото, отправляем только текст
            bot.send_message(call.message.chat.id, caption, parse_mode="HTML")
    else:
        bot.send_message(call.message.chat.id, caption, parse_mode="HTML")

    # Отправляем кнопки для дальнейших действий
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Добавить новый автомобиль в поиск", callback_data="search_car"
        )
    )
    markup.add(
        types.InlineKeyboardButton("🏠 Вернуться в главное меню", callback_data="start")
    )

    bot.send_message(
        call.message.chat.id,
        f"✅ Показан результат поиска по запросу:\n\n"
        f"Марка: {translated_maker_name}\n"
        f"Модель: {translated_class_name}\n"
        f"Поколение: {translated_car_name}\n"
        f"Конфигурация: {translated_model_name}\n"
        f"Год: {year_from}-{year_to}\n"
        f"Пробег: {mileage_from}-{mileage_to} км\n"
        f"Цвет: {color_ru}",
        reply_markup=markup,
    )


# Функции для работы с KCar
def get_kcar_manufacturers():
    """Получение списка производителей с KCar"""
    url = "https://api.kcar.com/bc/search/group/mnuftr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {"wr_eq_sell_dcd": "ALL", "wr_in_multi_columns": "cntr_rgn_cd|cntr_cd"}

    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        manufacturers = data.get("data", [])

        # Сортируем по имени производителя на английском
        manufacturers.sort(key=lambda x: x.get("mnuftrEnm", ""))

        return manufacturers
    except Exception as e:
        print("Ошибка при получении марок из KCar:", e)
        return []


def get_kcar_models(maker_code):
    """Получение списка моделей для выбранной марки с KCar"""
    url = "https://api.kcar.com/bc/search/group/modelGrp"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {
        "wr_eq_sell_dcd": "ALL",
        "wr_in_multi_columns": "cntr_rgn_cd|cntr_cd",
        "wr_eq_mnuftr_cd": maker_code,
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        models = data.get("data", [])

        # Сортируем по имени модели
        models.sort(key=lambda x: x.get("modelGrpNm", ""))

        # Отфильтровываем модели с count > 0, так как они реально представлены в списке
        models = [model for model in models if model.get("count", 0) > 0]

        return models
    except Exception as e:
        print(f"Ошибка при получении моделей с KCar для {maker_code}:", e)
        return []


def get_kcar_generations(maker_code, model_code):
    """Получение списка поколений для выбранной модели с KCar"""
    url = "https://api.kcar.com/bc/search/group/model"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {
        "wr_eq_sell_dcd": "ALL",
        "wr_in_multi_columns": "cntr_rgn_cd|cntr_cd",
        "wr_eq_mnuftr_cd": maker_code,
        "wr_eq_model_grp_cd": model_code,
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        generations = data.get("data", [])

        # Сортируем поколения по количеству автомобилей в наличии (по убыванию)
        generations.sort(key=lambda x: x.get("count", 0), reverse=True)

        # Отфильтровываем поколения с count > 0
        generations = [gen for gen in generations if gen.get("count", 0) > 0]

        return generations
    except Exception as e:
        print(
            f"Ошибка при получении поколений с KCar для {maker_code}/{model_code}:", e
        )
        return []


def get_kcar_configurations(maker_code, model_group_code, model_code):
    """Получение списка конфигураций для выбранного поколения с KCar"""
    url = "https://api.kcar.com/bc/search/group/grd"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {
        "wr_eq_sell_dcd": "ALL",
        "wr_in_multi_columns": "cntr_rgn_cd|cntr_cd",
        "wr_eq_mnuftr_cd": maker_code,
        "wr_eq_model_grp_cd": model_group_code,
        "wr_eq_model_cd": model_code,
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        configurations = data.get("data", [])

        # Сортируем конфигурации по количеству автомобилей в наличии (по убыванию)
        configurations.sort(key=lambda x: x.get("count", 0), reverse=True)

        # Отфильтровываем конфигурации с count > 0
        configurations = [
            config for config in configurations if config.get("count", 0) > 0
        ]

        return configurations
    except Exception as e:
        print(
            f"Ошибка при получении конфигураций с KCar для {maker_code}/{model_group_code}/{model_code}:",
            e,
        )
        return []


def handle_kcar_search(call):
    """Обработчик для поиска автомобилей на KCar"""
    # Получаем список производителей
    manufacturers = get_kcar_manufacturers()
    if not manufacturers:
        bot.answer_callback_query(call.id, "Не удалось загрузить марки с KCar.")
        return

    # Создаем клавиатуру с марками
    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in manufacturers:
        maker_name = item.get("mnuftrEnm", "Без названия")
        maker_code = item.get("mnuftrCd", "")

        # Получаем корейское название (если доступно)
        kr_maker_name = item.get("mnuftrNm", "")

        # Переводим корейское название, если оно есть
        translated_kr_name = ""
        if kr_maker_name:
            translated_kr_name = translate_smartly(kr_maker_name)

        # Формируем отображаемое имя
        display_name = maker_name
        if kr_maker_name and translated_kr_name != kr_maker_name:
            display_name = f"{maker_name} ({translated_kr_name})"

        # Используем специальный префикс для отличия от других площадок
        callback_data = f"kcar_brand_{maker_code}_{maker_name}"
        markup.add(
            types.InlineKeyboardButton(display_name, callback_data=callback_data)
        )

    bot.send_message(
        call.message.chat.id, "Выберите марку автомобиля:", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_brand_"))
def handle_kcar_brand_selection(call):
    """Обработчик выбора марки автомобиля на KCar"""
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    maker_code = parts[2]
    maker_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранную марку у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_maker_code"] = maker_code
    user_search_data[user_id]["kcar_maker_name"] = maker_name

    # Получаем список моделей для выбранной марки
    models = get_kcar_models(maker_code)
    if not models:
        bot.send_message(
            call.message.chat.id,
            f"Не удалось загрузить модели для {maker_name} или для этой марки нет доступных моделей.",
        )
        return

    # Создаем клавиатуру с моделями
    markup = types.InlineKeyboardMarkup(row_width=2)
    for item in models:
        model_name = item.get("modelGrpNm", "Без названия")
        model_code = item.get("modelGrpCd", "")

        # Переводим название модели
        translated_model_name = translate_smartly(model_name)

        # Формируем отображаемое имя
        display_name = model_name
        if model_name != translated_model_name and translated_model_name != model_name:
            display_name = f"{translated_model_name} ({model_name})"

        callback_data = f"kcar_model_{model_code}_{model_name}"
        markup.add(
            types.InlineKeyboardButton(display_name, callback_data=callback_data)
        )

    bot.send_message(
        call.message.chat.id,
        f"Марка: {maker_name}\nВыберите модель:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_model_"))
def handle_kcar_model_selection(call):
    """Обработчик выбора модели автомобиля на KCar"""
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    model_code = parts[2]
    model_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранную модель у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_model_code"] = model_code
    user_search_data[user_id]["kcar_model_name"] = model_name

    # Переводим название модели
    translated_model_name = translate_smartly(model_name)

    # Получаем информацию о марке
    maker_name = user_search_data[user_id].get("kcar_maker_name", "")
    maker_code = user_search_data[user_id].get("kcar_maker_code", "")

    # Переводим название марки
    translated_maker_name = translate_smartly(maker_name)

    # Получаем список поколений для выбранной модели
    generations = get_kcar_generations(maker_code, model_code)
    if not generations:
        bot.send_message(
            call.message.chat.id,
            f"Не удалось загрузить поколения для {translated_model_name} или для этой модели нет доступных поколений.",
        )
        return

    # Создаем клавиатуру с поколениями
    markup = types.InlineKeyboardMarkup(row_width=1)
    for item in generations:
        gen_name = item.get("modelNm", "Без названия")
        gen_year = item.get("prdcnYear", "")
        gen_code = item.get("modelCd", "")

        # Переводим название поколения
        translated_gen_name = translate_smartly(gen_name)

        # Формируем текст кнопки с названием и годами производства
        display_text = f"{translated_gen_name} {gen_year}"
        if gen_name != translated_gen_name and translated_gen_name != gen_name:
            display_text = f"{translated_gen_name} ({gen_name}) {gen_year}"

        callback_data = f"kcar_gen_{gen_code}_{gen_name}"

        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    # Определяем, как отображать названия марки и модели
    display_maker_name = translated_maker_name
    if maker_name != translated_maker_name and translated_maker_name != maker_name:
        display_maker_name = f"{translated_maker_name} ({maker_name})"

    display_model_name = translated_model_name
    if model_name != translated_model_name and translated_model_name != model_name:
        display_model_name = f"{translated_model_name} ({model_name})"

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_model_name}\nВыберите поколение:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_gen_"))
def handle_kcar_generation_selection(call):
    """Обработчик выбора поколения автомобиля на KCar"""
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    gen_code = parts[2]
    gen_name = parts[3] if len(parts) > 3 else "Неизвестно"

    # Сохраняем выбранное поколение у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_gen_code"] = gen_code
    user_search_data[user_id]["kcar_gen_name"] = gen_name

    # Переводим название поколения
    translated_gen_name = translate_smartly(gen_name)

    # Получаем информацию о предыдущих выборах
    maker_name = user_search_data[user_id].get("kcar_maker_name", "")
    maker_code = user_search_data[user_id].get("kcar_maker_code", "")
    model_name = user_search_data[user_id].get("kcar_model_name", "")
    model_code = user_search_data[user_id].get("kcar_model_code", "")

    # Переводим названия
    translated_maker_name = translate_smartly(maker_name)
    translated_model_name = translate_smartly(model_name)

    # Дополнительно получаем поколения снова, чтобы извлечь информацию о годах производства
    generations = get_kcar_generations(maker_code, model_code)

    # Ищем информацию о выбранном поколении среди полученных данных
    selected_generation = None
    for gen in generations:
        if gen.get("modelCd") == gen_code:
            selected_generation = gen
            break

    # Получаем и сохраняем года выпуска поколения
    if selected_generation:
        # Получаем строку с информацией о годах из поля prdcnYear
        gen_year_str = selected_generation.get("prdcnYear", "")
        print(
            f"⚙️ DEBUG kcar_gen_selection - Found generation year info: '{gen_year_str}'"
        )

        # Если есть информация о годах в формате '(19~24년)' или подобном
        # сначала удалим круглые скобки если они есть
        if gen_year_str.startswith("(") and gen_year_str.endswith(")"):
            gen_year_str = gen_year_str[1:-1]

        if "~" in gen_year_str:
            year_parts = gen_year_str.split("~")
            if len(year_parts) == 2:
                # Первая часть - год начала производства (например, '19')
                start_year_str = year_parts[0].strip()
                # Вторая часть - год окончания (например, '24년')
                end_year_str = year_parts[1].replace("년", "").strip()

                # Преобразуем в полный формат года
                current_century = "20"  # Предполагаем, что все модели 21 века

                # Обрабатываем начальный год
                if len(start_year_str) == 2 and start_year_str.isdigit():
                    start_year = int(current_century + start_year_str)
                    user_search_data[user_id]["kcar_generation_start_year"] = start_year
                    print(
                        f"⚙️ DEBUG kcar_gen_selection - Extracted start_year: {start_year}"
                    )

                # Обрабатываем конечный год
                if len(end_year_str) == 2 and end_year_str.isdigit():
                    end_year = int(current_century + end_year_str)
                    user_search_data[user_id]["kcar_generation_end_year"] = end_year
                    print(
                        f"⚙️ DEBUG kcar_gen_selection - Extracted end_year: {end_year}"
                    )

                # Если конечный год меньше начального (например, при переходе века), корректируем
                if (
                    "kcar_generation_start_year" in user_search_data[user_id]
                    and "kcar_generation_end_year" in user_search_data[user_id]
                ):
                    if (
                        user_search_data[user_id]["kcar_generation_end_year"]
                        < user_search_data[user_id]["kcar_generation_start_year"]
                    ):
                        user_search_data[user_id][
                            "kcar_generation_end_year"
                        ] += 100  # Добавляем век
        elif "현재" in gen_year_str:  # 현재 = "настоящее время" на корейском
            # Если годы указаны как "с X года по настоящее время"
            year_part = (
                gen_year_str.replace("년", "")
                .replace("현재", "")
                .replace("~", "")
                .strip()
            )
            if len(year_part) == 2 and year_part.isdigit():
                start_year = int("20" + year_part)
                user_search_data[user_id]["kcar_generation_start_year"] = start_year
                user_search_data[user_id][
                    "kcar_generation_end_year"
                ] = datetime.now().year
                print(
                    f"⚙️ DEBUG kcar_gen_selection - Extracted years: {start_year}-present"
                )

    # Получаем список конфигураций для выбранного поколения
    configurations = get_kcar_configurations(maker_code, model_code, gen_code)
    if not configurations:
        bot.send_message(
            call.message.chat.id,
            f"Не удалось загрузить конфигурации для {translated_gen_name} или для этого поколения нет доступных конфигураций.",
        )
        return

    # Создаем клавиатуру с конфигурациями
    markup = types.InlineKeyboardMarkup(row_width=1)
    for item in configurations:
        config_name = item.get("grdNm", "Без названия")
        config_code = item.get("grdCd", "")
        count = item.get("count", 0)

        # Переводим название конфигурации
        translated_config_name = translate_smartly(config_name)

        # Формируем текст кнопки с названием и количеством автомобилей
        display_text = f"{translated_config_name} ({count} шт.)"
        if (
            config_name != translated_config_name
            and translated_config_name != config_name
        ):
            display_text = f"{translated_config_name} ({config_name}) ({count} шт.)"

        callback_data = f"kcar_config_{config_code}_{config_name}"

        markup.add(
            types.InlineKeyboardButton(display_text, callback_data=callback_data)
        )

    # Определяем, как отображать названия
    display_maker_name = translated_maker_name
    if maker_name != translated_maker_name and translated_maker_name != maker_name:
        display_maker_name = f"{translated_maker_name} ({maker_name})"

    display_model_name = translated_model_name
    if model_name != translated_model_name and translated_model_name != model_name:
        display_model_name = f"{translated_model_name} ({model_name})"

    display_gen_name = translated_gen_name
    if gen_name != translated_gen_name and translated_gen_name != gen_name:
        display_gen_name = f"{translated_gen_name} ({gen_name})"

    # Показываем информацию о годах выпуска, если она доступна
    years_info = ""
    if (
        "kcar_generation_start_year" in user_search_data[user_id]
        and "kcar_generation_end_year" in user_search_data[user_id]
    ):
        start_year = user_search_data[user_id]["kcar_generation_start_year"]
        end_year = user_search_data[user_id]["kcar_generation_end_year"]
        years_info = f" ({start_year}-{end_year})"

    # Печатаем итоговые данные для отладки
    print(f"⚙️ DEBUG kcar_gen_selection - Final user_search_data for user {user_id}:")
    print(
        f"kcar_generation_start_year: {user_search_data[user_id].get('kcar_generation_start_year')}"
    )
    print(
        f"kcar_generation_end_year: {user_search_data[user_id].get('kcar_generation_end_year')}"
    )

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_model_name}\nПоколение: {display_gen_name}{years_info}\nВыберите конфигурацию:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_config_"))
def handle_kcar_configuration_selection(call):
    """Обработчик выбора конфигурации автомобиля на KCar"""
    # Парсим данные из callback_data
    parts = call.data.split("_", 3)
    config_code = parts[2]
    config_name = parts[3] if len(parts) > 3 else "Неизвестно"

    print(f"✅ DEBUG kcar_config_selection - raw data:")
    print(f"config_code: {config_code}")
    print(f"config_name: {config_name}")

    # Сохраняем выбранную конфигурацию у пользователя для дальнейшего использования
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_config_code"] = config_code
    user_search_data[user_id]["kcar_config_name"] = config_name

    # Переводим название конфигурации
    translated_config_name = translate_smartly(config_name)

    # Получаем информацию о предыдущих выборах
    maker_name = user_search_data[user_id].get("kcar_maker_name", "")
    maker_code = user_search_data[user_id].get("kcar_maker_code", "")
    model_name = user_search_data[user_id].get("kcar_model_name", "")
    model_code = user_search_data[user_id].get("kcar_model_code", "")
    gen_name = user_search_data[user_id].get("kcar_gen_name", "")
    gen_code = user_search_data[user_id].get("kcar_gen_code", "")

    # Переводим все названия
    translated_maker_name = translate_smartly(maker_name)
    translated_model_name = translate_smartly(model_name)
    translated_gen_name = translate_smartly(gen_name)

    # Текущий год для использования в расчетах
    current_year = datetime.now().year

    # Проверяем, были ли годы извлечены на этапе выбора поколения
    start_year = user_search_data[user_id].get("kcar_generation_start_year")
    end_year = user_search_data[user_id].get("kcar_generation_end_year")

    print(f"⚙️ DEBUG kcar_config_selection - Checking previously extracted years:")
    print(f"kcar_generation_start_year: {start_year}")
    print(f"kcar_generation_end_year: {end_year}")

    # Если годы были извлечены ранее, используем их
    if start_year is not None and end_year is not None:
        print(
            f"⚙️ DEBUG kcar_config_selection - Using previously extracted years: {start_year}-{end_year}"
        )
        years_extracted = True
    else:
        # Если годы не были извлечены ранее, пытаемся извлечь их из названия поколения
        print(
            f"⚙️ DEBUG kcar_config_selection - No previously extracted years, trying to extract from gen_name: '{gen_name}'"
        )
        years_extracted = False

        # По умолчанию используем значения
        start_year = current_year - 5  # По умолчанию 5 лет назад
        end_year = current_year  # По умолчанию текущий год

        # Пытаемся извлечь годы производства из названия поколения
        if "(" in gen_name and ")" in gen_name:
            period_part = gen_name.split("(")[1].split(")")[0].strip()
            print(f"⚙️ DEBUG kcar_config_selection - period_part: '{period_part}'")

            # Проверяем разные форматы разделителей
            if "—" in period_part:
                parts = period_part.split("—")
            elif "-" in period_part:
                parts = period_part.split("-")
            elif "~" in period_part:
                parts = period_part.split("~")
            else:
                parts = []

            print(f"⚙️ DEBUG kcar_config_selection - split parts: {parts}")

            if len(parts) == 2:
                start_date = parts[0].strip()
                end_date = parts[1].strip()
                print(
                    f"⚙️ DEBUG kcar_config_selection - start_date: '{start_date}', end_date: '{end_date}'"
                )

                # Извлекаем год из начальной даты
                if "." in start_date:
                    start_year_str = start_date.split(".")[-1]
                    print(
                        f"⚙️ DEBUG kcar_config_selection - parsed start_year_str: '{start_year_str}'"
                    )
                    if start_year_str.isdigit() and len(start_year_str) == 4:
                        start_year = int(start_year_str)
                        years_extracted = True
                elif start_date.isdigit():
                    if len(start_date) == 4:
                        start_year = int(start_date)
                        years_extracted = True
                    elif len(start_date) == 2:
                        start_year = int("20" + start_date)  # Предполагаем 21 век
                        years_extracted = True

                # Извлекаем год из конечной даты
                if "." in end_date:
                    end_year_str = end_date.split(".")[-1]
                    print(
                        f"⚙️ DEBUG kcar_config_selection - parsed end_year_str: '{end_year_str}'"
                    )
                    if end_year_str.isdigit() and len(end_year_str) == 4:
                        end_year = int(end_year_str)
                        years_extracted = True
                elif end_date.isdigit():
                    if len(end_date) == 4:
                        end_year = int(end_date)
                        years_extracted = True
                    elif len(end_date) == 2:
                        end_year = int("20" + end_date)  # Предполагаем 21 век
                        years_extracted = True
                elif "현재" in end_date:  # 현재 = настоящее время
                    end_year = current_year
                    years_extracted = True

    print(
        f"⚙️ DEBUG kcar_config_selection - final start_year: {start_year}, end_year: {end_year}, years_extracted: {years_extracted}"
    )

    # Гарантируем, что start_year не больше текущего года
    if start_year > current_year:
        start_year = current_year - 5

    # Если years_extracted = true и end_year < start_year, меняем их местами или корректируем
    if years_extracted and end_year < start_year:
        # Если разница небольшая, возможно это ошибка и годы нужно поменять местами
        if start_year - end_year < 10:
            start_year, end_year = end_year, start_year
            print(
                f"⚙️ DEBUG kcar_config_selection - swapped years: start_year: {start_year}, end_year: {end_year}"
            )
        else:
            # Если большая разница, то скорее всего проблема века
            end_year += 100
            print(
                f"⚙️ DEBUG kcar_config_selection - adjusted end_year century: {end_year}"
            )

    # Если end_year > current_year + 1 (год окончания далеко в будущем), ограничиваем для отображения
    # только если мы не уверены в извлеченных годах
    display_end_year = end_year
    if not years_extracted and display_end_year > current_year + 1:
        display_end_year = current_year

    # Сохраняем определенные годы для использования в дальнейшем, если они еще не сохранены
    if "kcar_generation_start_year" not in user_search_data[user_id]:
        user_search_data[user_id]["kcar_generation_start_year"] = start_year
    if "kcar_generation_end_year" not in user_search_data[user_id]:
        user_search_data[user_id]["kcar_generation_end_year"] = end_year

    # Показываем выбор года от
    year_markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем года от начала производства поколения до его конца или текущего года
    year_range = list(range(start_year, min(display_end_year, current_year) + 1))
    print(f"⚙️ DEBUG kcar_config_selection - year range for buttons: {year_range}")

    for year in year_range:
        year_markup.add(
            types.InlineKeyboardButton(
                f"{year}", callback_data=f"kcar_year_from_{year}"
            )
        )

    # Определяем, как отображать названия
    display_maker_name = translated_maker_name
    if maker_name != translated_maker_name and translated_maker_name != maker_name:
        display_maker_name = f"{translated_maker_name} ({maker_name})"

    display_model_name = translated_model_name
    if model_name != translated_model_name and translated_model_name != model_name:
        display_model_name = f"{translated_model_name} ({model_name})"

    display_gen_name = translated_gen_name
    if gen_name != translated_gen_name and translated_gen_name != gen_name:
        display_gen_name = f"{translated_gen_name} ({gen_name})"

    display_config_name = translated_config_name
    if config_name != translated_config_name and translated_config_name != config_name:
        display_config_name = f"{translated_config_name} ({config_name})"

    # Формируем сообщение с информацией о периоде выпуска поколения
    period_message = f"поколение {start_year}-{end_year}"

    bot.send_message(
        call.message.chat.id,
        f"Марка: {display_maker_name}\nМодель: {display_model_name}\nПоколение: {display_gen_name}\nКонфигурация: {display_config_name}\n\nВыберите начальный год выпуска ({period_message}):",
        reply_markup=year_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_year_from_"))
def handle_kcar_year_from_selection(call):
    """Обработчик выбора начального года для KCar"""
    # Парсим выбранный год
    year_from = call.data.split("_")[3]

    # Сохраняем выбранный начальный год
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_year_from"] = year_from

    # Получаем конечный год периода выпуска поколения из сохраненных данных
    # Приоритетно используем год окончания производства поколения, сохраненный ранее
    end_year = user_search_data[user_id].get(
        "kcar_generation_end_year", datetime.now().year
    )
    current_year = datetime.now().year
    year_from_int = int(year_from)

    # Проверка адекватности значения end_year
    if end_year > current_year + 1:
        # Если end_year слишком далеко в будущем, ограничиваем текущим годом
        display_end_year = current_year
        print(
            f"⚙️ DEBUG kcar_year_from_selection - limiting display_end_year to current_year: {current_year} (was {end_year})"
        )
    else:
        display_end_year = end_year

    print(
        f"⚙️ DEBUG kcar_year_from_selection - using year range: {year_from_int} to {end_year}, display_end_year: {display_end_year}"
    )

    bot.send_message(
        call.message.chat.id,
        f"Выбран начальный год: {year_from}. Теперь выберите конечный год:",
        reply_markup=get_kcar_year_to_keyboard(
            year_from_int, min(display_end_year, current_year)
        ),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_year_to_"))
def handle_kcar_year_to_selection(call):
    """Обработчик выбора конечного года для KCar"""
    # Парсим выбранный год
    year_to = call.data.split("_")[3]

    # Сохраняем выбранный конечный год
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_year_to"] = year_to

    # Показываем выбор минимального пробега
    mileage_markup = types.InlineKeyboardMarkup(row_width=3)
    for mileage in [0, 10000, 20000, 30000, 50000, 70000, 100000]:
        mileage_markup.add(
            types.InlineKeyboardButton(
                f"{mileage} км", callback_data=f"kcar_mileage_from_{mileage}"
            )
        )

    bot.send_message(
        call.message.chat.id,
        f"Выбран диапазон годов: {user_search_data[user_id]['kcar_year_from']}-{year_to}\nТеперь выберите минимальный пробег:",
        reply_markup=mileage_markup,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("kcar_mileage_from_")
)
def handle_kcar_mileage_from_selection(call):
    """Обработчик выбора минимального пробега для KCar"""
    # Парсим выбранный пробег
    mileage_from = call.data.split("_")[3]

    # Сохраняем выбранный минимальный пробег
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_mileage_from"] = mileage_from

    # Показываем выбор максимального пробега
    mileage_markup = types.InlineKeyboardMarkup(row_width=3)
    mileage_from_int = int(mileage_from)

    for mileage in [50000, 100000, 150000, 200000, 250000, 300000]:
        if mileage > mileage_from_int:
            mileage_markup.add(
                types.InlineKeyboardButton(
                    f"{mileage} км", callback_data=f"kcar_mileage_to_{mileage}"
                )
            )

    bot.send_message(
        call.message.chat.id,
        f"Выбран минимальный пробег: {mileage_from} км\nТеперь выберите максимальный пробег:",
        reply_markup=mileage_markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_mileage_to_"))
def handle_kcar_mileage_to_selection(call):
    """Обработчик выбора максимального пробега для KCar"""
    # Парсим выбранный пробег
    mileage_to = call.data.split("_")[3]

    # Сохраняем выбранный максимальный пробег
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    user_search_data[user_id]["kcar_mileage_to"] = mileage_to

    # Показываем выбор цвета
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Добавляем вариант "Любой"
    markup.add(types.InlineKeyboardButton("Любой", callback_data="kcar_color_Любой"))

    # Добавляем доступные цвета
    for kr_name, ru_name in KCAR_COLOR_TRANSLATIONS.items():
        if kr_name != "Любой":  # Исключаем "Любой", так как мы его уже добавили выше
            markup.add(
                types.InlineKeyboardButton(
                    ru_name, callback_data=f"kcar_color_{kr_name}"
                )
            )

    bot.send_message(
        call.message.chat.id,
        f"Выбран диапазон пробега: {user_search_data[user_id]['kcar_mileage_from']}-{mileage_to} км\nТеперь выберите цвет автомобиля:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("kcar_color_"))
def handle_kcar_color_selection(call):
    """Обработчик выбора цвета для KCar"""
    # Парсим выбранный цвет
    color_kr = call.data.split("_")[2]

    # Сохраняем выбранный цвет
    user_id = call.from_user.id
    if user_id not in user_search_data:
        user_search_data[user_id] = {}

    color_ru = KCAR_COLOR_TRANSLATIONS.get(color_kr, "Неизвестно")

    user_search_data[user_id]["kcar_color_kr"] = color_kr
    user_search_data[user_id]["kcar_color_ru"] = color_ru

    # Получаем все сохраненные данные о выборе пользователя
    maker_name = user_search_data[user_id].get("kcar_maker_name", "")
    maker_code = user_search_data[user_id].get("kcar_maker_code", "")
    model_name = user_search_data[user_id].get("kcar_model_name", "")
    model_code = user_search_data[user_id].get("kcar_model_code", "")
    gen_name = user_search_data[user_id].get("kcar_gen_name", "")
    gen_code = user_search_data[user_id].get("kcar_gen_code", "")
    config_name = user_search_data[user_id].get("kcar_config_name", "")
    config_code = user_search_data[user_id].get("kcar_config_code", "")
    year_from = user_search_data[user_id].get("kcar_year_from", "")
    year_to = user_search_data[user_id].get("kcar_year_to", "")
    mileage_from = user_search_data[user_id].get("kcar_mileage_from", "")
    mileage_to = user_search_data[user_id].get("kcar_mileage_to", "")

    # Переводим все названия
    translated_maker_name = translate_smartly(maker_name)
    translated_model_name = translate_smartly(model_name)
    translated_gen_name = translate_smartly(gen_name)
    translated_config_name = translate_smartly(config_name)

    # Определяем, как отображать названия
    display_maker_name = translated_maker_name
    if maker_name != translated_maker_name and translated_maker_name != maker_name:
        display_maker_name = f"{translated_maker_name} ({maker_name})"

    display_model_name = translated_model_name
    if model_name != translated_model_name and translated_model_name != model_name:
        display_model_name = f"{translated_model_name} ({model_name})"

    display_gen_name = translated_gen_name
    if gen_name != translated_gen_name and translated_gen_name != gen_name:
        display_gen_name = f"{translated_gen_name} ({gen_name})"

    display_config_name = translated_config_name
    if config_name != translated_config_name and translated_config_name != config_name:
        display_config_name = f"{translated_config_name} ({config_name})"

    # Отправляем сообщение о завершении выбора параметров
    summary = (
        f"✅ Поиск на KCar с параметрами:\n\n"
        f"Марка: {display_maker_name}\n"
        f"Модель: {display_model_name}\n"
        f"Поколение: {display_gen_name}\n"
        f"Конфигурация: {display_config_name}\n"
        f"Год: {year_from}-{year_to}\n"
        f"Пробег: {mileage_from}-{mileage_to} км\n"
        f"Цвет: {color_ru}\n\n"
        f"Пожалуйста, подождите, идет поиск автомобилей..."
    )

    message = bot.send_message(
        call.message.chat.id,
        summary,
        parse_mode="HTML",
    )

    # Ищем автомобили с помощью функции парсинга HTML
    cars = search_kcar_cars_by_html(
        maker_code,
        model_code,
        gen_code,
        year_from=year_from,
        year_to=year_to,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        color=color_kr,  # Передаем корейское название цвета
    )

    if not cars:
        # Если автомобили не найдены
        # Создаем ссылку на сайт с поиском без ограничений по цвету
        search_url = f"https://www.kcar.com/bc/search?searchCond=%7B%22wr_eq_mnuftr_cd%22%3A%22{maker_code}%22%2C%22wr_eq_model_grp_cd%22%3A%22{model_code}%22%2C%22wr_eq_model_cd%22%3A%22{gen_code}%22%7D"

        no_results_text = (
            f"{summary}\n\n❌ <b>К сожалению, автомобили с указанными параметрами не найдены.</b>\n\n"
            f"Возможные причины:\n"
            f"• На данный момент нет автомобилей выбранного цвета\n"
            f"• Указанные параметры слишком ограничивают поиск\n\n"
            f"Попробуйте изменить критерии поиска или посмотреть все доступные автомобили "
            f"данной модели на сайте KCar по ссылке ниже."
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Просмотреть на сайте KCar", url=search_url)
        )
        markup.add(
            types.InlineKeyboardButton("➕ Новый поиск", callback_data="search_car")
        )
        markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="start"))

        bot.edit_message_text(
            no_results_text,
            chat_id=call.message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        # Формируем сообщение с результатами поиска
        bot.edit_message_text(
            f"{summary}\n\n✅ Найдено автомобилей: {len(cars)}",
            chat_id=call.message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
        )

        # Отправляем информацию о каждом автомобиле
        for car in cars:
            car_message = (
                f"🚗 <b>{car['title']}</b>\n\n"
                f"💰 <b>Цена:</b> {car['price']}\n"
                f"📅 <b>Год:</b> {car['year']}\n"
                f"🛣 <b>Пробег:</b> {car['mileage']}\n"
                f"⛽️ <b>Топливо:</b> {car['fuel_type']}\n"
                f"📍 <b>Местоположение:</b> {car['location']}\n"
            )

            if car["description"]:
                car_message += f"\n📝 <b>Описание:</b> {car['description']}\n"

            if car["labels"]:
                labels_text = ", ".join(car["labels"])
                car_message += f"\n🏷 <b>Особенности:</b> {labels_text}\n"

            # Добавляем ссылку на страницу автомобиля
            car_message += f"\n🔎 <a href='{car['link']}'>Подробнее на сайте KCar</a>"

            # Создаем клавиатуру с кнопкой для перехода к автомобилю
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("Открыть на сайте KCar", url=car["link"])
            )

            # Если есть изображение, отправляем фото с описанием
            if car["img_url"]:
                try:
                    bot.send_photo(
                        call.message.chat.id,
                        car["img_url"],
                        caption=car_message,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    print(f"Ошибка при отправке фото: {e}")
                    # Если не удалось отправить фото, отправляем только текст
                    bot.send_message(
                        call.message.chat.id,
                        car_message,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
            else:
                # Если нет изображения, отправляем только текст
                bot.send_message(
                    call.message.chat.id,
                    car_message,
                    reply_markup=markup,
                    parse_mode="HTML",
                )

    # Кнопки для дальнейших действий
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Добавить новый автомобиль в поиск", callback_data="search_car"
        )
    )
    markup.add(
        types.InlineKeyboardButton("🏠 Вернуться в главное меню", callback_data="start")
    )

    bot.send_message(
        call.message.chat.id,
        "Что вы хотите сделать дальше?",
        reply_markup=markup,
        parse_mode="HTML",
    )


def search_kcar_cars_by_html(
    mnuftr_cd,
    model_grp_cd,
    model_cd,
    year_from=None,
    year_to=None,
    mileage_from=None,
    mileage_to=None,
    color=None,
):
    """
    Поиск автомобилей на KCar через парсинг HTML страницы

    Параметры:
    mnuftr_cd (str): Код производителя
    model_grp_cd (str): Код группы моделей
    model_cd (str): Код модели
    year_from (str, optional): Начальный год выпуска
    year_to (str, optional): Конечный год выпуска
    mileage_from (str, optional): Минимальный пробег
    mileage_to (str, optional): Максимальный пробег
    color (str, optional): Корейское название цвета

    Возвращает:
    list: Список автомобилей с информацией
    """
    # Базовый поисковый запрос
    base_search_cond = {
        "wr_eq_mnuftr_cd": mnuftr_cd,
        "wr_eq_model_grp_cd": model_grp_cd,
        "wr_eq_model_cd": model_cd,
    }

    # Добавляем дополнительные параметры, если они указаны
    if year_from and year_to:
        base_search_cond["wr_bt_prdcn_year"] = f"{year_from},{year_to}"

    if mileage_from is not None and mileage_to is not None:
        base_search_cond["wr_bt_accent_km"] = f"{mileage_from},{mileage_to}"

    # Добавляем параметр цвета, если выбран конкретный цвет (не "Любой")
    if color and color != "Любой":
        # Находим корейское название цвета среди ключей словаря
        for kr_color, ru_color in KCAR_COLOR_TRANSLATIONS.items():
            if kr_color == color:
                # Здесь предполагается, что код цвета может потребоваться позже
                # Сейчас используем просто корейское название
                base_search_cond["wr_eq_extl_color_nm"] = kr_color
                break

    # Преобразуем словарь в JSON строку и кодируем для URL
    search_cond = urllib.parse.quote(json.dumps(base_search_cond))

    # Формируем URL для запроса
    url = f"https://www.kcar.com/bc/search?searchCond={search_cond}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        print(f"DEBUG: Отправка запроса на URL: {url}")
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Ошибка при получении страницы: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Ищем блок с автомобилями
        car_list_wrap = soup.select_one("div.carListWrap")
        if not car_list_wrap:
            print("Не найден блок с автомобилями (div.carListWrap)")
            return []

        # Извлекаем все блоки с автомобилями
        car_list_boxes = car_list_wrap.select("div.carListBox")
        if not car_list_boxes:
            print("Не найдены блоки с автомобилями (div.carListBox)")
            # Проверяем, содержит ли блок сообщение о пустых результатах
            empty_result = car_list_wrap.select_one("div.empty-car-list")
            if empty_result:
                print("Найдено сообщение о пустых результатах")
            return []

        print(f"DEBUG: Найдено {len(car_list_boxes)} автомобилей")

        results = []
        for box in car_list_boxes[:5]:  # Ограничиваем до 5 результатов
            try:
                # Извлекаем данные об автомобиле
                # Название автомобиля
                car_name_elem = box.select_one("div.carName p.carTit a")
                car_name = car_name_elem.text.strip() if car_name_elem else "Неизвестно"
                # Переводим название автомобиля
                translated_car_name = translate_smartly(car_name)

                # Получаем ссылку на автомобиль
                car_link = car_name_elem.get("href", "") if car_name_elem else ""
                if car_link:
                    car_link = f"https://www.kcar.com{car_link}"

                # Цена
                car_exp_elem = box.select_one("div.carExpIn p.carExp")
                car_price = car_exp_elem.text.strip() if car_exp_elem else "Неизвестно"

                # Детали автомобиля (год, пробег, тип топлива)
                car_details_elem = box.select_one("p.detailCarCon")
                car_details = []
                if car_details_elem:
                    for span in car_details_elem.select("span"):
                        car_details.append(span.text.strip())

                # Проверяем что у нас есть достаточно деталей
                year = car_details[0] if len(car_details) > 0 else "Неизвестно"
                mileage = car_details[1] if len(car_details) > 1 else "Неизвестно"
                fuel_type = car_details[2] if len(car_details) > 2 else "Неизвестно"
                location = car_details[3] if len(car_details) > 3 else "Неизвестно"

                # Переводим данные
                translated_fuel_type = translate_smartly(fuel_type)
                translated_location = translate_smartly(location)

                # Изображение автомобиля
                img_elem = box.select_one("div.carListImg a img")
                img_url = img_elem.get("src", "") if img_elem else ""

                # Проверяем ссылку на изображение, если она относительная, добавляем домен
                if img_url and not img_url.startswith(("http://", "https://")):
                    img_url = f"https://www.kcar.com{img_url}"

                # Краткое описание автомобиля
                car_desc_elem = box.select_one("div.carSimcDesc")
                car_desc = car_desc_elem.text.strip() if car_desc_elem else ""
                # Переводим описание
                translated_desc = translate_smartly(car_desc)

                # Получаем дополнительные метки (VIP, 360 и т.д.)
                car_labels = []
                free_delivery = box.select_one("span.stateDlvy")
                if free_delivery:
                    car_labels.append("Бесплатная доставка")

                car_360 = box.select_one("span.car360Img")
                if car_360:
                    car_labels.append("360° обзор")

                # Проверяем наличие специальных опций
                special_options = box.select("ul.infoTooltip li button")
                for option in special_options:
                    option_text = option.text.strip()
                    if option_text:
                        translated_option = translate_smartly(option_text)
                        car_labels.append(translated_option)

                results.append(
                    {
                        "title": translated_car_name,
                        "original_title": car_name,
                        "price": car_price,
                        "year": year,
                        "mileage": mileage,
                        "fuel_type": translated_fuel_type,
                        "original_fuel_type": fuel_type,
                        "location": translated_location,
                        "original_location": location,
                        "description": translated_desc,
                        "original_description": car_desc,
                        "link": car_link,
                        "img_url": img_url,
                        "labels": car_labels,
                    }
                )
                print(f"DEBUG: Успешно обработан автомобиль {car_name}")
            except Exception as e:
                print(f"Ошибка при парсинге автомобиля: {e}")
                continue

        return results
    except Exception as e:
        print(f"Ошибка при поиске автомобилей на KCar через HTML: {e}")
        return []


def get_kcar_year_to_keyboard(start_year, end_year):
    """Создает клавиатуру с диапазоном лет от start_year до end_year для выбора конечного года"""
    year_markup = types.InlineKeyboardMarkup(row_width=3)

    print(
        f"⚙️ DEBUG get_kcar_year_to_keyboard - Creating keyboard with range: {start_year} to {end_year}"
    )

    # Добавляем все года от начального до конечного
    for year in range(start_year, end_year + 1):
        year_markup.add(
            types.InlineKeyboardButton(f"{year}", callback_data=f"kcar_year_to_{year}")
        )

    return year_markup


@bot.callback_query_handler(func=lambda call: call.data.startswith("price_from_"))
def handle_price_from_selection(call):
    user_id = call.from_user.id

    # Проверяем, что у пользователя есть сохраненные данные
    if user_id not in user_search_data:
        bot.answer_callback_query(
            call.id, "Ошибка: данные не найдены. Начните поиск заново."
        )
        return

    # Парсим выбранную минимальную цену
    param = call.data.split("_")[2]

    if param == "any":
        price_from = None
        price_from_display = "Любая"
    else:
        price_from = int(param)
        price_from_display = f"{price_from // 100} млн вон"

    # Сохраняем выбранную минимальную цену
    user_search_data[user_id]["price_from"] = price_from

    # Получаем сохраненные данные
    user_data = user_search_data[user_id]

    # Отображаем выбор максимальной цены
    markup = types.InlineKeyboardMarkup(row_width=3)

    # Добавляем кнопку "Любая" для максимальной цены
    markup.add(types.InlineKeyboardButton("Любая", callback_data="price_to_any"))

    # Добавляем кнопки с диапазоном цен от 1 до 100 млн вон
    # Если выбрана минимальная цена, начинаем с нее
    min_price_value = 0 if price_from is None else price_from // 100

    price_ranges = [
        p
        for p in [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100]
        if p > min_price_value
    ]

    buttons = []
    for price in price_ranges:
        price_param = price * 100  # Конвертация в параметр API (1 млн = 100)
        buttons.append(
            types.InlineKeyboardButton(
                f"{price} млн", callback_data=f"price_to_{price_param}"
            )
        )

    # Добавляем кнопки группами по 3
    for i in range(0, len(buttons), 3):
        row = buttons[i : i + 3]
        markup.row(*row)

    # Формируем текст с выбранными параметрами
    selected_color_ru = (
        "Любой"
        if user_data.get("color") == "all"
        else COLOR_TRANSLATIONS.get(user_data.get("color", ""), "Неизвестно")
    )

    bot.edit_message_text(
        f"Марка: {user_data.get('manufacturer')} ({user_data.get('model_group')})\n"
        f"Модель: {user_data.get('model')} ({user_data.get('trim')})\n"
        f"Год выпуска: {user_data.get('year_from')}-{user_data.get('year_to')}\n"
        f"Пробег: от {user_data.get('mileage_from')} до {user_data.get('mileage_to')} км\n"
        f"Цвет: {selected_color_ru}\n"
        f"Минимальная цена: {price_from_display}\n\n"
        f"Выберите максимальную цену:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("price_to_"))
def handle_price_to_selection(call):
    user_id = call.from_user.id

    # Проверяем, что у пользователя есть сохраненные данные
    if user_id not in user_search_data:
        bot.answer_callback_query(
            call.id, "Ошибка: данные не найдены. Начните поиск заново."
        )
        return

    # Парсим выбранную максимальную цену
    param = call.data.split("_")[2]

    if param == "any":
        price_to = None
        price_to_display = "Любая"
    else:
        price_to = int(param)
        price_to_display = f"{price_to // 100} млн вон"

    # Сохраняем выбранную максимальную цену
    user_search_data[user_id]["price_to"] = price_to

    # Получаем сохраненные данные пользователя
    user_data = user_search_data[user_id]

    # Проверяем наличие всех необходимых данных и устанавливаем значения по умолчанию если отсутствуют
    if "mileage_from" not in user_data:
        print(
            "⚠️ DEBUG [handle_price_to_selection] - mileage_from отсутствует, устанавливаем по умолчанию 0"
        )
        user_data["mileage_from"] = 0

    if "mileage_to" not in user_data:
        print(
            "⚠️ DEBUG [handle_price_to_selection] - mileage_to отсутствует, устанавливаем по умолчанию 100000"
        )
        user_data["mileage_to"] = 100000

    manufacturer = user_data["manufacturer"]
    model_group = user_data["model_group"]
    model = user_data["model"]
    trim = user_data["trim"]
    year_from = user_data["year_from"]
    year_to = user_data["year_to"]
    mileage_from = user_data["mileage_from"]
    mileage_to = user_data["mileage_to"]
    selected_color_kr = user_data["color"]
    price_from = user_data.get("price_from")
    price_to = user_data.get("price_to")

    # Преобразование для отображения
    selected_color_ru = (
        "Любой"
        if selected_color_kr == "all"
        else COLOR_TRANSLATIONS.get(selected_color_kr, "Неизвестно")
    )

    price_from_display = (
        "Любая" if price_from is None else f"{price_from // 100} млн вон"
    )

    # Отправляем сообщение о начале поиска
    bot.send_message(
        call.message.chat.id,
        "🔍 Начинаем поиск автомобилей по заданным параметрам. Это может занять некоторое время...",
    )

    # Информация о выбранных параметрах
    bot.send_message(
        call.message.chat.id,
        f"📋 Ваш запрос:\n"
        f"• {manufacturer} {model_group} {model}\n"
        f"• Комплектация: {trim}\n"
        f"• Год выпуска: {year_from}-{year_to}\n"
        f"• Пробег: от {mileage_from} до {mileage_to} км\n"
        f"• Цвет: {selected_color_ru}\n"
        f"• Цена: от {price_from_display} до {price_to_display}",
    )

    # Кнопки после завершения добавления авто
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Добавить новый автомобиль в поиск", callback_data="search_car"
        )
    )
    markup.add(
        types.InlineKeyboardButton("🏠 Вернуться в главное меню", callback_data="start")
    )
    bot.send_message(
        call.message.chat.id,
        "Хотите добавить ещё один автомобиль в поиск или вернуться в главное меню?",
        reply_markup=markup,
    )

    # Сохраняем запрос пользователя
    if user_id not in user_requests:
        user_requests[user_id] = []

    user_requests[user_id].append(
        {
            "manufacturer": manufacturer,
            "model_group": model_group,
            "model": model,
            "trim": trim,
            "year_from": year_from,
            "year_to": year_to,
            "mileage_from": mileage_from,
            "mileage_to": mileage_to,
            "color": selected_color_kr,
            "price_from": price_from,
            "price_to": price_to,
        }
    )

    save_requests(user_requests)

    # Запускаем поиск в отдельном потоке
    threading.Thread(
        target=check_for_new_cars,
        args=(
            call.from_user.id,  # user_id для параметров поиска
            call.message.chat.id,  # chat_id для отправки сообщений
            manufacturer.strip(),
            model_group.strip(),
            model.strip(),
            trim.strip(),
            year_from,
            year_to,
            mileage_from,
            mileage_to,
            "" if selected_color_kr == "all" else selected_color_kr.strip(),
            price_from,
            price_to,
        ),
        daemon=True,
    ).start()


# Запуск бота
if __name__ == "__main__":
    from datetime import datetime

    print("=" * 50)
    print(
        f"🚀 [UniTrading Bot] Запуск бота — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print("📦 Загрузка сохранённых запросов пользователей...")
    load_requests()
    print("✅ Запросы успешно загружены.")
    print("🤖 Бот запущен и ожидает команды...")
    print("=" * 50)
    bot.infinity_polling()
