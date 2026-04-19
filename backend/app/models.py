from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClipJobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class ClipJobSource(str, Enum):
    """Origem do job: só replay_trigger aparece na lista pública de seleção."""

    replay_trigger = "replay_trigger"
    admin_manual = "admin_manual"
    legacy = "legacy"


class OrderStatus(str, Enum):
    pending_payment = "pending_payment"
    paid = "paid"
    cancelled = "cancelled"


class ClipJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    start_utc: datetime
    end_utc: datetime
    status: ClipJobStatus = ClipJobStatus.queued
    source: ClipJobSource = Field(default=ClipJobSource.legacy)
    triggered_at_utc: Optional[datetime] = None
    output_relpath: Optional[str] = None
    error_text: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Order(SQLModel, table=True):
    __tablename__ = "customer_order"

    id: Optional[int] = Field(default=None, primary_key=True)
    clip_job_id: int = Field(foreign_key="clipjob.id")
    amount_cents: int = 0
    status: OrderStatus = OrderStatus.pending_payment
    customer_note: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PaymentEvent(SQLModel, table=True):
    __tablename__ = "payment_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="customer_order.id")
    provider: str = "manual"
    payload_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
