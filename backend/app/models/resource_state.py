import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResourceStateTransition(Base):
    __tablename__ = "resource_state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    resource_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    to_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    triggered_by: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    duration_in_prior_state_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )


class ResourceReadinessDefault(Base):
    __tablename__ = "resource_readiness_defaults"

    resource_type: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )
    default_cleaning_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    requires_manual_verification: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    default_maintenance_check_interval_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )


class ResourceReadySubscription(Base):
    __tablename__ = "resource_ready_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    resource_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    subscribed_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
