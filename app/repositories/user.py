from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserStatus


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id_for_update(self, telegram_user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            status=UserStatus.active,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def update_profile(
        self,
        user: User,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        await self._session.flush()
        return user

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self._session.execute(
            select(User).order_by(User.id.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count_users(self) -> int:
        from sqlalchemy import func

        result = await self._session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def load_user_with_keys(self, telegram_user_id: int) -> User | None:
        result = await self._session.execute(
            select(User)
            .options(selectinload(User.vpn_keys))
            .where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()
