import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class TransferStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    DESTINATION_HELD = "DESTINATION_HELD"
    TRANSPORT_ASSIGNED = "TRANSPORT_ASSIGNED"
    SOURCE_RELEASE_PENDING = "SOURCE_RELEASE_PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    COMPENSATED = "COMPENSATED"


class TransferType(str, enum.Enum):
    INTRA_FACILITY = "INTRA_FACILITY"
    INTER_FACILITY = "INTER_FACILITY"


# =============================================================================
# ORM Model
# =============================================================================
class PatientTransfer(Base):
    __tablename__ = "patient_transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("transactions.tx_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_bed_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("beds.id"),
        nullable=False,
    )
    destination_bed_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("beds.id"),
        nullable=False,
    )
    transport_resource_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("resources.resource_id", ondelete="SET NULL"),
        nullable=True,
    )
    transfer_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TransferType.INTRA_FACILITY.value,
    )
    reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=TransferStatus.INITIATED.value,
    )
    hold_ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    initiated_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    committed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    transaction = relationship("Transaction", foreign_keys=[tx_id])
    patient = relationship("Patient", foreign_keys=[patient_id])
    source_bed = relationship("Bed", foreign_keys=[source_bed_id])
    destination_bed = relationship("Bed", foreign_keys=[destination_bed_id])
    transport_resource = relationship("Resource", foreign_keys=[transport_resource_id])
