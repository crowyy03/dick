from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportBinding(Base):
    __tablename__ = "import_bindings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vpn_key_id: Mapped[int] = mapped_column(ForeignKey("vpn_keys.id", ondelete="CASCADE"), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
