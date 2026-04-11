"""Reply-клавиатура администратора (только private + ADMIN_TELEGRAM_ID)."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ADM_BACK = "◀️ Меню"
BTN_ADM_PANEL = "Проверка панели"
BTN_ADM_IMPORT = "Импорт клиентов"
BTN_ADM_UNBOUND = "Непривязанные"
BTN_ADM_BIND = "Привязать ключ"
BTN_ADM_REQUESTS = "Заявки 2-го"
BTN_ADM_STATS = "Статистика"
BTN_ADM_LOGS = "Логи"
BTN_ADM_USERS = "Пользователи"


def menu_admin() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADM_PANEL), KeyboardButton(text=BTN_ADM_STATS)],
            [KeyboardButton(text=BTN_ADM_IMPORT), KeyboardButton(text=BTN_ADM_UNBOUND)],
            [KeyboardButton(text=BTN_ADM_BIND), KeyboardButton(text=BTN_ADM_REQUESTS)],
            [KeyboardButton(text=BTN_ADM_LOGS), KeyboardButton(text=BTN_ADM_USERS)],
            [KeyboardButton(text=BTN_ADM_BACK)],
        ],
        resize_keyboard=True,
    )
