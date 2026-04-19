from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.deps import DbSession, get_current_admin
from app.models import ClipJob, ClipJobSource, ClipJobStatus, Order, OrderStatus, utcnow
from app.security import create_download_token
from app.services.payment import mark_order_paid

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreate(BaseModel):
    clip_job_id: int = Field(gt=0)
    amount_cents: int = Field(ge=0)
    customer_note: str | None = None
    metadata: dict[str, Any] | None = None


class OrderOut(BaseModel):
    id: int
    clip_job_id: int
    amount_cents: int
    status: str
    customer_note: str | None
    metadata: dict[str, Any] | None = None
    clip_status: str | None = None
    clip_source: str | None = None
    download_token: str | None = None


def _order_out(session: DbSession, order: Order) -> OrderOut:
    job = session.get(ClipJob, order.clip_job_id)
    token = None
    if (
        order.status == OrderStatus.paid
        and job
        and job.status == ClipJobStatus.done
        and job.output_relpath
    ):
        token = create_download_token(job.id)
    return OrderOut(
        id=order.id,
        clip_job_id=order.clip_job_id,
        amount_cents=order.amount_cents,
        status=order.status.value,
        customer_note=order.customer_note,
        metadata=order.metadata_json,
        clip_status=job.status.value if job else None,
        clip_source=job.source.value if job else None,
        download_token=token,
    )


@router.post("", response_model=OrderOut)
def create_order(body: OrderCreate, session: DbSession):
    """Cliente escolhe um replay já exportado (gatilho da quadra)."""
    job = session.get(ClipJob, body.clip_job_id)
    if not job:
        raise HTTPException(404, "Clip não encontrado")
    if job.source != ClipJobSource.replay_trigger:
        raise HTTPException(400, "Só é possível pedir replays gerados pelo gatilho da quadra")
    if job.status != ClipJobStatus.done:
        raise HTTPException(400, "Replay ainda não está pronto; aguarde o processamento")
    existing = session.exec(select(Order).where(Order.clip_job_id == job.id)).first()
    if existing and existing.status in (OrderStatus.pending_payment, OrderStatus.paid):
        raise HTTPException(409, "Já existe pedido ativo para este replay")
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
    return _order_out(session, order)


@router.get("/admin", response_model=list[OrderOut])
def list_orders(
    session: DbSession,
    _admin: Annotated[str, Depends(get_current_admin)],
):
    orders = session.exec(select(Order).order_by(Order.id.desc()).limit(200)).all()
    return [_order_out(session, o) for o in orders]


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
    return _order_out(session, order)


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
    return _order_out(session, order)
