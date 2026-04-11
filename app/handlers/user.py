from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User as TgUser,
)

from app.bot import texts_ru as T
from app.bot.notify import safe_send_admin
from app.keyboards import user_kb as UK
from app.keyboards.admin_kb import second_key_decision
from app.services.container import AppContainer
from app.services.key_service import KeyService, KeyServiceError
from app.services.user_service import UserService

PARSE_HTML = "HTML"


async def _sync_tg_profile(session, fu: TgUser) -> None:
    """Обновить имя/username в БД до выдачи ключа — remark в панели берётся из профиля."""
    us = UserService(session)
    await us.register_or_update_profile(
        telegram_user_id=fu.id,
        username=fu.username,
        first_name=fu.first_name,
        last_name=fu.last_name,
    )


def _main_kb(message: Message, container: AppContainer):
    """Главное меню; у ADMIN_TELEGRAM_ID — доп. строка «Администрация»."""
    if message.from_user is None:
        return UK.main_menu(show_admin=False)
    return UK.main_menu(
        show_admin=message.from_user.id == container.settings.admin_telegram_id
    )


def _admin_url(username: str) -> str:
    u = username.lstrip("@")
    return f"https://t.me/{u}"


def build_user_router() -> Router:
    r = Router(name="user")

    @r.message(CommandStart())
    async def cmd_start(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        tg = message.from_user.id
        sup = container.settings.support_telegram_username
        async with container.session_factory() as session:
            us = UserService(session)
            user, created = await us.register_or_update_profile(
                telegram_user_id=tg,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            await session.commit()

        async with container.session_factory() as session:
            us2 = UserService(session)
            await us2.deliver_pending_notifications(message.bot, tg)
            await session.commit()

        if created:
            await safe_send_admin(
                message.bot,
                container.settings.admin_telegram_id,
                f"Новый пользователь: `{tg}` (@{message.from_user.username or '—'})",
            )

        text = T.start_greeting(message.from_user.first_name, tg, sup)
        await message.answer(text, reply_markup=_main_kb(message, container), parse_mode=PARSE_HTML)

    @r.message(F.text == UK.BTN_BACK_MAIN)
    async def back_to_main(message: Message, container: AppContainer) -> None:
        await message.answer(
            T.back_to_main_ack(),
            reply_markup=_main_kb(message, container),
            parse_mode=PARSE_HTML,
        )

    @r.message(F.text == UK.BTN_SECTION_CONNECTION)
    async def open_connection(message: Message) -> None:
        await message.answer(
            T.submenu_hint_connection(),
            reply_markup=UK.menu_connection(),
            parse_mode=PARSE_HTML,
        )

    @r.message(F.text == UK.BTN_SECTION_STATUS)
    async def open_status(message: Message) -> None:
        await message.answer(
            T.submenu_hint_status(),
            reply_markup=UK.menu_status(),
            parse_mode=PARSE_HTML,
        )

    @r.message(F.text == UK.BTN_SECTION_GUIDES)
    async def open_guides(message: Message) -> None:
        await message.answer(
            T.submenu_hint_guides(),
            reply_markup=UK.menu_guides(),
            parse_mode=PARSE_HTML,
        )

    @r.message(F.text == UK.BTN_SECTION_SUPPORT)
    async def open_support(message: Message) -> None:
        await message.answer(
            T.submenu_hint_support(),
            reply_markup=UK.menu_support(),
            parse_mode=PARSE_HTML,
        )

    @r.message(F.text == UK.BTN_HELP)
    @r.message(Command("help"))
    async def cmd_help(message: Message, container: AppContainer) -> None:
        sup = container.settings.support_telegram_username
        await message.answer(
            T.help_text(sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_HOW_TO)
    async def instruction(message: Message) -> None:
        await message.answer(
            T.INSTRUCTION,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_WHAT_INSTALL)
    async def what_to_install(message: Message, container: AppContainer) -> None:
        sup = container.settings.support_telegram_username
        text = T.WHAT_TO_INSTALL + T.contact_footer(sup)
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_FAQ)
    async def faq_handler(message: Message, container: AppContainer) -> None:
        sup = container.settings.support_telegram_username
        await message.answer(
            T.faq_full(sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_REPORT)
    async def report_problem(message: Message, container: AppContainer) -> None:
        sup = container.settings.support_telegram_username
        await message.answer(
            T.report_problem_prompt(sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_CHECK_ACCESS)
    async def check_access(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            text = await ks.compose_access_check_message(message.from_user.id)
            await session.commit()
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_VPN_STATUS)
    async def vpn_status(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            text = await ks.compose_vpn_status_message(message.from_user.id)
            await session.commit()
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_HISTORY)
    async def user_history(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            text = await ks.compose_user_history_message(message.from_user.id)
            await session.commit()
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_TRAFFIC_TOTAL)
    async def traffic_totals(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            text = await ks.compose_traffic_totals_message(message.from_user.id)
            await session.commit()
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_WRITE_ADMIN)
    async def write_admin(message: Message, container: AppContainer) -> None:
        sup = container.settings.support_telegram_username
        await message.answer(
            T.write_admin_prompt(sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_MY_KEYS)
    async def my_keys(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            text = await ks.compose_my_keys_message(message.from_user.id)
            await session.commit()
        await message.answer(
            text,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )

    @r.message(F.text == UK.BTN_GET_ACCESS)
    async def get_key(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        tg = message.from_user.id
        sup = container.settings.support_telegram_username
        try:
            async with container.session_factory() as session:
                await _sync_tg_profile(session, message.from_user)
                ks = KeyService(
                    session,
                    container.settings,
                    container.panel,
                    container.regenerate_limiter,
                )
                _, link = await ks.issue_first_key(tg)
                await session.commit()
        except KeyServiceError as e:
            await message.answer(
                str(e),
                parse_mode=PARSE_HTML,
                reply_markup=_main_kb(message, container),
            )
            if e.notify_admin:
                await safe_send_admin(
                    message.bot,
                    container.settings.admin_telegram_id,
                    f"Выдача ключа не завершена: `{tg}` — {e!s}",
                )
            return
        except Exception:
            await message.answer(
                T.generic_try_later(sup),
                parse_mode=PARSE_HTML,
                reply_markup=_main_kb(message, container),
            )
            await safe_send_admin(
                message.bot,
                container.settings.admin_telegram_id,
                f"Ошибка выдачи ключа пользователю `{tg}`",
            )
            return

        await message.answer(
            T.after_first_key(link, sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )
        await safe_send_admin(
            message.bot,
            container.settings.admin_telegram_id,
            f"Автовыдача первого ключа: `{tg}`",
        )

    async def _do_regen(
        message: Message,
        container: AppContainer,
        key_id: int,
        *,
        profile: TgUser | None = None,
    ) -> None:
        fu = profile or message.from_user
        if fu is None:
            return
        tg = fu.id
        sup = container.settings.support_telegram_username
        try:
            async with container.session_factory() as session:
                await _sync_tg_profile(session, fu)
                ks = KeyService(
                    session,
                    container.settings,
                    container.panel,
                    container.regenerate_limiter,
                )
                _, link = await ks.regenerate_key(tg, key_id)
                await session.commit()
        except KeyServiceError as e:
            await message.answer(
                str(e),
                parse_mode=PARSE_HTML,
                reply_markup=_main_kb(message, container),
            )
            if e.notify_admin:
                await safe_send_admin(
                    message.bot,
                    container.settings.admin_telegram_id,
                    f"Регенерация не завершена: `{tg}` key_id={key_id} — {e!s}",
                )
            return
        await message.answer(
            T.after_regenerate(link, sup),
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )
        await safe_send_admin(
            message.bot,
            container.settings.admin_telegram_id,
            f"Регенерация ключа пользователем `{tg}`, key_id={key_id}",
        )

    @r.message(F.text == UK.BTN_REGEN)
    async def regen_menu(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        sup = container.settings.support_telegram_username
        async with container.session_factory() as session:
            ks = KeyService(
                session,
                container.settings,
                container.panel,
                container.regenerate_limiter,
            )
            keys = await ks.list_active_keys_for_telegram(message.from_user.id)
            await session.commit()
        if not keys:
            await message.answer(
                T.regen_no_keys(sup),
                parse_mode=PARSE_HTML,
                reply_markup=_main_kb(message, container),
            )
            return
        if len(keys) == 1:
            await _do_regen(message, container, keys[0].id)
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=T.regen_device_button_label(k.key_slot_number),
                        callback_data=f"urg:{k.id}",
                    )
                ]
                for k in keys
            ]
        )
        await message.answer(
            T.regen_pick_prompt(),
            parse_mode=PARSE_HTML,
            reply_markup=kb,
        )

    @r.callback_query(F.data.startswith("urg:"))
    async def regen_pick(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.from_user is None or cb.message is None:
            return
        try:
            kid = int(cb.data.split(":")[1])
        except (IndexError, ValueError):
            await cb.answer("Некорректные данные")
            return
        await cb.answer()
        await _do_regen(cb.message, container, kid, profile=cb.from_user)

    @r.message(F.text == UK.BTN_SECOND_DEVICE)
    async def second_dev(message: Message, container: AppContainer) -> None:
        if message.from_user is None:
            return
        tg = message.from_user.id
        sup = container.settings.support_telegram_username
        try:
            async with container.session_factory() as session:
                await _sync_tg_profile(session, message.from_user)
                ks = KeyService(
                    session,
                    container.settings,
                    container.panel,
                    container.regenerate_limiter,
                )
                msg, req_id, auto_issued = await ks.request_second_device(tg)
                await session.commit()
        except KeyServiceError as e:
            await message.answer(
                str(e),
                parse_mode=PARSE_HTML,
                reply_markup=_main_kb(message, container),
            )
            if e.notify_admin:
                await safe_send_admin(
                    message.bot,
                    container.settings.admin_telegram_id,
                    f"Второе устройство: `{tg}` — {e!s}",
                )
            return
        out = msg
        if req_id is not None:
            out = msg + T.second_device_pending_footer(sup)
        await message.answer(
            out,
            parse_mode=PARSE_HTML,
            reply_markup=_main_kb(message, container),
        )
        if req_id is not None:
            await safe_send_admin(
                message.bot,
                container.settings.admin_telegram_id,
                f"Заявка на второй ключ #{req_id} от `{tg}`",
                reply_markup=second_key_decision(req_id),
                parse_mode="Markdown",
            )
        elif auto_issued:
            await safe_send_admin(
                message.bot,
                container.settings.admin_telegram_id,
                f"Автовыдача второго ключа пользователю `{tg}`",
                parse_mode="Markdown",
            )

    return r
