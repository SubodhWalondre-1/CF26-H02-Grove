import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =============================================================================
# Python Enums
# =============================================================================
class UserRole(str, enum.Enum):
    doctor = "doctor"
    nurse = "nurse"
    admin = "admin"
    system = "system"


class ResourceType(str, enum.Enum):
    ot = "ot"
    surgeon = "surgeon"
    anesthesia = "anesthesia"
    ventilator = "ventilator"
    other = "other"


class ResourceStatus(str, enum.Enum):
    available = "available"
    tentative = "tentative"
    locked = "locked"


class RequestType(str, enum.Enum):
    single_resource = "single_resource"
    care_bundle = "care_bundle"
    patient_transfer = "patient_transfer"
    escalation = "escalation"


class TxState(str, enum.Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    ARBITRATING = "ARBITRATING"
    NO_CONFLICT = "NO_CONFLICT"
    PREPARING = "PREPARING"
    COMMITTING = "COMMITTING"
    ROLLINGBACK = "ROLLINGBACK"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    COMPENSATING = "COMPENSATING"
    RELEASED = "RELEASED"
    CLOSED = "CLOSED"


class HoldState(str, enum.Enum):
    requested = "requested"
    tentative = "tentative"
    held = "held"
    released = "released"
    failed = "failed"


class ConflictStatus(str, enum.Enum):
    unresolved = "unresolved"
    resolved = "resolved"


class BedType(str, enum.Enum):
    ICU = "ICU"
    GENERAL = "GENERAL"
    STEP_DOWN = "STEP_DOWN"
    EMERGENCY = "EMERGENCY"


class BedStatus(str, enum.Enum):
    FREE = "FREE"
    CLEANING = "CLEANING"
    SANITIZED = "SANITIZED"
    READY = "READY"
    TENTATIVE_HOLD = "TENTATIVE_HOLD"
    LOCKED = "LOCKED"
    IN_USE = "IN_USE"
    POST_USE = "POST_USE"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


user_role_enum = PGEnum(
    UserRole,
    name="user_role",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
resource_type_enum = PGEnum(
    ResourceType,
    name="resource_type",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
resource_status_enum = PGEnum(
    ResourceStatus,
    name="resource_status",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
request_type_enum = PGEnum(
    RequestType,
    name="request_type",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
tx_state_enum = PGEnum(
    TxState,
    name="tx_state",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
hold_state_enum = PGEnum(
    HoldState,
    name="hold_state",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
conflict_status_enum = PGEnum(
    ConflictStatus,
    name="conflict_status",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
bed_type_enum = PGEnum(
    BedType,
    name="bed_type_enum",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
bed_status_enum = PGEnum(
    BedStatus,
    name="bed_status_enum",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)


# =============================================================================
# ORM Models
# =============================================================================
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(user_role_enum, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="requester"
    )


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    clinical_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_acuity: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("0.00"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="patient"
    )


class Resource(Base):
    __tablename__ = "resources"

    resource_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    type: Mapped[ResourceType] = mapped_column(
        resource_type_enum, nullable=False
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ResourceStatus] = mapped_column(
        resource_status_enum,
        default=ResourceStatus.available,
        nullable=False,
    )
    criticality: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.00"), nullable=False
    )
    held_by_tx: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cleaning_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sanitized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    held_by_transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[held_by_tx]
    )
    transaction_associations: Mapped[List["TransactionResource"]] = (
        relationship("TransactionResource", back_populates="resource")
    )


class Transaction(Base):
    __tablename__ = "transactions"

    tx_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    request_type: Mapped[RequestType] = mapped_column(
        request_type_enum, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("patients.patient_id"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(
        String(20), ForeignKey("users.user_id"), nullable=False
    )
    state: Mapped[TxState] = mapped_column(
        tx_state_enum, default=TxState.CREATED, nullable=False
    )
    request_fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)
    hold_ttl_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="transactions"
    )
    requester: Mapped["User"] = relationship(
        "User", back_populates="transactions"
    )
    resources: Mapped[List["TransactionResource"]] = relationship(
        "TransactionResource", back_populates="transaction"
    )
    state_history: Mapped[List["TransactionStateHistory"]] = relationship(
        "TransactionStateHistory", back_populates="transaction"
    )
    audit_events: Mapped[List["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="transaction"
    )
    conflict_transactions: Mapped[List["ConflictTransaction"]] = relationship(
        "ConflictTransaction", back_populates="transaction"
    )


class TransactionStateHistory(Base):
    __tablename__ = "transaction_state_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=False
    )
    state: Mapped[TxState] = mapped_column(
        tx_state_enum, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="state_history"
    )


class TransactionResource(Base):
    __tablename__ = "transaction_resources"

    tx_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), primary_key=True
    )
    resource_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("resources.resource_id"), primary_key=True
    )
    hold_state: Mapped[HoldState] = mapped_column(
        hold_state_enum,
        default=HoldState.requested,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="resources"
    )
    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="transaction_associations"
    )


class Conflict(Base):
    __tablename__ = "conflicts"

    conflict_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    resource_contested: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("resources.resource_id"), nullable=True
    )
    winner_tx_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=True
    )
    resolution_level: Mapped[str] = mapped_column(
        String(20), default="transaction", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conflict_transactions: Mapped[List["ConflictTransaction"]] = relationship(
        "ConflictTransaction", back_populates="conflict"
    )


class ConflictTransaction(Base):
    __tablename__ = "conflict_transactions"

    conflict_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("conflicts.conflict_id"), primary_key=True
    )
    tx_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), primary_key=True
    )
    base_acuity: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    wait_contribution: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False
    )
    resource_criticality: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False
    )
    effective_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)

    conflict: Mapped["Conflict"] = relationship(
        "Conflict", back_populates="conflict_transactions"
    )
    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="conflict_transactions"
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    audit_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    tx_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=True
    )
    conflict_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("conflicts.conflict_id"), nullable=True
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("resources.resource_id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effective_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    detail: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", back_populates="audit_events"
    )


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint("from_resource_type", "to_resource_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_resource_type: Mapped[ResourceType] = mapped_column(
        resource_type_enum, nullable=False
    )
    to_resource_type: Mapped[ResourceType] = mapped_column(
        resource_type_enum, nullable=False
    )


class CompensationEvent(Base):
    __tablename__ = "compensation_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tx_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("resources.resource_id"), nullable=False
    )
    release_order: Mapped[int] = mapped_column(Integer, nullable=False)
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AdminPolicy(Base):
    __tablename__ = "admin_policies"

    role: Mapped[UserRole] = mapped_column(
        user_role_enum, primary_key=True
    )
    action: Mapped[str] = mapped_column(String(30), primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)



class AdminConfig(Base):
    __tablename__ = "admin_config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("users.user_id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ─────────────────────────────────────────────
# BED MODEL
# ─────────────────────────────────────────────
class Bed(Base):
    __tablename__ = "beds"

    id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        default=lambda: f"BED-{uuid.uuid4().hex[:6].upper()}",
    )
    bed_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    ward: Mapped[str] = mapped_column(String(100), nullable=False)
    bed_type: Mapped[BedType] = mapped_column(bed_type_enum, nullable=False)
    status: Mapped[BedStatus] = mapped_column(
        bed_status_enum, nullable=False, default=BedStatus.FREE
    )

    # Current occupancy — null when bed is free
    current_patient_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("patients.patient_id", ondelete="SET NULL"),
        nullable=True,
    )
    current_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("transactions.tx_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Readiness tracking
    last_cleaned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Physical location
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    room_number: Mapped[str] = mapped_column(String(10), nullable=False)

    # Special features
    is_isolation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_ventilator_port: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_oxygen_port: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    weight_capacity_kg: Mapped[int] = mapped_column(
        Integer, default=150, nullable=False
    )

    # Maintenance
    maintenance_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    maintenance_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    cleaning_logs: Mapped[List["BedCleaningLog"]] = relationship(
        "BedCleaningLog", back_populates="bed", lazy="selectin"
    )
    assignment_history: Mapped[List["BedAssignment"]] = relationship(
        "BedAssignment", back_populates="bed", lazy="selectin"
    )


# ─────────────────────────────────────────────
# BED CLEANING LOG MODEL
# ─────────────────────────────────────────────
class BedCleaningLog(Base):
    __tablename__ = "bed_cleaning_logs"

    id: Mapped[str] = mapped_column(
        String(30),
        primary_key=True,
        default=lambda: f"CLEAN-{uuid.uuid4().hex[:8].upper()}",
    )
    bed_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("beds.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cleaned_by: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # employee_id
    verified_by: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # employee_id
    status: Mapped[str] = mapped_column(
        String(20), default="IN_PROGRESS", nullable=False
    )  # IN_PROGRESS | COMPLETED | VERIFIED
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    bed: Mapped["Bed"] = relationship("Bed", back_populates="cleaning_logs")


# ─────────────────────────────────────────────
# BED ASSIGNMENT HISTORY MODEL
# ─────────────────────────────────────────────
class BedAssignment(Base):
    __tablename__ = "bed_assignments"

    id: Mapped[str] = mapped_column(
        String(30),
        primary_key=True,
        default=lambda: f"ASSIGN-{uuid.uuid4().hex[:8].upper()}",
    )
    bed_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("beds.id"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("patients.patient_id"), nullable=False
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("transactions.tx_id"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_by: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # employee_id
    release_reason: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # DISCHARGED | TRANSFERRED | EXPIRED | CANCELLED

    bed: Mapped["Bed"] = relationship("Bed", back_populates="assignment_history")

