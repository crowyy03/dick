import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegenerationInitiator(str, enum.Enum):
    user = "user"
    admin = "admin"
    system = "system"


class RegenerationHistory(Base):
    __tablename__ = "regeneration_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    old_key_id: Mapped[int] = mapped_column(ForeignKey("vpn_keys.id", ondelete="RESTRICT"), nullable=False)
    new_key_id: Mapped[int] = mapped_column(ForeignKey("vpn_keys.id", ondelete="RESTRICT"), nullable=False)
    initiator: Mapped[RegenerationInitiator] = mapped_column(
        SAEnum(RegenerationInitiator, name="regeneration_initiator", native_enum=False),
        nullable=False,
    )
    initiator_telegram_id: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
