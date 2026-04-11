from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit import AuditRepository
from app.repositories.pending_notification import PendingNotificationRepository
from app.repositories.user import UserRepository
from app.models.user import User


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._pending = PendingNotificationRepository(session)
        self._audit = AuditRepository(session)

    async def register_or_update_profile(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> tuple[User, bool]:
        user = await self._users.get_by_telegram_id(telegram_user_id)
        created = False
        if user is None:
            user = await self._users.create(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            created = True
            await self._audit.write_audit(
                actor_type="user",
                actor_telegram_id=telegram_user_id,
                event_type="user_created",
                entity_type="user",
                entity_id=str(user.id),
                details={"telegram_user_id": telegram_user_id},
            )
        else:
            await self._users.update_profile(
                user, username=username, first_name=first_name, last_name=last_name
            )
        return user, created

    async def admin_create_legacy_user(
        self, telegram_user_id: int, admin_telegram_id: int
    ) -> tuple[User, bool]:
        """Create user by telegram id if missing (admin onboarding)."""
        existing = await self._users.get_by_telegram_id(telegram_user_id)
        if existing:
            return existing, False
        created_new = False
        user = None
        async with self._session.begin_nested():
            try:
                user = await self._users.create(telegram_user_id=telegram_user_id)
                created_new = True
            except IntegrityError:
                pass
        if user is None:
            user = await self._users.get_by_telegram_id(telegram_user_id)
        if user is None:
            raise RuntimeError("create failed")
        if created_new:
            await self._audit.write_audit(
                actor_type="admin",
                actor_telegram_id=admin_telegram_id,
                event_type="legacy_user_created",
                entity_type="user",
                entity_id=str(user.id),
                details={"telegram_user_id": telegram_user_id},
            )
            await self._audit.write_admin_action(
                action_type="create_legacy_user",
                admin_telegram_id=admin_telegram_id,
                metadata={"telegram_user_id": telegram_user_id},
            )
        return user, created_new

    async def deliver_pending_notifications(self, bot: Bot, telegram_user_id: int) -> None:
        rows = await self._pending.list_unsent_for_user(telegram_user_id)
        now = datetime.now(tz=UTC)
        for row in rows:
            try:
                await bot.send_message(telegram_user_id, row.message_text)
            except Exception:
                # User blocked bot or never started — keep unsent
                continue
            await self._pending.mark_sent(row.id, now)
