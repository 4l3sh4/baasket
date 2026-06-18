from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

from flask import Flask

from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.factory import wire_standard_observers
from logistics_v2.order_persistence_observer import OrderPersistenceObserver
from logistics_v2.shipping_observer import ShippingObserver
from payment import PaymentReceipt


def run_checkout_logistics_v2(
    *,
    app: Flask,
    order_id: int,
    buyer_id: int,
    buyer_name: str,
    buyer_email: str,
    payment_method: str,
    receipt: PaymentReceipt,
    offer_id: int | None = None,
    step_delay_seconds: float | None = None,
) -> CheckoutSession:
    """Thin adapter: maps Flask checkout data onto a LogisticsV2 CheckoutSession."""
    delay = step_delay_seconds
    if delay is None:
        delay = float(os.environ.get("LOGISTICS_V2_STEP_DELAY", "10"))

    session = CheckoutSession(
        session_id=uuid4(),
        buyer_id=buyer_id,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        payment_method=payment_method,
        subtotal=Decimal(receipt.subtotal),
        fee=Decimal(receipt.fee),
        total=Decimal(receipt.total),
        payment_reference=receipt.reference,
        offer_id=offer_id,
        order_id=order_id,
    )

    wire_standard_observers(session, step_delay_seconds=delay)
    session.attach(OrderPersistenceObserver(order_id, app))
    session.attach(ShippingObserver(order_id, app))
    session.confirm_payment(order_id=order_id)
    return session
