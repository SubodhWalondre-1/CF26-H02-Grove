import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class IdempotencyStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"
    EXPIRED = "EXPIRED"


# =============================================================================
# ORM Model
# =============================================================================
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    fingerprint: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    request_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    claimed_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=IdempotencyStatus.PENDING.value,
        nullable=False,
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    duplicate_hits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
