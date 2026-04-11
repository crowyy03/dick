"""Пользовательские тексты: простой русский, HTML для Telegram (parse_mode=HTML)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_SUPPORT = "voronin_36"


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def support_mention(username: str | None = None) -> str:
    u = (username or DEFAULT_SUPPORT).lstrip("@")
    return f"@{u}"


def contact_footer(username: str | None = None) -> str:
    return f"\n\nВопросы → {support_mention(username)}"


def contact_short(username: str | None = None) -> str:
    return f"Пиши: {support_mention(username)}"


def format_data_volume(total_bytes: int) -> str:
    n = max(0, int(total_bytes))
    if n < 1024:
        return f"{n} Б"
    if n < 1024**2:
        return f"{n / 1024:.1f} КБ"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} МБ"
    return f"{n / 1024**3:.2f} ГБ"


def start_greeting(first_name: str | None, telegram_id: int, support_user: str | None = None) -> str:
    name = first_name or "друг"
    return (
        f"Привет, {name} 👋 VPN и ключи — через меню ниже (четыре раздела).\n\n"
        f"Твой Telegram ID (если админ спросит): <code>{telegram_id}</code>\n"
        f"Не взлетает — {contact_short(support_user)}."
    )


def submenu_hint_connection() -> str:
    return "<b>Подключение</b> — действия ниже."


def submenu_hint_status() -> str:
    return "<b>Статус</b> — действия ниже."


def submenu_hint_guides() -> str:
    return "<b>Инструкции</b> — действия ниже."


def submenu_hint_support() -> str:
    return "<b>Поддержка</b> — действия ниже."


def back_to_main_ack() -> str:
    return "Главное меню."


def help_text(support_user: str | None = None) -> str:
    su = support_mention(support_user)
    return (
        "🧭 <b>Кратко</b>\n"
        "<b>Подключение</b> — ключи и устройства.\n"
        "<b>Статус</b> — проверки, VPN, трафик, история.\n"
        "<b>Инструкции</b> — как вставить ссылку, что скачать.\n"
        "<b>Поддержка</b> — FAQ и админ.\n\n"
        f"Пиши: {su}"
    )


INSTRUCTION = """📶 <b>Как подключиться</b>

1) Приложение: Amnezia или v2Box (iOS/Android/Windows/Mac).
2) Скопируй <b>ключ</b> (<code>vless://…</code>) из бота.
3) В приложении — «Импорт» / вставка из буфера.
4) Включи VPN. Не ожило — другая сеть или перезапуск приложения.

Одна ссылка ≈ одно устройство; второе — отдельный ключ, если разрешено."""


WHAT_TO_INSTALL = """📲 <b>Что скачать</b>

iOS/Android/ПК — <b>AmneziaVPN</b> или <b>v2Box</b> (магазин приложений или сайт).

Потом — «Как подключиться» и ключ из бота."""


FAQ_TROUBLESHOOTING = """🆘 <b>Не работает</b>

Авиарежим · выкл/вкл VPN · обнови приложение · другая сеть · перезагрузка.

Дальше — напиши админу."""


def faq_full(support_user: str | None = None) -> str:
    return FAQ_TROUBLESHOOTING + contact_footer(support_user)


def report_problem_prompt(support_user: str | None = None) -> str:
    return (
        "📨 <b>Проблема</b>\n"
        "Одним сообщением: что не так. Передам админу.\n"
        f"Или: {support_mention(support_user)}"
    )


def format_keys_empty(support_user: str | None = None) -> str:
    return (
        "Подключений в боте <b>нет</b>. Новый — «Получить доступ». "
        "Старый доступ «вручную» — напиши админу для привязки."
        + contact_footer(support_user)
    )


def _date_ru(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y")


def _datetime_ru_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def format_activity_line(
    panel_last_seen_utc: datetime | None,
    traffic_last_seen_utc: datetime | None,
    online: bool | None,
) -> str | None:
    """Строка для пользователя; если панель ничего не отдала — None."""
    candidates = [x for x in (panel_last_seen_utc, traffic_last_seen_utc) if x is not None]
    best = max(candidates, key=lambda x: x.timestamp()) if candidates else None
    parts: list[str] = []
    if best is not None:
        parts.append(f"last: <b>{html_escape(_datetime_ru_utc(best))}</b>")
    if online is True:
        parts.append("панель: online")
    elif online is False:
        parts.append("панель: не online")
    if not parts:
        return None
    return " ".join(parts) + "."


def format_my_keys_block(
    *,
    keys: list[Any],
    lines_per_key: list[str],
    second_slot_empty: bool,
    support_user: str | None = None,
) -> str:
    header = "🔑 <b>Подключения</b>\n\n"
    body = "\n\n".join(lines_per_key)
    extra = ""
    if second_slot_empty and len(keys) >= 1:
        extra = "\n\nВторой слот свободен — «Второе устройство», если можно."
    two_hint = ""
    if len(keys) >= 2:
        two_hint = "\n\nДва ключа — максимум."
    return (
        header
        + body
        + extra
        + two_hint
        + "\n\n<i>Данные с панели, не твой Wi‑Fi.</i>"
        + contact_footer(support_user)
    )


def human_device_title(slot_number: int) -> str:
    if slot_number == 1:
        return "Основное устройство"
    if slot_number == 2:
        return "Второе устройство"
    return f"Устройство {slot_number}"


def regen_device_button_label(slot_number: int) -> str:
    if slot_number == 1:
        return "Первое устройство"
    if slot_number == 2:
        return "Второе устройство"
    return f"Устройство {slot_number}"


def line_key_human(
    *,
    slot_number: int,
    created_at: datetime,
    origin_human: str,
    panel_line: str | None,
    traffic_line: str | None,
    activity_line: str | None = None,
) -> str:
    title = human_device_title(slot_number)
    parts = [
        f"<b>{html_escape(title)}</b>",
        f"• с {_date_ru(created_at)} · {origin_human}",
    ]
    if traffic_line:
        parts.append(f"• {traffic_line}")
    if panel_line:
        parts.append(f"• {panel_line}")
    if activity_line:
        parts.append(f"• {activity_line}")
    return "\n".join(parts)


def origin_human_from_key(key: Any) -> str:
    from app.models.vpn_key import VpnKeySource

    if key.source == VpnKeySource.imported:
        return "импорт"
    return "бот"


def after_first_key(vless_uri: str, support_user: str | None = None) -> str:
    safe = html_escape(vless_uri)
    su = support_mention(support_user)
    return (
        "Готово 🎉 Ключ ниже — это одна строка <code>vless://…</code>.\n\n"
        f"<code>{safe}</code>\n\n"
        "Скопируй целиком → в Amnezia или v2Box «Импорт из буфера» → включи VPN.\n"
        f"Не ожило — раздел «Поддержка» или {su}.\n"
        "Ещё шаги — раздел <b>Инструкции</b>."
        + contact_footer(support_user)
    )


def after_regenerate(vless_uri: str, support_user: str | None = None) -> str:
    safe = html_escape(vless_uri)
    return (
        "Новый ключ 🔁 Старый в панели снят — импортируй эту строку заново:\n\n"
        f"<code>{safe}</code>\n\n"
        "В приложении удали старый профиль или обнови импорт."
        + contact_footer(support_user)
    )


def second_device_auto_ok(vless_uri: str, support_user: str | None = None) -> str:
    safe = html_escape(vless_uri)
    return (
        "Второе устройство 📲 Отдельный ключ (одна строка <code>vless://…</code>):\n\n"
        f"<code>{safe}</code>\n\n"
        "Импорт только на этом устройстве; первый ключ не трогай."
        + contact_footer(support_user)
    )


def second_device_pending() -> str:
    return "Заявка у админа ✉️ Ждём ответа."


def second_device_pending_footer(support_user: str | None = None) -> str:
    return "\n\n" + contact_short(support_user)


def second_device_already_pending() -> str:
    return "Заявка уже в очереди."


def second_device_limit_reached(support_user: str | None = None) -> str:
    return "Уже <b>два</b> ключа — лимит. Исключения — через админа." + contact_footer(support_user)


def access_check_panel_down(support_user: str | None = None) -> str:
    return "⚠️ Панель не отвечает — попробуй позже." + contact_footer(support_user)


def vpn_status_no_keys(support_user: str | None = None) -> str:
    return "📡 Нет ключей в боте." + contact_footer(support_user)


def vpn_status_panel_down(support_user: str | None = None) -> str:
    return "📡 Панель недоступна — статус неизвестен." + contact_footer(support_user)


def vpn_status_message(body: str, support_user: str | None = None) -> str:
    return (
        f"📡 <b>Статус VPN</b>\n\n{body}\n\n"
        "<i>Только данные панели; «online» ≠ интернет у тебя дома.</i>"
        + contact_footer(support_user)
    )


def traffic_totals_no_keys(support_user: str | None = None) -> str:
    return "📊 Нет активных ключей — считать нечего." + contact_footer(support_user)


def traffic_totals_panel_down(support_user: str | None = None) -> str:
    return "📊 Панель не ответила — трафик неизвестен." + contact_footer(support_user)


def traffic_totals_message(body: str, support_user: str | None = None) -> str:
    return (
        f"📊 <b>Трафик (панель)</b>\n\n{body}\n\n"
        "<i>↑+↓ накопительно, как отдаёт API 3x-ui (не «сброс раз в месяц», если панель сама не сбрасывает).</i>"
        + contact_footer(support_user)
    )


_HISTORY_LABELS: dict[str, str] = {
    "user_created": "Зашёл в бота (профиль создан)",
    "key_issued_first": "Выдан первый ключ",
    "key_regenerated": "Ключ обновили (новая ссылка)",
    "second_key_requested": "Запросили второе устройство (ожидание админа)",
    "key_issued_second": "Выдан ключ для второго устройства",
    "import_bound": "Привязали существующий ключ к аккаунту",
    "access_revoked_all": "Админ отключил все подключения",
    "access_key_revoked": "Админ отключил доступ к ключу",
}


def _history_suffix(event_type: str, details: dict[str, Any]) -> str:
    if event_type in ("key_issued_first", "key_issued_second", "key_regenerated", "access_key_revoked"):
        slot = details.get("slot")
        if slot is not None:
            return f" (устройство {slot})"
    if event_type == "access_revoked_all":
        n = details.get("count")
        if n is not None:
            return f" ({n} шт.)"
    return ""


def format_user_history(events: list[Any], support_user: str | None = None) -> str:
    """``events`` — записи ``AuditLog`` в хронологическом порядке (старые → новые)."""
    if not events:
        return "📜 Пока пусто — события появятся после действий в боте." + contact_footer(support_user)
    lines: list[str] = []
    for e in events:
        et = str(e.event_type)
        label = _HISTORY_LABELS.get(et, f"Событие: {html_escape(et)}")
        det = e.details if isinstance(e.details, dict) else {}
        suf = _history_suffix(et, det)
        lines.append(f"• {_datetime_ru_utc(e.created_at)} — {label}{suf}")
    body = "\n".join(lines)
    return f"📜 <b>История</b>\n\n{body}\n\n<i>Только события из бота.</i>" + contact_footer(support_user)


def write_admin_prompt(support_user: str | None = None) -> str:
    return f"✉️ Напиши: {support_mention(support_user)}"


def access_check_ok(summary_lines: list[str], support_user: str | None = None) -> str:
    body = "\n".join(f"• {html_escape(s)}" for s in summary_lines)
    return (
        f"🔎 <b>Проверка</b>\n\n{body}\n\n<i>Только сервер, не твой Wi‑Fi.</i>"
        + contact_footer(support_user)
    )


class UserFacing:
    ALREADY_HAS_ACCESS = "У тебя уже есть доступ — загляни в «Мои подключения»."
    PANEL_ISSUE_FIRST = (
        "Не смог выдать доступ: сервер с ключами сейчас капризничает. "
        "Уже передал сигнал админу — напиши ему, если срочно."
    )
    PANEL_ISSUE_FIRST_UNVERIFIED = (
        "Панель не подтвердила ключ или не получилось его собрать — доступ не выдан. "
        "Напиши админу, при необходимости повторим."
    )
    PANEL_REVOKE_OLD = (
        "Не получилось снять старый доступ перед обновлением. "
        "Без паники — напиши админу, разрулим вручную."
    )
    PANEL_NEW_AFTER_REGEN = (
        "Старый сняли, а новый не завёлся. Так бывает. Напиши админу — починим."
    )
    USER_NOT_FOUND = "Что-то пошло не так с аккаунтом. Напиши админу."
    KEY_NOT_FOUND = "Такого подключения не нашёл — возможно, уже отключили."
    PANEL_SECOND = "Второе устройство сейчас не завести — сервер отвертелся. Напиши админу."
    NEED_FIRST = "Сначала нужно первое подключение — кнопка «Получить доступ»."
    CREATE_USER_FAIL = "Не смог сохранить профиль. Попробуй ещё раз или напиши админу."


def traffic_line_from_server(total_bytes: int) -> str:
    vol = format_data_volume(total_bytes)
    return f"трафик <b>{html_escape(vol)}</b> (↑+↓)"


def traffic_line_unavailable() -> str:
    return "трафик: панель не отдала"


def traffic_line_not_in_report() -> str:
    return "трафик: нет в отчёте"


def panel_client_missing() -> str:
    return "⚠️ ключа нет в панели"


def panel_client_disabled() -> str:
    return "⚠️ в панели выключено"


def panel_client_ok() -> str:
    return "в панели ок"


def regen_pick_prompt() -> str:
    return "Какое устройство обновить?"


def regen_no_keys(support_user: str | None = None) -> str:
    return "Нечего обновлять — нет ключей." + contact_footer(support_user)


def generic_try_later(support_user: str | None = None) -> str:
    return "Ошибка на нашей стороне — позже или админ." + contact_footer(support_user)
