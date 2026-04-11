from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pending_notification import PendingUserNotification


class PendingNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, telegram_user_id: int, message_text: str) -> None:
        row = PendingUserNotification(telegram_user_id=telegram_user_id, message_text=message_text)
        self._session.add(row)
        await self._session.flush()

    async def list_unsent_for_user(self, telegram_user_id: int) -> list[PendingUserNotification]:
        result = await self._session.execute(
            select(PendingUserNotification)
            .where(
                PendingUserNotification.telegram_user_id == telegram_user_id,
                PendingUserNotification.sent_at.is_(None),
            )
            .order_by(PendingUserNotification.id.asc())
        )
        return list(result.scalars().all())

    async def mark_sent(self, notification_id: int, sent_at: datetime) -> None:
        await self._session.execute(
            update(PendingUserNotification)
            .where(PendingUserNotification.id == notification_id)
            .values(sent_at=sent_at)
        )
        await self._session.flush()
