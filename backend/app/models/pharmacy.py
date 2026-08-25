import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class PharmacyResourceType(str, enum.Enum):
    medication_slot = "medication_slot"
    blood_unit = "blood_unit"
    oxygen_unit = "oxygen_unit"


class PharmacyResourceStatus(str, enum.Enum):
    STOCKED = "STOCKED"
    LOW_STOCK = "LOW_STOCK"
    DEPLETED = "DEPLETED"
    EXPIRED = "EXPIRED"
    RECALLED = "RECALLED"


class PharmacyReservationStatus(str, enum.Enum):
    RESERVED = "RESERVED"
    DISPENSED = "DISPENSED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# =============================================================================
# PostgreSQL ENUM bindings
# =============================================================================
pharmacy_resource_type_enum = PGEnum(
    PharmacyResourceType,
    name="pharmacy_resource_type",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)

pharmacy_resource_status_enum = PGEnum(
    PharmacyResourceStatus,
    name="pharmacy_resource_status",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)

pharmacy_reservation_status_enum = PGEnum(
    PharmacyReservationStatus,
    name="pharmacy_reservation_status",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)


# =============================================================================
# ORM Models
# =============================================================================
class PharmacyResource(Base):
    __tablename__ = "pharmacy_resources"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    resource_type: Mapped[PharmacyResourceType] = mapped_column(
        pharmacy_resource_type_enum, nullable=False
    )
    sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    storage_location: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    critical_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PharmacyResourceStatus] = mapped_column(
        pharmacy_resource_status_enum,
        nullable=False,
        default=PharmacyResourceStatus.STOCKED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PharmacyReservation(Base):
    __tablename__ = "pharmacy_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=False
    )
    pharmacy_resource_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pharmacy_resources.id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PharmacyReservationStatus] = mapped_column(
        pharmacy_reservation_status_enum,
        nullable=False,
        default=PharmacyReservationStatus.RESERVED,
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispensed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
