from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vpn_key import VpnKey, VpnKeySource, VpnKeyStatus


class VpnKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key_id: int) -> VpnKey | None:
        result = await self._session.execute(select(VpnKey).where(VpnKey.id == key_id))
        return result.scalar_one_or_none()

    async def get_for_update(self, key_id: int) -> VpnKey | None:
        result = await self._session.execute(
            select(VpnKey).where(VpnKey.id == key_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: int) -> list[VpnKey]:
        result = await self._session.execute(
            select(VpnKey)
            .where(
                VpnKey.user_id == user_id,
                VpnKey.status == VpnKeyStatus.active,
            )
            .order_by(VpnKey.key_slot_number)
        )
        return list(result.scalars().all())

    async def count_active_for_user(self, user_id: int) -> int:
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.count())
            .select_from(VpnKey)
            .where(VpnKey.user_id == user_id, VpnKey.status == VpnKeyStatus.active)
        )
        return int(result.scalar_one())

    async def list_imported_unbound(self, limit: int = 50, offset: int = 0) -> list[VpnKey]:
        result = await self._session.execute(
            select(VpnKey)
            .where(VpnKey.status == VpnKeyStatus.imported_unbound)
            .order_by(VpnKey.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_panel_identity(
        self, inbound_id: int, panel_client_email: str
    ) -> VpnKey | None:
        result = await self._session.execute(
            select(VpnKey).where(
                VpnKey.inbound_id == inbound_id,
                VpnKey.panel_client_email == panel_client_email,
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        *,
        user_id: int | None,
        inbound_id: int,
        panel_client_email: str,
        panel_client_uuid: str | None,
        panel_remark: str | None,
        panel_sub_id: str | None,
        key_slot_number: int,
        source: VpnKeySource,
        status: VpnKeyStatus,
    ) -> VpnKey:
        row = VpnKey(
            user_id=user_id,
            inbound_id=inbound_id,
            panel_client_email=panel_client_email,
            panel_client_uuid=panel_client_uuid,
            panel_remark=panel_remark,
            panel_sub_id=panel_sub_id,
            key_slot_number=key_slot_number,
            source=source,
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def revoke(self, key: VpnKey) -> None:
        from datetime import UTC, datetime

        key.status = VpnKeyStatus.revoked
        key.revoked_at = datetime.now(tz=UTC)
        await self._session.flush()
