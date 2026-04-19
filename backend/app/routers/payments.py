import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.db import engine
from app.models import Order, OrderStatus
from sqlmodel import Session
from app.services.payment import mark_order_paid

router = APIRouter(prefix="/payments", tags=["payments"])


class WebhookBody(BaseModel):
    order_id: int
    event: str = "paid"
    extra: dict[str, Any] | None = None


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    """
    Stub de webhook para integração futura (PSP). MVP: HMAC-SHA256 do corpo bruto com PAYMENT_WEBHOOK_SECRET.
    """
    s = get_settings()
    if s.payment_provider != "webhook_stub":
        raise HTTPException(404, "Webhook não habilitado (PAYMENT_PROVIDER)")
    raw = await request.body()
    secret = s.payment_webhook_secret.encode()
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(expected, x_signature):
        raise HTTPException(401, "Assinatura inválida")
    try:
        body = WebhookBody.model_validate(json.loads(raw.decode("utf-8")))
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(400, "JSON inválido") from e

    with Session(engine) as session:
        order = session.get(Order, body.order_id)
        if not order:
            raise HTTPException(404, "Pedido não encontrado")
        if order.status == OrderStatus.cancelled:
            raise HTTPException(400, "Pedido cancelado")
        mark_order_paid(
            session,
            order,
            provider="webhook_stub",
            payload={"event": body.event, "extra": body.extra},
        )
    return {"ok": True}
