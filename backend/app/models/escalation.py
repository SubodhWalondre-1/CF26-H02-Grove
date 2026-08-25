import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class EscalationDecision(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EscalationSourceFeature(str, enum.Enum):
    DIRECT = "DIRECT"
    PATIENT_TRANSFER = "PATIENT_TRANSFER"
    DIAGNOSTIC_SCHEDULING = "DIAGNOSTIC_SCHEDULING"
    EMERGENCY_OVERRIDE_ROUTED = "EMERGENCY_OVERRIDE_ROUTED"


# =============================================================================
# ORM Model
# =============================================================================
class EscalationRequest(Base):
    __tablename__ = "escalation_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    escalating_tx_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    escalating_acuity: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
    )
    target_resource_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    holder_tx_id: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    holder_acuity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(
        String(16),
        default=EscalationDecision.PENDING.value,
        nullable=False,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    requested_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_feature: Mapped[str] = mapped_column(
        String(32),
        default=EscalationSourceFeature.DIRECT.value,
        nullable=False,
    )
