from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action import AdminAction
from app.models.audit_log import AuditLog
from app.models.import_binding import ImportBinding
from app.models.regeneration import RegenerationHistory, RegenerationInitiator

USER_TIMELINE_EVENT_TYPES = frozenset(
    {
        "user_created",
        "key_issued_first",
        "key_regenerated",
        "second_key_requested",
        "key_issued_second",
        "import_bound",
        "access_revoked_all",
        "access_key_revoked",
    }
)


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_audit(
        self,
        *,
        actor_type: str,
        actor_telegram_id: int | None,
        event_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        row = AuditLog(
            actor_type=actor_type,
            actor_telegram_id=actor_telegram_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
        self._session.add(row)
        await self._session.flush()

    async def write_admin_action(
        self,
        *,
        action_type: str,
        admin_telegram_id: int,
        metadata: dict[str, Any],
    ) -> None:
        row = AdminAction(
            action_type=action_type,
            admin_telegram_id=admin_telegram_id,
            metadata_json=metadata,
        )
        self._session.add(row)
        await self._session.flush()

    async def write_import_binding(
        self,
        *,
        vpn_key_id: int,
        telegram_user_id: int,
        admin_telegram_id: int,
    ) -> None:
        row = ImportBinding(
            vpn_key_id=vpn_key_id,
            telegram_user_id=telegram_user_id,
            admin_telegram_id=admin_telegram_id,
        )
        self._session.add(row)
        await self._session.flush()

    async def recent_audit(self, limit: int = 30) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_user_timeline(self, telegram_user_id: int, limit: int = 30) -> list[AuditLog]:
        """События, относящиеся к пользователю (по актору или полям в details)."""
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.event_type.in_(USER_TIMELINE_EVENT_TYPES))
            .where(
                or_(
                    AuditLog.actor_telegram_id == telegram_user_id,
                    AuditLog.details.contains({"target_telegram_user_id": telegram_user_id}),
                    AuditLog.details.contains({"telegram_user_id": telegram_user_id}),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def write_regeneration_history(
        self,
        *,
        old_key_id: int,
        new_key_id: int,
        initiator: RegenerationInitiator,
        initiator_telegram_id: int | None,
    ) -> None:
        row = RegenerationHistory(
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            initiator=initiator,
            initiator_telegram_id=initiator_telegram_id,
        )
        self._session.add(row)
        await self._session.flush()
