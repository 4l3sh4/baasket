from __future__ import annotations

from datetime import datetime

from flask import Flask

from extensions import db
from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.checkout_session_state import CheckoutSessionState, to_tracking_status
from models import OrderModel, OrderTracking


class OrderPersistenceObserver:
    """Syncs LogisticsV2 session state into OrderModel / OrderTracking rows."""

    def __init__(self, order_id: int, app: Flask) -> None:
        self.order_id = order_id
        self.app = app

    def update(
        self,
        session: CheckoutSession,
        previous_state: CheckoutSessionState,
    ) -> None:
        tracking_status = to_tracking_status(session.state)
        if tracking_status is None:
            return

        updated_at = session.tracking_updated_at_utc or session.payment_confirmed_at_utc or datetime.utcnow()

        with self.app.app_context():
            order = db.session.get(OrderModel, self.order_id)
            if order is None:
                return

            current = order.tracking_status
            sequence = ["paid", "packed", "shipped", "delivered"]
            if sequence.index(tracking_status) < sequence.index(current):
                return

            order.tracking_status = tracking_status
            order.tracking_updated_at = updated_at
            db.session.add(
                OrderTracking(
                    order_id=order.id,
                    status=tracking_status,
                    timestamp=updated_at,
                )
            )
            db.session.commit()
