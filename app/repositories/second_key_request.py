from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.second_key_request import SecondKeyRequest, SecondKeyRequestStatus


class SecondKeyRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(self, user_id: int) -> SecondKeyRequest:
        row = SecondKeyRequest(user_id=user_id, status=SecondKeyRequestStatus.pending)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, request_id: int) -> SecondKeyRequest | None:
        result = await self._session.execute(
            select(SecondKeyRequest).where(SecondKeyRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, request_id: int) -> SecondKeyRequest | None:
        result = await self._session.execute(
            select(SecondKeyRequest)
            .where(SecondKeyRequest.id == request_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def has_pending_for_user(self, user_id: int) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(SecondKeyRequest)
            .where(
                SecondKeyRequest.user_id == user_id,
                SecondKeyRequest.status == SecondKeyRequestStatus.pending,
            )
        )
        return int(result.scalar_one()) > 0

    async def list_pending(self, limit: int = 50) -> list[SecondKeyRequest]:
        result = await self._session.execute(
            select(SecondKeyRequest)
            .where(SecondKeyRequest.status == SecondKeyRequestStatus.pending)
            .order_by(SecondKeyRequest.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_decision(
        self,
        req: SecondKeyRequest,
        *,
        status: SecondKeyRequestStatus,
        admin_telegram_id: int,
        reject_reason: str | None = None,
    ) -> None:
        req.status = status
        req.admin_telegram_id = admin_telegram_id
        req.reject_reason = reject_reason
        await self._session.flush()
