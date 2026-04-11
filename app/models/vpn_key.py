from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class VpnKeySource(str, enum.Enum):
    imported = "imported"
    issued_by_bot = "issued_by_bot"


class VpnKeyStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"
    imported_unbound = "imported_unbound"


class VpnKey(Base):
    __tablename__ = "vpn_keys"
    __table_args__ = (
        Index(
            "uq_vpn_keys_user_slot_active",
            "user_id",
            "key_slot_number",
            unique=True,
            postgresql_where=text("status = 'active' AND user_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    inbound_id: Mapped[int] = mapped_column(Integer(), nullable=False)
    panel_client_email: Mapped[str] = mapped_column(String(512), nullable=False)
    panel_client_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    panel_remark: Mapped[str | None] = mapped_column(String(512), nullable=True)
    panel_sub_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    key_slot_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    source: Mapped[VpnKeySource] = mapped_column(
        SAEnum(VpnKeySource, name="vpn_key_source", native_enum=False),
        nullable=False,
    )
    status: Mapped[VpnKeyStatus] = mapped_column(
        SAEnum(VpnKeyStatus, name="vpn_key_status", native_enum=False),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User | None] = relationship(back_populates="vpn_keys")
