import asyncio

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import texts_ru as T
from app.bot.states import AdminBindStates
from app.keyboards import admin_reply_kb as ARK
from app.keyboards import user_kb as UK
from app.keyboards.admin_kb import slot_pick
from app.core.config import Settings
from app.repositories.audit import AuditRepository
from app.repositories.user import UserRepository
from app.repositories.vpn_key import VpnKeyRepository
from app.services.container import AppContainer
from app.services.key_service import KeyService, KeyServiceError
from app.services.user_service import UserService


def build_admin_router(settings: Settings) -> Router:
    r = Router(name="admin")
    priv = F.chat.type == "private"
    adm = F.from_user.id == settings.admin_telegram_id
    combo = priv & adm
    acb = F.from_user.id == settings.admin_telegram_id

    def ks(session, container: AppContainer) -> KeyService:
        return KeyService(
            session,
            container.settings,
            container.panel,
            container.regenerate_limiter,
        )

    async def adm_answer_panel(message: Message, container: AppContainer) -> None:
        try:
            inbounds = await container.panel.healthcheck()
            lines = "\n".join(f"• id={x.id} {x.remark or ''} ({x.protocol or '?'})" for x in inbounds[:40])
            await message.answer(f"Панель OK. Inbounds:\n{lines or '—'}", reply_markup=ARK.menu_admin())
        except Exception as e:
            await message.answer(
                f"Ошибка панели: {type(e).__name__}: {e}",
                reply_markup=ARK.menu_admin(),
            )

    async def adm_answer_import(message: Message, container: AppContainer) -> None:
        try:
            async with container.session_factory() as session:
                n = await ks(session, container).import_unbound_from_panel(
                    settings.default_inbound_id, message.from_user.id
                )
                await session.commit()
        except Exception as e:
            await message.answer(f"Импорт: {e}", reply_markup=ARK.menu_admin())
            return
        await message.answer(f"Импортировано новых: {n}", reply_markup=ARK.menu_admin())

    async def adm_answer_unbound(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = VpnKeyRepository(session)
            rows = await repo.list_imported_unbound(limit=15)
            await session.commit()
        if not rows:
            await message.answer("Непривязанных нет.", reply_markup=ARK.menu_admin())
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"#{k.id}", callback_data=f"bk:{k.id}")] for k in rows
            ]
        )
        await message.answer("Выбери ключ (или /admin_bind):", reply_markup=kb)

    async def adm_answer_bind(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = VpnKeyRepository(session)
            rows = await repo.list_imported_unbound(limit=15)
            await session.commit()
        if not rows:
            await message.answer("Нечего привязывать. Сначала импорт.", reply_markup=ARK.menu_admin())
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"#{k.id}", callback_data=f"bk:{k.id}")] for k in rows
            ]
        )
        await message.answer("Ключ для привязки:", reply_markup=kb)

    async def adm_answer_requests(message: Message, container: AppContainer) -> None:
        from app.keyboards.admin_kb import second_key_decision
        from app.repositories.second_key_request import SecondKeyRequestRepository

        async with container.session_factory() as session:
            repo = SecondKeyRequestRepository(session)
            pending = await repo.list_pending()
            await session.commit()
        if not pending:
            await message.answer("Заявок нет.", reply_markup=ARK.menu_admin())
            return
        for p in pending[:5]:
            await message.answer(
                f"Заявка #{p.id} user_id={p.user_id}",
                reply_markup=second_key_decision(p.id),
            )
        await message.answer("Кнопки на сообщениях выше.", reply_markup=ARK.menu_admin())

    async def adm_answer_stats(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            st = await ks(session, container).stats()
            await session.commit()
        await message.answer(
            f"Пользователей: {st['users']}\nАктивных ключей: {st['active_keys']}\n"
            f"Непривязанных импортов: {st['unbound_imported']}",
            reply_markup=ARK.menu_admin(),
        )

    async def adm_answer_server(message: Message) -> None:
        try:
            with open("/host/proc/stat") as f:
                line1 = f.readline().split()
            await asyncio.sleep(0.5)
            with open("/host/proc/stat") as f:
                line2 = f.readline().split()
            idle1 = int(line1[4])
            total1 = sum(int(x) for x in line1[1:])
            idle2 = int(line2[4])
            total2 = sum(int(x) for x in line2[1:])
            cpu = round(100 * (1 - (idle2 - idle1) / (total2 - total1)), 1)

            meminfo = {}
            with open("/host/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":")
                    meminfo[k.strip()] = int(v.strip().split()[0])
            mem_total = meminfo["MemTotal"] / 1024 / 1024
            mem_free = (meminfo["MemFree"] + meminfo.get("Buffers", 0) + meminfo.get("Cached", 0)) / 1024 / 1024
            mem_used = mem_total - mem_free

            with open("/host/proc/uptime") as f:
                uptime_sec = int(float(f.read().split()[0]))
            days = uptime_sec // 86400
            hours = (uptime_sec % 86400) // 3600
            mins = (uptime_sec % 3600) // 60

            xray_conns = 0
            for fname in ["/host/proc/net/tcp", "/host/proc/net/tcp6"]:
                try:
                    with open(fname) as f:
                        for line in f.readlines()[1:]:
                            if line.split()[3] == "01":
                                xray_conns += 1
                except FileNotFoundError:
                    pass

            def read_net():
                with open("/host/proc/net/dev") as f:
                    lines = f.readlines()
                result = {}
                for line in lines[2:]:
                    parts = line.split(":")
                    if len(parts) == 2:
                        iface = parts[0].strip()
                        vals = parts[1].split()
                        result[iface] = (int(vals[0]), int(vals[8]))
                return result

            net1 = read_net()
            await asyncio.sleep(2)
            net2 = read_net()

            net_lines = []
            for iface in ["eth0", "ens3", "ens18", "ens160"]:
                if iface in net1 and iface in net2:
                    rx = (net2[iface][0] - net1[iface][0]) / 2 / 1024 / 1024 * 8
                    tx = (net2[iface][1] - net1[iface][1]) / 2 / 1024 / 1024 * 8
                    net_lines.append(f"  ↓ {rx:.1f} Мбит/с  ↑ {tx:.1f} Мбит/с")

            net_str = "\n".join(net_lines) if net_lines else "  н/д"

            text = (
                f"🖥 <b>Состояние сервера</b>\n\n"
                f"⏱ Uptime: {days}д {hours}ч {mins}м\n"
                f"💻 CPU: {cpu}%\n"
                f"🧠 RAM: {mem_used:.1f} / {mem_total:.1f} ГБ\n"
                f"🔗 Подключений Xray: {xray_conns}\n\n"
                f"📡 Трафик (последние 2с):\n{net_str}"
            )
        except Exception as e:
            text = f"Ошибка получения данных: {e}"
        await message.answer(text, parse_mode="HTML", reply_markup=ARK.menu_admin())

    async def adm_answer_logs(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = AuditRepository(session)
            rows = await repo.recent_audit(limit=20)
            await session.commit()
        lines = [f"{x.created_at.isoformat()[:19]} {x.event_type}" for x in rows]
        text = "\n".join(lines) if lines else "Пусто"
        if len(text) > 3500:
            text = text[:3500] + "…"
        await message.answer(text, reply_markup=ARK.menu_admin())

    async def adm_answer_users(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = UserRepository(session)
            users = await repo.list_users(limit=30)
            await session.commit()
        lines = [f"`{u.telegram_user_id}` @{u.username or '—'} — db {u.id}" for u in users]
        body = "\n".join(lines) if lines else "—"
        await message.answer(f"Пользователи:\n{body}", parse_mode="Markdown", reply_markup=ARK.menu_admin())

    @r.message(Command("admin"), combo)
    async def admin_menu(message: Message, container: AppContainer) -> None:
        await message.answer(
            "Админ-раздел. С параметрами: /admin_add_user, /admin_user, /admin_keys, "
            "/admin_revoke, /admin_disable_key, /admin_import_clients [inbound]",
            reply_markup=ARK.menu_admin(),
        )

    @r.message(F.text == UK.BTN_SECTION_ADMIN, combo)
    async def admin_open_reply(message: Message, container: AppContainer) -> None:
        await message.answer(
            "Администрация. Команды с ID см. /admin",
            reply_markup=ARK.menu_admin(),
        )

    @r.message(F.text == ARK.BTN_ADM_BACK, combo)
    async def admin_reply_back_to_user_menu(message: Message, container: AppContainer) -> None:
        await message.answer(
            "Обычное меню.",
            reply_markup=UK.main_menu(show_admin=True),
        )

    @r.message(F.text == ARK.BTN_ADM_PANEL, combo)
    async def admin_reply_panel(message: Message, container: AppContainer) -> None:
        await adm_answer_panel(message, container)

    @r.message(F.text == ARK.BTN_ADM_IMPORT, combo)
    async def admin_reply_import(message: Message, container: AppContainer) -> None:
        await adm_answer_import(message, container)

    @r.message(F.text == ARK.BTN_ADM_UNBOUND, combo)
    async def admin_reply_unbound(message: Message, container: AppContainer) -> None:
        await adm_answer_unbound(message, container)

    @r.message(F.text == ARK.BTN_ADM_BIND, combo)
    async def admin_reply_bind(message: Message, container: AppContainer) -> None:
        await adm_answer_bind(message, container)

    @r.message(F.text == ARK.BTN_ADM_REQUESTS, combo)
    async def admin_reply_requests(message: Message, container: AppContainer) -> None:
        await adm_answer_requests(message, container)

    @r.message(F.text == ARK.BTN_ADM_STATS, combo)
    async def admin_reply_stats(message: Message, container: AppContainer) -> None:
        await adm_answer_stats(message, container)

    @r.message(F.text == ARK.BTN_ADM_LOGS, combo)
    async def admin_reply_logs(message: Message, container: AppContainer) -> None:
        await adm_answer_logs(message, container)

    @r.message(F.text == ARK.BTN_ADM_SERVER, combo)
    async def admin_reply_server(message: Message) -> None:
        await adm_answer_server(message)

    @r.message(F.text == ARK.BTN_ADM_USERS, combo)
    async def admin_reply_users(message: Message, container: AppContainer) -> None:
        await adm_answer_users(message, container)

    @r.message(Command("admin_panel_check"), combo)
    async def panel_check(message: Message, container: AppContainer) -> None:
        await adm_answer_panel(message, container)

    @r.message(Command("admin_add_user"), combo)
    async def admin_add_user(message: Message, command: CommandObject, container: AppContainer) -> None:
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Использование: /admin_add_user <telegram_id>")
            return
        tid = int(command.args.strip())
        async with container.session_factory() as session:
            us = UserService(session)
            _, created = await us.admin_create_legacy_user(tid, message.from_user.id)
            await session.commit()
        await message.answer("Создан новый пользователь." if created else "Пользователь уже существует.")

    @r.message(Command("admin_users"), combo)
    async def admin_users(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = UserRepository(session)
            users = await repo.list_users(limit=30)
            await session.commit()
        lines = [f"`{u.telegram_user_id}` @{u.username or '—'} — id {u.id}" for u in users]
        await message.answer("Пользователи:\n" + "\n".join(lines), parse_mode="Markdown")

    @r.message(Command("admin_user"), combo)
    async def admin_user(message: Message, command: CommandObject, container: AppContainer) -> None:
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Использование: /admin_user <telegram_id>")
            return
        tid = int(command.args.strip())
        async with container.session_factory() as session:
            repo = UserRepository(session)
            u = await repo.get_by_telegram_id(tid)
            await session.commit()
        if not u:
            await message.answer("Не найден.")
            return
        await message.answer(
            f"User db_id={u.id}\ntelegram=`{u.telegram_user_id}`\n@{u.username or '—'}\n"
            f"{u.first_name or ''} {u.last_name or ''}\nstatus={u.status.value}",
            parse_mode="Markdown",
        )

    @r.message(Command("admin_keys"), combo)
    async def admin_keys(message: Message, command: CommandObject, container: AppContainer) -> None:
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Использование: /admin_keys <telegram_id>")
            return
        tid = int(command.args.strip())
        async with container.session_factory() as session:
            svc = ks(session, container)
            keys = await svc.list_active_keys_for_telegram(tid)
            await session.commit()
        if not keys:
            await message.answer("Нет активных ключей (или пользователь не найден).")
            return
        parts = []
        for k in keys:
            parts.append(
                f"key_id={k.id} slot={k.key_slot_number} inbound={k.inbound_id} "
                f"email=`{k.panel_client_email}` source={k.source.value}"
            )
        await message.answer("\n".join(parts), parse_mode="Markdown")

    @r.message(Command("admin_requests"), combo)
    async def admin_requests(message: Message, container: AppContainer) -> None:
        from app.repositories.second_key_request import SecondKeyRequestRepository

        async with container.session_factory() as session:
            repo = SecondKeyRequestRepository(session)
            pending = await repo.list_pending()
            await session.commit()
        if not pending:
            await message.answer("Нет заявок.")
            return
        lines = [f"#{p.id} user_id={p.user_id}" for p in pending]
        await message.answer("Заявки:\n" + "\n".join(lines))

    @r.message(Command("admin_import_clients"), combo)
    async def admin_import_cmd(message: Message, command: CommandObject, container: AppContainer) -> None:
        inbound_id = settings.default_inbound_id
        if command.args and command.args.strip().isdigit():
            inbound_id = int(command.args.strip())
        try:
            async with container.session_factory() as session:
                n = await ks(session, container).import_unbound_from_panel(
                    inbound_id, message.from_user.id
                )
                await session.commit()
        except Exception as e:
            await message.answer(f"Импорт ошибка: {e}")
            return
        await message.answer(f"Импортировано новых записей: {n} (inbound {inbound_id})")

    @r.message(Command("admin_unbound_clients"), combo)
    async def admin_unbound(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = VpnKeyRepository(session)
            rows = await repo.list_imported_unbound(limit=20)
            await session.commit()
        if not rows:
            await message.answer("Нет непривязанных ключей.")
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"#{k.id} {k.panel_client_email[:20]}", callback_data=f"bk:{k.id}")]
                for k in rows[:12]
            ]
        )
        await message.answer("Выберите ключ для привязки или /admin_bind:", reply_markup=kb)

    @r.message(Command("admin_bind"), combo)
    async def admin_bind_cmd(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = VpnKeyRepository(session)
            rows = await repo.list_imported_unbound(limit=20)
            await session.commit()
        if not rows:
            await message.answer("Нет непривязанных ключей. Сначала /admin_import_clients")
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"#{k.id} {k.panel_client_email[:24]}", callback_data=f"bk:{k.id}")]
                for k in rows[:12]
            ]
        )
        await message.answer("Выберите ключ:", reply_markup=kb)

    @r.callback_query(acb, F.data.startswith("bk:"), F.message.chat.type == "private")
    async def cb_bind_pick(cb: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
        if cb.message is None or cb.data is None:
            return
        try:
            kid = int(cb.data.split(":")[1])
        except (IndexError, ValueError):
            await cb.answer("Ошибка")
            return
        await state.set_state(AdminBindStates.waiting_telegram_id)
        await state.update_data(bind_key_id=kid)
        await cb.answer()
        await cb.message.answer(f"Ключ #{kid}. Введите telegram user id получателя (цифрами).")

    @r.message(StateFilter(AdminBindStates.waiting_telegram_id), combo, F.text)
    async def bind_tg_received(
        message: Message, state: FSMContext, container: AppContainer
    ) -> None:
        data = await state.get_data()
        kid = data.get("bind_key_id")
        if kid is None:
            await state.clear()
            return
        txt = (message.text or "").strip()
        if not txt.isdigit():
            await message.answer("Отправьте только цифры — Telegram user id.")
            return
        target_tg = int(txt)
        await state.update_data(bind_target_tg=target_tg)
        await state.set_state(AdminBindStates.waiting_slot)
        await message.answer(
            f"Telegram `{target_tg}`. Выберите слот для ключа #{kid}:",
            reply_markup=slot_pick(int(kid)),
            parse_mode="Markdown",
        )

    @r.callback_query(
        acb,
        StateFilter(AdminBindStates.waiting_slot),
        F.data.regexp(r"^bs:([12]):(\d+)$"),
        F.message.chat.type == "private",
    )
    async def cb_bind_slot(cb: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
        if cb.message is None or cb.data is None:
            return
        parts = cb.data.split(":")
        slot = int(parts[1])
        kid = int(parts[2])
        data = await state.get_data()
        target_tg = data.get("bind_target_tg")
        if target_tg is None:
            await cb.answer("Сессия устарела")
            await state.clear()
            return
        try:
            async with container.session_factory() as session:
                row = await ks(session, container).bind_unbound_key(
                    kid, int(target_tg), slot, cb.from_user.id
                )
                await session.commit()
        except KeyServiceError as e:
            await cb.answer(str(e)[:200])
            return
        await state.clear()
        await cb.answer("Готово")
        await cb.message.answer(f"Привязано: key #{row.id} → `{target_tg}` слот {slot}", parse_mode="Markdown")

    @r.message(Command("admin_revoke"), combo)
    async def admin_revoke(message: Message, command: CommandObject, container: AppContainer) -> None:
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Использование: /admin_revoke <telegram_id>")
            return
        tid = int(command.args.strip())
        try:
            async with container.session_factory() as session:
                n = await ks(session, container).admin_revoke_all_keys(tid, message.from_user.id)
                await session.commit()
        except KeyServiceError as e:
            await message.answer(str(e))
            return
        await message.answer(f"Отозвано ключей (успешно в панели): {n}")

    @r.message(Command("admin_disable_key"), combo)
    async def admin_disable_key(message: Message, command: CommandObject, container: AppContainer) -> None:
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Использование: /admin_disable_key <key_id>")
            return
        kid = int(command.args.strip())
        try:
            async with container.session_factory() as session:
                await ks(session, container).admin_disable_key(kid, message.from_user.id)
                await session.commit()
        except KeyServiceError as e:
            await message.answer(str(e))
            return
        await message.answer(f"Ключ #{kid} отключён.")

    @r.message(Command("admin_stats"), combo)
    async def admin_stats(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            st = await ks(session, container).stats()
            await session.commit()
        await message.answer(
            f"Пользователей: {st['users']}\nАктивных ключей: {st['active_keys']}\n"
            f"Непривязанных импортов: {st['unbound_imported']}"
        )

    @r.message(Command("admin_logs"), combo)
    async def admin_logs(message: Message, container: AppContainer) -> None:
        async with container.session_factory() as session:
            repo = AuditRepository(session)
            rows = await repo.recent_audit(limit=25)
            await session.commit()
        lines = [f"{x.created_at.isoformat()} {x.event_type} {x.details}" for x in rows]
        text = "\n".join(lines) if lines else "Пусто"
        if len(text) > 3500:
            text = text[:3500] + "…"
        await message.answer(text)

    @r.callback_query(acb, F.data == "adm:panel", F.message.chat.type == "private")
    async def cb_adm_panel(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_panel(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:import", F.message.chat.type == "private")
    async def cb_adm_import(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_import(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:unbound", F.message.chat.type == "private")
    async def cb_adm_unbound(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_unbound(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:bind", F.message.chat.type == "private")
    async def cb_adm_bind(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_bind(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:req", F.message.chat.type == "private")
    async def cb_adm_req(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_requests(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:stats", F.message.chat.type == "private")
    async def cb_adm_stats(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_stats(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data == "adm:logs", F.message.chat.type == "private")
    async def cb_adm_logs(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None:
            return
        await adm_answer_logs(cb.message, container)
        await cb.answer()

    @r.callback_query(acb, F.data.regexp(r"^sok:[ar]:\d+$"), F.message.chat.type == "private")
    async def cb_second_key_decision(cb: CallbackQuery, container: AppContainer) -> None:
        if cb.message is None or cb.data is None:
            return
        parts = cb.data.split(":")
        action = parts[1]
        rid = int(parts[2])

        link: str | None = None
        utg: int
        try:
            async with container.session_factory() as session:
                svc = ks(session, container)
                if action == "a":
                    _, link, utg = await svc.approve_second_key(rid, cb.from_user.id)
                    await session.commit()
                else:
                    utg = await svc.reject_second_key(rid, cb.from_user.id, reason="Отклонено")
                    await session.commit()
        except KeyServiceError as e:
            await cb.answer(str(e)[:100])
            return
        await cb.answer()
        if action == "a":
            await cb.message.answer(f"Одобрено #{rid}")
            sup = container.settings.support_telegram_username
            text = T.second_device_auto_ok(link or "", sup)
            try:
                await cb.message.bot.send_message(utg, text, parse_mode="HTML")
            except Exception:
                async with container.session_factory() as session:
                    ksvc = ks(session, container)
                    await ksvc.enqueue_user_notification(utg, text)
                    await session.commit()
        else:
            await cb.message.answer(f"Отклонено #{rid}")
            sup = container.settings.support_telegram_username
            reject_txt = (
                "Заявка на второе устройство отклонена.\n"
                "Если это ошибка — напиши админу: "
                f"{T.support_mention(sup)}"
            )
            try:
                await cb.message.bot.send_message(utg, reject_txt, parse_mode="HTML")
            except Exception:
                async with container.session_factory() as session:
                    ksvc = ks(session, container)
                    await ksvc.enqueue_user_notification(utg, reject_txt)
                    await session.commit()

    return r
