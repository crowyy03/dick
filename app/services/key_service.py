from __future__ import annotations

import secrets
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts_ru as user_txt
from app.core.config import SecondKeyMode, Settings
from app.integrations.three_x_ui.errors import PanelError
from app.integrations.three_x_ui.protocol import (
    ClientTrafficRow,
    CreatedClient,
    PanelClientRow,
    VpnPanelClient,
)
from app.models.regeneration import RegenerationInitiator
from app.models.second_key_request import SecondKeyRequestStatus
from app.models.user import User
from app.models.vpn_key import VpnKey, VpnKeySource, VpnKeyStatus
from app.repositories.audit import AuditRepository
from app.repositories.pending_notification import PendingNotificationRepository
from app.repositories.second_key_request import SecondKeyRequestRepository
from app.repositories.user import UserRepository
from app.repositories.vpn_key import VpnKeyRepository
from app.services.rate_limit import RegenerateRateLimiter

class KeyServiceError(Exception):
    def __init__(self, message: str, *, notify_admin: bool = False) -> None:
        super().__init__(message)
        self.notify_admin = bool(notify_admin)


class KeyService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        panel: VpnPanelClient,
        regenerate_limiter: RegenerateRateLimiter,
    ) -> None:
        self._session = session
        self._settings = settings
        self._panel = panel
        self._limiter = regenerate_limiter
        self._users = UserRepository(session)
        self._keys = VpnKeyRepository(session)
        self._req = SecondKeyRequestRepository(session)
        self._audit = AuditRepository(session)
        self._pending = PendingNotificationRepository(session)

    def _user_msg(self, text: str, *, with_support_footer: bool = True) -> str:
        text = text.rstrip()
        if with_support_footer:
            return text + user_txt.contact_footer(self._settings.support_telegram_username)
        return text

    def _email_for_slot(self, telegram_user_id: int, slot: int) -> str:
        return f"tg{telegram_user_id}_s{slot}_{secrets.token_hex(4)}"

    def _panel_client_remark(self, user: User) -> str:
        """Подпись клиента в 3x-ui (поле remark): имя из Telegram, иначе @username, иначе tg:id."""
        tid = user.telegram_user_id
        parts: list[str] = []
        if user.first_name:
            t = user.first_name.replace("\n", " ").replace("\r", "").strip()
            if t:
                parts.append(t)
        if user.last_name:
            t = user.last_name.replace("\n", " ").replace("\r", "").strip()
            if t:
                parts.append(t)
        label = " ".join(parts).strip()
        if not label and user.username:
            u = user.username.lstrip("@")
            if u:
                label = f"@{u}"
        if not label:
            return f"tg:{tid}"
        return f"{label[:180]} · tg:{tid}"

    def _inbound_for_slot(self, slot: int) -> int:
        if slot == 2 and self._settings.second_device_inbound_id is not None:
            return self._settings.second_device_inbound_id
        return self._settings.default_inbound_id

    async def _finalize_panel_issued_client(
        self,
        inbound_id: int,
        created: CreatedClient,
        *,
        remark_for_link: str,
        fail_user_message: str,
        audit_event: str,
        telegram_user_id: int | None,
    ) -> str:
        """Проверка клиента в панели + vless://; при ошибке — откат delClient в панели."""
        if not created.uuid:
            try:
                await self._panel.delete_client_by_email(inbound_id, created.email)
            except PanelError:
                pass
            await self._audit.write_audit(
                actor_type="system",
                actor_telegram_id=None,
                event_type=audit_event,
                details={"error": "missing uuid after create", "email": created.email[:120]},
            )
            raise KeyServiceError(
                self._user_msg(fail_user_message),
                notify_admin=True,
            )

        try:
            await self._panel.verify_client_created(inbound_id, created.email, created.uuid)
            inbound_row = await self._panel.fetch_inbound_raw(inbound_id)
            flow = (self._settings.panel_client_flow or "").strip() or None
            return self._panel.build_vless_share_link(
                inbound_row,
                client_uuid=created.uuid,
                client_flow=flow,
                remark=remark_for_link,
            )
        except PanelError as e:
            try:
                await self._panel.delete_client_by_email(inbound_id, created.email)
            except PanelError:
                pass
            await self._audit.write_audit(
                actor_type="system",
                actor_telegram_id=None,
                event_type=audit_event,
                details={
                    "error": str(e)[:500],
                    "email": created.email[:120],
                    "telegram_user_id": telegram_user_id,
                },
            )
            raise KeyServiceError(
                self._user_msg(fail_user_message),
                notify_admin=True,
            ) from e

    async def ensure_user_exists(self, telegram_user_id: int) -> User:
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if user:
            return user
        async with self._session.begin_nested():
            try:
                return await self._users.create(telegram_user_id=telegram_user_id)
            except IntegrityError:
                pass
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if user is None:
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.CREATE_USER_FAIL))
        return user

    async def list_active_keys_for_telegram(self, telegram_user_id: int) -> list[VpnKey]:
        user = await self._users.get_by_telegram_id(telegram_user_id)
        if not user:
            return []
        return await self._keys.list_active_for_user(user.id)

    async def issue_first_key(
        self,
        telegram_user_id: int,
    ) -> tuple[VpnKey, str]:
        user = await self._users.get_by_telegram_id_for_update(telegram_user_id)
        if user is None:
            user = await self.ensure_user_exists(telegram_user_id)
            user = await self._users.get_by_telegram_id_for_update(telegram_user_id)
        assert user is not None

        if await self._keys.count_active_for_user(user.id) >= 1:
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.ALREADY_HAS_ACCESS))

        inbound_id = self._inbound_for_slot(1)
        email = self._email_for_slot(telegram_user_id, 1)
        remark = self._panel_client_remark(user)
        try:
            created = await self._panel.create_client(
                inbound_id,
                email,
                remark=remark,
                telegram_user_id=user.telegram_user_id,
            )
        except PanelError as e:
            await self._audit.write_audit(
                actor_type="system",
                actor_telegram_id=None,
                event_type="panel_error_issue_first",
                details={"error": str(e)[:500], "telegram_user_id": telegram_user_id},
            )
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.PANEL_ISSUE_FIRST)) from e

        direct_link = await self._finalize_panel_issued_client(
            inbound_id,
            created,
            remark_for_link=remark,
            fail_user_message=user_txt.UserFacing.PANEL_ISSUE_FIRST_UNVERIFIED,
            audit_event="panel_verify_failed_issue_first",
            telegram_user_id=telegram_user_id,
        )

        key = await self._keys.add(
            user_id=user.id,
            inbound_id=inbound_id,
            panel_client_email=created.email,
            panel_client_uuid=created.uuid,
            panel_remark=None,
            panel_sub_id=created.sub_id,
            key_slot_number=1,
            source=VpnKeySource.issued_by_bot,
            status=VpnKeyStatus.active,
        )
        await self._audit.write_audit(
            actor_type="user",
            actor_telegram_id=telegram_user_id,
            event_type="key_issued_first",
            entity_type="vpn_key",
            entity_id=str(key.id),
            details={"slot": 1, "source": "issued_by_bot"},
        )
        return key, direct_link

    async def regenerate_key(
        self,
        telegram_user_id: int,
        key_id: int,
    ) -> tuple[VpnKey, str]:
        ok, msg = self._limiter.check(
            telegram_user_id,
            self._settings.regenerate_cooldown_sec,
            self._settings.regenerate_max_per_day,
        )
        if not ok:
            await self._audit.write_audit(
                actor_type="user",
                actor_telegram_id=telegram_user_id,
                event_type="regenerate_rate_limited",
                details={"message": msg or ""},
            )
            raise KeyServiceError(
                self._user_msg(msg or "Пожалуйста, чуть-чуть подожди.")
            )

        user = await self._users.get_by_telegram_id_for_update(telegram_user_id)
        if user is None:
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.USER_NOT_FOUND))
        old = await self._keys.get_for_update(key_id)
        if old is None or old.user_id != user.id or old.status != VpnKeyStatus.active:
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.KEY_NOT_FOUND))

        inbound_id = old.inbound_id
        remark = self._panel_client_remark(user)
        new_email = self._email_for_slot(telegram_user_id, old.key_slot_number)
        try:
            created = await self._panel.create_client(
                inbound_id,
                new_email,
                remark=remark,
                telegram_user_id=user.telegram_user_id,
            )
        except PanelError as e:
            await self._audit.write_audit(
                actor_type="system",
                actor_telegram_id=telegram_user_id,
                event_type="panel_error_regenerate_create_failed",
                details={"error": str(e)[:500]},
            )
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.PANEL_NEW_AFTER_REGEN)) from e

        direct_link = await self._finalize_panel_issued_client(
            inbound_id,
            created,
            remark_for_link=remark,
            fail_user_message=user_txt.UserFacing.PANEL_NEW_AFTER_REGEN,
            audit_event="panel_verify_failed_regenerate",
            telegram_user_id=telegram_user_id,
        )

        try:
            await self._panel.delete_client_by_email(inbound_id, old.panel_client_email)
        except PanelError as e:
            try:
                await self._panel.delete_client_by_email(inbound_id, created.email)
            except PanelError:
                pass
            await self._audit.write_audit(
                actor_type="user",
                actor_telegram_id=telegram_user_id,
                event_type="panel_error_regenerate",
                entity_type="vpn_key",
                entity_id=str(key_id),
                details={"error": str(e)[:500], "rolled_back_new": True},
            )
            raise KeyServiceError(
                self._user_msg(user_txt.UserFacing.PANEL_REVOKE_OLD),
                notify_admin=True,
            ) from e

        await self._keys.revoke(old)

        new_key = await self._keys.add(
            user_id=user.id,
            inbound_id=inbound_id,
            panel_client_email=created.email,
            panel_client_uuid=created.uuid,
            panel_remark=None,
            panel_sub_id=created.sub_id,
            key_slot_number=old.key_slot_number,
            source=VpnKeySource.issued_by_bot,
            status=VpnKeyStatus.active,
        )
        await self._audit.write_regeneration_history(
            old_key_id=old.id,
            new_key_id=new_key.id,
            initiator=RegenerationInitiator.user,
            initiator_telegram_id=telegram_user_id,
        )
        self._limiter.register(telegram_user_id)
        await self._audit.write_audit(
            actor_type="user",
            actor_telegram_id=telegram_user_id,
            event_type="key_regenerated",
            entity_type="vpn_key",
            entity_id=str(new_key.id),
            details={"old_key_id": old.id, "slot": old.key_slot_number},
        )
        return new_key, direct_link

    async def request_second_device(
        self, telegram_user_id: int
    ) -> tuple[str, int | None, bool]:
        """Сообщение пользователю, id заявки (если есть), флаг «автовыдача второго ключа»."""
        user = await self._users.get_by_telegram_id_for_update(telegram_user_id)
        if user is None:
            user = await self.ensure_user_exists(telegram_user_id)
            user = await self._users.get_by_telegram_id_for_update(telegram_user_id)
        assert user is not None

        if await self._keys.count_active_for_user(user.id) >= 2:
            raise KeyServiceError(
                user_txt.second_device_limit_reached(self._settings.support_telegram_username)
            )

        if await self._keys.count_active_for_user(user.id) < 1:
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.NEED_FIRST))

        if self._settings.second_key_mode == SecondKeyMode.auto:
            _, link = await self._issue_second_slot(user, telegram_user_id)
            return (
                user_txt.second_device_auto_ok(
                    link, self._settings.support_telegram_username
                ),
                None,
                True,
            )

        if await self._req.has_pending_for_user(user.id):
            return user_txt.second_device_already_pending(), None, False

        req_row = await self._req.create_pending(user.id)
        await self._audit.write_audit(
            actor_type="user",
            actor_telegram_id=telegram_user_id,
            event_type="second_key_requested",
            entity_type="user",
            entity_id=str(user.id),
            details={"request_id": req_row.id},
        )
        return user_txt.second_device_pending(), req_row.id, False

    async def _issue_second_slot(self, user: User, telegram_user_id: int) -> tuple[VpnKey, str]:
        if await self._keys.count_active_for_user(user.id) >= 2:
            raise KeyServiceError(
                user_txt.second_device_limit_reached(self._settings.support_telegram_username)
            )
        inbound_id = self._inbound_for_slot(2)
        email = self._email_for_slot(telegram_user_id, 2)
        remark = self._panel_client_remark(user)
        try:
            created = await self._panel.create_client(
                inbound_id,
                email,
                remark=remark,
                telegram_user_id=user.telegram_user_id,
            )
        except PanelError as e:
            await self._audit.write_audit(
                actor_type="system",
                actor_telegram_id=None,
                event_type="panel_error_second_key",
                details={"error": str(e)[:500], "telegram_user_id": telegram_user_id},
            )
            raise KeyServiceError(self._user_msg(user_txt.UserFacing.PANEL_SECOND)) from e

        direct_link = await self._finalize_panel_issued_client(
            inbound_id,
            created,
            remark_for_link=remark,
            fail_user_message=user_txt.UserFacing.PANEL_SECOND,
            audit_event="panel_verify_failed_second_key",
            telegram_user_id=telegram_user_id,
        )

        key = await self._keys.add(
            user_id=user.id,
            inbound_id=inbound_id,
            panel_client_email=created.email,
            panel_client_uuid=created.uuid,
            panel_remark=None,
            panel_sub_id=created.sub_id,
            key_slot_number=2,
            source=VpnKeySource.issued_by_bot,
            status=VpnKeyStatus.active,
        )
        await self._audit.write_audit(
            actor_type="system",
            actor_telegram_id=telegram_user_id,
            event_type="key_issued_second",
            entity_type="vpn_key",
            entity_id=str(key.id),
            details={"slot": 2},
        )
        return key, direct_link

    async def approve_second_key(self, request_id: int, admin_telegram_id: int) -> tuple[VpnKey, str, int]:
        req = await self._req.get_for_update(request_id)
        if req is None or req.status != SecondKeyRequestStatus.pending:
            raise KeyServiceError("Заявка не найдена или уже обработана.")
        user = await self._users.get_by_id_for_update(req.user_id)
        if user is None:
            raise KeyServiceError("Пользователь не найден.")

        key, link = await self._issue_second_slot(user, user.telegram_user_id)
        await self._req.set_decision(
            req,
            status=SecondKeyRequestStatus.approved,
            admin_telegram_id=admin_telegram_id,
        )
        await self._audit.write_admin_action(
            action_type="second_key_approved",
            admin_telegram_id=admin_telegram_id,
            metadata={"request_id": request_id, "vpn_key_id": key.id},
        )
        return key, link, user.telegram_user_id

    async def reject_second_key(
        self, request_id: int, admin_telegram_id: int, reason: str | None
    ) -> int:
        req = await self._req.get_for_update(request_id)
        if req is None or req.status != SecondKeyRequestStatus.pending:
            raise KeyServiceError("Заявка не найдена или уже обработана.")
        user = await self._users.get_by_id(req.user_id)
        if user is None:
            raise KeyServiceError("Пользователь не найден.")
        await self._req.set_decision(
            req,
            status=SecondKeyRequestStatus.rejected,
            admin_telegram_id=admin_telegram_id,
            reject_reason=reason,
        )
        await self._audit.write_admin_action(
            action_type="second_key_rejected",
            admin_telegram_id=admin_telegram_id,
            metadata={"request_id": request_id, "reason": reason or ""},
        )
        return user.telegram_user_id

    async def import_unbound_from_panel(self, inbound_id: int, admin_telegram_id: int) -> int:
        rows = await self._panel.list_clients_in_inbound(inbound_id)
        n = 0
        for c in rows:
            if not c.enable:
                continue
            exists = await self._keys.find_by_panel_identity(c.inbound_id, c.email)
            if exists:
                continue
            await self._keys.add(
                user_id=None,
                inbound_id=c.inbound_id,
                panel_client_email=c.email,
                panel_client_uuid=c.uuid,
                panel_remark=c.remark,
                panel_sub_id=c.sub_id,
                key_slot_number=1,
                source=VpnKeySource.imported,
                status=VpnKeyStatus.imported_unbound,
            )
            n += 1
        await self._audit.write_admin_action(
            action_type="import_clients",
            admin_telegram_id=admin_telegram_id,
            metadata={"inbound_id": inbound_id, "imported_count": n},
        )
        return n

    async def bind_unbound_key(
        self,
        vpn_key_id: int,
        target_telegram_user_id: int,
        slot: int,
        admin_telegram_id: int,
    ) -> VpnKey:
        if slot not in (1, 2):
            raise KeyServiceError("Слот должен быть 1 или 2.")
        key = await self._keys.get_for_update(vpn_key_id)
        if key is None or key.status != VpnKeyStatus.imported_unbound:
            raise KeyServiceError("Ключ не найден или уже привязан.")

        user = await self._users.get_by_telegram_id_for_update(target_telegram_user_id)
        if user is None:
            async with self._session.begin_nested():
                try:
                    user = await self._users.create(telegram_user_id=target_telegram_user_id)
                except IntegrityError:
                    user = None
            if user is None:
                user = await self._users.get_by_telegram_id_for_update(target_telegram_user_id)
        if user is None:
            raise KeyServiceError("Пользователь не найден.")

        conflict = await self._keys.list_active_for_user(user.id)
        for k in conflict:
            if k.key_slot_number == slot:
                raise KeyServiceError(f"У пользователя уже занят слот {slot}.")

        key.user_id = user.id
        key.key_slot_number = slot
        key.status = VpnKeyStatus.active
        key.source = VpnKeySource.imported
        await self._session.flush()

        if self._settings.panel_update_remark_on_bind:
            try:
                await self._panel.update_client_remark(
                    key.inbound_id,
                    key.panel_client_email,
                    f"tg:{target_telegram_user_id}",
                )
            except PanelError:
                pass

        await self._audit.write_import_binding(
            vpn_key_id=key.id,
            telegram_user_id=target_telegram_user_id,
            admin_telegram_id=admin_telegram_id,
        )
        await self._audit.write_audit(
            actor_type="admin",
            actor_telegram_id=admin_telegram_id,
            event_type="import_bound",
            entity_type="vpn_key",
            entity_id=str(key.id),
            details={"target_telegram_user_id": target_telegram_user_id, "slot": slot},
        )
        await self._audit.write_admin_action(
            action_type="bind_imported",
            admin_telegram_id=admin_telegram_id,
            metadata={
                "vpn_key_id": key.id,
                "telegram_user_id": target_telegram_user_id,
                "slot": slot,
            },
        )
        return key

    async def admin_revoke_all_keys(self, target_telegram_user_id: int, admin_telegram_id: int) -> int:
        user = await self._users.get_by_telegram_id(target_telegram_user_id)
        if user is None:
            raise KeyServiceError("Пользователь не найден.")
        keys = await self._keys.list_active_for_user(user.id)
        revoked = 0
        for k in keys:
            try:
                await self._panel.delete_client_by_email(k.inbound_id, k.panel_client_email)
            except PanelError:
                await self._audit.write_audit(
                    actor_type="admin",
                    actor_telegram_id=admin_telegram_id,
                    event_type="panel_error_revoke",
                    entity_type="vpn_key",
                    entity_id=str(k.id),
                    details={"error": "delete failed"},
                )
                continue
            await self._keys.revoke(k)
            revoked += 1
            await self._audit.write_audit(
                actor_type="admin",
                actor_telegram_id=admin_telegram_id,
                event_type="access_key_revoked",
                entity_type="vpn_key",
                entity_id=str(k.id),
                details={
                    "target_telegram_user_id": target_telegram_user_id,
                    "slot": k.key_slot_number,
                    "reason": "admin_revoke_all",
                },
            )
        if revoked:
            await self._audit.write_audit(
                actor_type="admin",
                actor_telegram_id=admin_telegram_id,
                event_type="access_revoked_all",
                details={
                    "target_telegram_user_id": target_telegram_user_id,
                    "count": revoked,
                },
            )
        await self._audit.write_admin_action(
            action_type="revoke_all",
            admin_telegram_id=admin_telegram_id,
            metadata={"target_telegram_user_id": target_telegram_user_id, "count": revoked},
        )
        return revoked

    async def admin_disable_key(self, vpn_key_id: int, admin_telegram_id: int) -> None:
        key = await self._keys.get_for_update(vpn_key_id)
        if key is None or key.status != VpnKeyStatus.active:
            raise KeyServiceError("Активный ключ не найден.")
        try:
            await self._panel.delete_client_by_email(key.inbound_id, key.panel_client_email)
        except PanelError as e:
            await self._audit.write_audit(
                actor_type="admin",
                actor_telegram_id=admin_telegram_id,
                event_type="panel_error_disable_key",
                entity_type="vpn_key",
                entity_id=str(key.id),
                details={"error": str(e)[:300]},
            )
            raise KeyServiceError("Панель не подтвердила отключение.") from e
        owner = await self._users.get_by_id(key.user_id)
        tg_target = owner.telegram_user_id if owner else None
        await self._keys.revoke(key)
        await self._audit.write_audit(
            actor_type="admin",
            actor_telegram_id=admin_telegram_id,
            event_type="access_key_revoked",
            entity_type="vpn_key",
            entity_id=str(vpn_key_id),
            details={
                "target_telegram_user_id": tg_target,
                "slot": key.key_slot_number,
                "reason": "admin_disable_key",
            },
        )
        await self._audit.write_admin_action(
            action_type="disable_key",
            admin_telegram_id=admin_telegram_id,
            metadata={"vpn_key_id": vpn_key_id},
        )

    async def subscription_link_for_key(self, key: VpnKey) -> str:
        return self._panel.build_subscription_link(
            key.panel_sub_id, key.panel_client_email, key.inbound_id
        )

    async def enqueue_user_notification(self, telegram_user_id: int, text: str) -> None:
        await self._pending.enqueue(telegram_user_id, text)

    async def _panel_snapshot_for_keys(
        self, keys: list[VpnKey],
    ) -> list[
        tuple[
            VpnKey,
            str,
            str,
            int | None,
            Literal["traffic_ok", "traffic_no_api", "traffic_no_row"],
            PanelClientRow | None,
            ClientTrafficRow | None,
            str | None,
        ]
    ]:
        """Панель, трафик, сырые строки для активности (lastOnline / online — если панель отдала)."""
        if not keys:
            return []
        unique_inbounds = {k.inbound_id for k in keys}
        inbound_clients: dict[int, list[PanelClientRow]] = {}
        clients_ok: dict[int, bool] = {}
        for iid in unique_inbounds:
            try:
                inbound_clients[iid] = await self._panel.list_clients_in_inbound(iid)
                clients_ok[iid] = True
            except PanelError:
                inbound_clients[iid] = []
                clients_ok[iid] = False

        emails = [k.panel_client_email for k in keys]
        traffic_by_email: dict[str, ClientTrafficRow] | None = await self._panel.fetch_client_traffics_by_emails(
            emails
        )

        out: list[
            tuple[
                VpnKey,
                str,
                str,
                int | None,
                Literal["traffic_ok", "traffic_no_api", "traffic_no_row"],
                PanelClientRow | None,
                ClientTrafficRow | None,
                str | None,
            ]
        ] = []
        for k in sorted(keys, key=lambda x: x.key_slot_number):
            match: PanelClientRow | None = None
            if not clients_ok.get(k.inbound_id, False):
                panel_short = "панель не ответила"
            else:
                match = next(
                    (c for c in inbound_clients[k.inbound_id] if c.email == k.panel_client_email),
                    None,
                )
                if match is None:
                    panel_short = "на сервере записи нет"
                elif not match.enable:
                    panel_short = "на сервере выключено"
                else:
                    panel_short = "на сервере всё ок"

            traffic_row: ClientTrafficRow | None = None
            if traffic_by_email is None:
                traffic_short = "статистики нет"
                traffic_bytes = None
                t_state: Literal["traffic_ok", "traffic_no_api", "traffic_no_row"] = "traffic_no_api"
            else:
                traffic_row = traffic_by_email.get(k.panel_client_email)
                if traffic_row is None:
                    traffic_short = "в отчёте трафика пусто"
                    traffic_bytes = None
                    t_state = "traffic_no_row"
                else:
                    traffic_bytes = traffic_row.total_use_bytes()
                    traffic_short = user_txt.format_data_volume(traffic_bytes)
                    t_state = "traffic_ok"

            activity_line = user_txt.format_activity_line(
                match.last_seen_utc if match else None,
                traffic_row.last_seen_utc if traffic_row else None,
                traffic_row.online if traffic_row else None,
            )
            out.append((k, panel_short, traffic_short, traffic_bytes, t_state, match, traffic_row, activity_line))
        return out

    async def compose_my_keys_message(self, telegram_user_id: int) -> str:
        support = self._settings.support_telegram_username
        keys = await self.list_active_keys_for_telegram(telegram_user_id)
        if not keys:
            return user_txt.format_keys_empty(support)

        snap = await self._panel_snapshot_for_keys(keys)
        lines_per_key = []
        for k, panel_short, _ts, traffic_bytes, t_state, _m, _tr, activity_line in snap:
            origin = user_txt.origin_human_from_key(k)

            if panel_short == "панель не ответила":
                panel_line = "не смогли проверить запись на сервере — панель молчит"
            elif panel_short == "на сервере записи нет":
                panel_line = user_txt.panel_client_missing()
            elif panel_short == "на сервере выключено":
                panel_line = user_txt.panel_client_disabled()
            else:
                panel_line = user_txt.panel_client_ok()

            if t_state == "traffic_ok" and traffic_bytes is not None:
                traffic_line = user_txt.traffic_line_from_server(traffic_bytes)
            elif t_state == "traffic_no_api":
                traffic_line = user_txt.traffic_line_unavailable()
            else:
                traffic_line = user_txt.traffic_line_not_in_report()

            lines_per_key.append(
                user_txt.line_key_human(
                    slot_number=k.key_slot_number,
                    created_at=k.created_at,
                    origin_human=origin,
                    panel_line=panel_line,
                    traffic_line=traffic_line,
                    activity_line=activity_line,
                )
            )

        second_empty = len(keys) == 1 and keys[0].key_slot_number == 1
        return user_txt.format_my_keys_block(
            keys=keys,
            lines_per_key=lines_per_key,
            second_slot_empty=second_empty,
            support_user=support,
        )

    async def compose_access_check_message(self, telegram_user_id: int) -> str:
        support = self._settings.support_telegram_username
        try:
            await self._panel.healthcheck()
        except PanelError:
            return user_txt.access_check_panel_down(support)

        keys = await self.list_active_keys_for_telegram(telegram_user_id)
        summary = ["панель отвечает"]
        if not keys:
            summary.append("в боте нет ключей — если доступ должен быть, админ")
            return user_txt.access_check_ok(summary, support)

        snap = await self._panel_snapshot_for_keys(keys)
        for k, ps, ts, _tb, _st, _m, _tr, act in snap:
            title = user_txt.human_device_title(k.key_slot_number)
            extra = f" · {act}" if act else ""
            summary.append(f"{title}: {ps}, {ts}{extra}")
        summary.append("не твой Wi‑Fi")
        return user_txt.access_check_ok(summary, support)

    async def compose_vpn_status_message(self, telegram_user_id: int) -> str:
        support = self._settings.support_telegram_username
        keys = await self.list_active_keys_for_telegram(telegram_user_id)
        if not keys:
            return user_txt.vpn_status_no_keys(support)
        try:
            await self._panel.healthcheck()
        except PanelError:
            return user_txt.vpn_status_panel_down(support)

        snap = await self._panel_snapshot_for_keys(keys)
        blocks: list[str] = []
        for k, ps, ts, _tb, _st, _m, _tr, act in snap:
            title = user_txt.human_device_title(k.key_slot_number)
            if ps == "панель не ответила":
                panel_line = "панель: нет связи"
            elif ps == "на сервере записи нет":
                panel_line = "панель: записи нет"
            elif ps == "на сервере выключено":
                panel_line = "панель: выкл"
            else:
                panel_line = "панель: ок"

            traffic_line = f"трафик: {user_txt.html_escape(ts)}"
            act_line = act or "активность: нет lastOnline/online"
            blocks.append(
                f"<b>{user_txt.html_escape(title)}</b> · бот: активен\n{panel_line}\n{traffic_line}\n{act_line}"
            )

        body = "\n\n".join(blocks)
        return user_txt.vpn_status_message(body, support_user=support)

    async def compose_traffic_totals_message(self, telegram_user_id: int) -> str:
        """Накопительный трафик up+down по данным API панели (как «за всё время» с точки зрения счётчиков)."""
        support = self._settings.support_telegram_username
        keys = await self.list_active_keys_for_telegram(telegram_user_id)
        if not keys:
            return user_txt.traffic_totals_no_keys(support)
        try:
            await self._panel.healthcheck()
        except PanelError:
            return user_txt.traffic_totals_panel_down(support)

        snap = await self._panel_snapshot_for_keys(keys)
        lines: list[str] = []
        known: list[int] = []
        for k, _ps, _ts, tb, t_state, _m, _tr, _act in snap:
            title = user_txt.human_device_title(k.key_slot_number)
            if t_state == "traffic_ok" and tb is not None:
                lines.append(f"{user_txt.html_escape(title)}: <b>{user_txt.format_data_volume(tb)}</b>")
                known.append(tb)
            elif t_state == "traffic_no_api":
                lines.append(f"{user_txt.html_escape(title)}: панель не отдала счётчики")
            else:
                lines.append(f"{user_txt.html_escape(title)}: нет строки в отчёте")

        body = "\n".join(lines)
        if len(known) >= 2:
            total = sum(known)
            body += f"\n\n<b>Всего:</b> {user_txt.format_data_volume(total)}"
        return user_txt.traffic_totals_message(body, support_user=support)

    async def compose_user_history_message(self, telegram_user_id: int) -> str:
        support = self._settings.support_telegram_username
        rows = await self._audit.list_user_timeline(telegram_user_id, limit=40)
        chronological = list(reversed(rows))
        return user_txt.format_user_history(chronological, support_user=support)

    async def stats(self) -> dict[str, Any]:
        from sqlalchemy import func, select

        from app.models.user import User
        from app.models.vpn_key import VpnKey

        uc = await self._session.execute(select(func.count()).select_from(User))
        kc = await self._session.execute(
            select(func.count()).select_from(VpnKey).where(VpnKey.status == VpnKeyStatus.active)
        )
        ub = await self._session.execute(
            select(func.count())
            .select_from(VpnKey)
            .where(VpnKey.status == VpnKeyStatus.imported_unbound)
        )
        return {
            "users": int(uc.scalar_one()),
            "active_keys": int(kc.scalar_one()),
            "unbound_imported": int(ub.scalar_one()),
        }
