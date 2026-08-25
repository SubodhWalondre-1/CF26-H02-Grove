import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShortageThreshold(Base):
    __tablename__ = "shortage_thresholds"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    resource_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    subtype: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    critical_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    unit_label: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )
    resource_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    subtype: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    units_needed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(
        String(32),
        default="SYSTEM",
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
