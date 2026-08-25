import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class OverrideTriggerType(str, enum.Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_DECLARE = "MANUAL_DECLARE"


class OverrideFlagReason(str, enum.Enum):
    FREQUENCY_THRESHOLD = "FREQUENCY_THRESHOLD"
    POST_HOC_ACUITY_MISMATCH = "POST_HOC_ACUITY_MISMATCH"


# =============================================================================
# ORM Model
# =============================================================================
class EmergencyOverrideEvent(Base):
    __tablename__ = "emergency_override_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    patient_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    acuity_score_at_trigger: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
    )
    manual_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    requested_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    resources_requested: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    escalation_ids: Mapped[Optional[List[uuid.UUID]]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=True,
    )
    latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    flagged_for_review: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    flag_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
