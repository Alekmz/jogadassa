from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.deps import DbSession, get_current_admin
from app.models import ClipJob, ClipJobStatus, Order, OrderStatus, utcnow
from app.services.payment import mark_order_paid

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreate(BaseModel):
    start_utc: datetime
    end_utc: datetime
    amount_cents: int = Field(ge=0)
    customer_note: str | None = None
    metadata: dict[str, Any] | None = None


class OrderOut(BaseModel):
    id: int
    clip_job_id: int
    amount_cents: int
    status: str
    customer_note: str | None
    clip_status: str | None = None


@router.post("", response_model=OrderOut)
def create_order(body: OrderCreate, session: DbSession):
    """Cliente/quadra cria pedido; clip só processa após pagamento confirmado."""
    if body.end_utc <= body.start_utc:
        raise HTTPException(400, "end_utc deve ser maior que start_utc")
    job = ClipJob(start_utc=body.start_utc, end_utc=body.end_utc)
    session.add(job)
    session.commit()
    session.refresh(job)
    order = Order(
        clip_job_id=job.id,
        amount_cents=body.amount_cents,
        status=OrderStatus.pending_payment,
        customer_note=body.customer_note,
        metadata_json=body.metadata,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return OrderOut(
        id=order.id,
        clip_job_id=order.clip_job_id,
        amount_cents=order.amount_cents,
        status=order.status.value,
        customer_note=order.customer_note,
        clip_status=job.status.value,
    )


@router.get("/admin", response_model=list[OrderOut])
def list_orders(
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    orders = session.exec(select(Order).order_by(Order.id.desc()).limit(200)).all()
    out: list[OrderOut] = []
    for o in orders:
        job = session.get(ClipJob, o.clip_job_id)
        out.append(
            OrderOut(
                id=o.id,
                clip_job_id=o.clip_job_id,
                amount_cents=o.amount_cents,
                status=o.status.value,
                customer_note=o.customer_note,
                clip_status=job.status.value if job else None,
            )
        )
    return out


@router.post("/admin/{order_id}/mark-paid", response_model=OrderOut)
def admin_mark_paid(
    order_id: int,
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    """MVP: confirma pagamento manual (PIX, dinheiro, etc.)."""
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    mark_order_paid(session, order, provider="manual", payload={"source": "admin"})
    session.refresh(order)
    job = session.get(ClipJob, order.clip_job_id)
    return OrderOut(
        id=order.id,
        clip_job_id=order.clip_job_id,
        amount_cents=order.amount_cents,
        status=order.status.value,
        customer_note=order.customer_note,
        clip_status=job.status.value if job else None,
    )


@router.post("/admin/{order_id}/cancel", response_model=OrderOut)
def admin_cancel(
    order_id: int,
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    order.status = OrderStatus.cancelled
    order.updated_at = utcnow()
    session.add(order)
    session.commit()
    session.refresh(order)
    job = session.get(ClipJob, order.clip_job_id)
    return OrderOut(
        id=order.id,
        clip_job_id=order.clip_job_id,
        amount_cents=order.amount_cents,
        status=order.status.value,
        customer_note=order.customer_note,
        clip_status=job.status.value if job else None,
    )
