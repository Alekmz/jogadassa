"""
Provedores de pagamento (MVP: confirmação manual + webhook stub).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlmodel import Session

from app.models import Order, OrderStatus, PaymentEvent, utcnow


class PaymentProvider(ABC):
    @abstractmethod
    def name(self) -> str:
        pass


class ManualPaymentProvider(PaymentProvider):
    """Pagamento confirmado pelo admin ou processo externo (PIX manual, etc.)."""

    def name(self) -> str:
        return "manual"


class WebhookStubProvider(PaymentProvider):
    """
    Stub para integração futura: mesmo repositório pode validar HMAC em webhook HTTP.
    """

    def name(self) -> str:
        return "webhook_stub"


def get_provider(kind: str) -> PaymentProvider:
    k = (kind or "manual").lower()
    if k == "webhook_stub":
        return WebhookStubProvider()
    return ManualPaymentProvider()


def mark_order_paid(
    session: Session,
    order: Order,
    provider: str,
    payload: dict[str, Any] | None = None,
) -> None:
    order.status = OrderStatus.paid
    order.updated_at = utcnow()
    session.add(order)
    ev = PaymentEvent(order_id=order.id, provider=provider, payload_json=payload or {})
    session.add(ev)
    session.commit()
    session.refresh(order)
