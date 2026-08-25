import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class DiagnosticResourceType(str, enum.Enum):
    DIAGNOSTIC_MRI = "DIAGNOSTIC_MRI"
    DIAGNOSTIC_CT = "DIAGNOSTIC_CT"
    DIAGNOSTIC_XRAY = "DIAGNOSTIC_XRAY"


class EquipmentStatus(str, enum.Enum):
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    IN_USE = "IN_USE"
    REPORTING = "REPORTING"
    CALIBRATING = "CALIBRATING"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"


class AppointmentStatus(str, enum.Enum):
    PENDING_CONFIRM = "PENDING_CONFIRM"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class LabSlotStatus(str, enum.Enum):
    READY = "READY"
    AT_CAPACITY = "AT_CAPACITY"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"


class SampleStatus(str, enum.Enum):
    SAMPLE_COLLECTED = "SAMPLE_COLLECTED"
    IN_TRANSIT = "IN_TRANSIT"
    PROCESSING = "PROCESSING"
    RESULT_READY = "RESULT_READY"
    RESULT_DELIVERED = "RESULT_DELIVERED"
    REJECTED = "REJECTED"


class SamplePriority(str, enum.Enum):
    ROUTINE = "ROUTINE"
    STAT = "STAT"


# =============================================================================
# ORM Models
# =============================================================================
class DiagnosticEquipment(Base):
    __tablename__ = "diagnostic_equipment"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    equipment_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EquipmentStatus.READY.value
    )
    avg_scan_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_contrast: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_calibrated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    calibration_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointments: Mapped[List["DiagnosticAppointment"]] = relationship(
        "DiagnosticAppointment", back_populates="equipment", cascade="all, delete-orphan"
    )


class DiagnosticAppointment(Base):
    __tablename__ = "diagnostic_appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.tx_id", ondelete="CASCADE"), nullable=False
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("diagnostic_equipment.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False
    )
    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AppointmentStatus.PENDING_CONFIRM.value
    )
    hold_ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    contrast_reservation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pharmacy_reservations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    equipment: Mapped["DiagnosticEquipment"] = relationship(
        "DiagnosticEquipment", back_populates="appointments"
    )


class LabSlot(Base):
    __tablename__ = "lab_slots"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    lab_station_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False)
    current_load: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LabSlotStatus.READY.value
    )
    location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    samples: Mapped[List["LabSample"]] = relationship(
        "LabSample", back_populates="lab_slot", cascade="all, delete-orphan"
    )


class LabSample(Base):
    __tablename__ = "lab_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.tx_id", ondelete="CASCADE"), nullable=False
    )
    lab_slot_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lab_slots.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False
    )
    test_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(25), nullable=False, default=SampleStatus.SAMPLE_COLLECTED.value
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default=SamplePriority.ROUTINE.value
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    result_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    turnaround_estimate_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lab_slot: Mapped["LabSlot"] = relationship(
        "LabSlot", back_populates="samples"
    )
