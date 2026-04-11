"""Reply-клавиатура: главное меню (разделы) и подменю."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

# --- Главный экран (2×2) ---
BTN_SECTION_CONNECTION = "Подключение"
BTN_SECTION_STATUS = "Статус"
BTN_SECTION_GUIDES = "Инструкции"
BTN_SECTION_SUPPORT = "Поддержка"
BTN_SECTION_ADMIN = "Администрация"

# --- Назад ---
BTN_BACK_MAIN = "◀️ Главное меню"

# --- Листья (те же тексты, что в хендлерах) ---
BTN_GET_ACCESS = "Получить доступ"
BTN_MY_KEYS = "Мои подключения"
BTN_REGEN = "Обновить доступ"
BTN_SECOND_DEVICE = "Второе устройство"
BTN_HOW_TO = "Как подключиться"
BTN_HELP = "Помощь"
BTN_CHECK_ACCESS = "Проверить доступ"
BTN_VPN_STATUS = "Статус VPN"
BTN_WHAT_INSTALL = "Что скачать"
BTN_HISTORY = "Моя история"
BTN_TRAFFIC_TOTAL = "Трафик всего"
BTN_FAQ = "Не работает"
BTN_REPORT = "Сообщить о проблеме"
BTN_WRITE_ADMIN = "Написать админу"


def main_menu(*, show_admin: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text=BTN_SECTION_CONNECTION),
            KeyboardButton(text=BTN_SECTION_STATUS),
        ],
        [
            KeyboardButton(text=BTN_SECTION_GUIDES),
            KeyboardButton(text=BTN_SECTION_SUPPORT),
        ],
    ]
    if show_admin:
        rows.append([KeyboardButton(text=BTN_SECTION_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_connection() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_GET_ACCESS), KeyboardButton(text=BTN_MY_KEYS)],
            [KeyboardButton(text=BTN_REGEN), KeyboardButton(text=BTN_SECOND_DEVICE)],
            [KeyboardButton(text=BTN_BACK_MAIN)],
        ],
        resize_keyboard=True,
    )


def menu_status() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHECK_ACCESS), KeyboardButton(text=BTN_VPN_STATUS)],
            [KeyboardButton(text=BTN_HISTORY), KeyboardButton(text=BTN_TRAFFIC_TOTAL)],
            [KeyboardButton(text=BTN_BACK_MAIN)],
        ],
        resize_keyboard=True,
    )


def menu_guides() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HOW_TO), KeyboardButton(text=BTN_WHAT_INSTALL)],
            [KeyboardButton(text=BTN_BACK_MAIN)],
        ],
        resize_keyboard=True,
    )


def menu_support() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_HELP), KeyboardButton(text=BTN_FAQ)],
            [KeyboardButton(text=BTN_REPORT), KeyboardButton(text=BTN_WRITE_ADMIN)],
            [KeyboardButton(text=BTN_BACK_MAIN)],
        ],
        resize_keyboard=True,
    )
