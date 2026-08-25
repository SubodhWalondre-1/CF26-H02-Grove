import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperationRecord(Base):
    __tablename__ = "operation_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tx_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
    )
    audit_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
