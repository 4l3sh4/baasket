from __future__ import annotations

from datetime import datetime

from flask import Flask

from extensions import db
from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.checkout_session_state import CheckoutSessionState, to_tracking_status
from models import ShippingModel, ShippingTracking


class ShippingPersistenceObserver:
    """Syncs LogisticsV2 session state into ShippingModel / ShippingTracking rows."""

    def __init__(self, shipping_id: int, app: Flask) -> None:
        self.shipping_id = shipping_id
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
            shipping = db.session.get(ShippingModel, self.shipping_id)
            if shipping is None:
                return

            current = shipping.tracking_status
            sequence = ["paid", "packed", "shipped", "delivered"]
            if sequence.index(tracking_status) < sequence.index(current):
                return

            shipping.tracking_status = tracking_status
            shipping.tracking_updated_at = updated_at
            db.session.add(
                ShippingTracking(
                    shipping_id=shipping.id,
                    status=tracking_status,
                    timestamp=updated_at,
                )
            )
            db.session.commit()
