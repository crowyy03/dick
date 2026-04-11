from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверка панели", callback_data="adm:panel")],
            [InlineKeyboardButton(text="Импорт клиентов", callback_data="adm:import")],
            [InlineKeyboardButton(text="Непривязанные ключи", callback_data="adm:unbound")],
            [InlineKeyboardButton(text="Привязать ключ", callback_data="adm:bind")],
            [InlineKeyboardButton(text="Заявки 2-го ключа", callback_data="adm:req")],
            [InlineKeyboardButton(text="Статистика", callback_data="adm:stats")],
            [InlineKeyboardButton(text="Логи", callback_data="adm:logs")],
        ]
    )


def second_key_decision(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"sok:a:{request_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"sok:r:{request_id}"),
            ]
        ]
    )


def unbound_key_pick(key_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Ключ #{key_id}", callback_data=f"bk:{key_id}")],
        ]
    )


def slot_pick(key_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Слот 1", callback_data=f"bs:1:{key_id}"),
                InlineKeyboardButton(text="Слот 2", callback_data=f"bs:2:{key_id}"),
            ],
        ]
    )
