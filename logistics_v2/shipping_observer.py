from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4

from flask import Flask

from extensions import db
from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.checkout_session_state import CheckoutSessionState, to_tracking_status
from models import OrderModel, Payment, Shipping


class ShippingObserver:
    """Observer that drives the UML Shipping entity (updateTrackingInfo / confirmDelivery)."""

    _CARRIER = "Baasket Logistics"

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

        with self.app.app_context():
            order = db.session.get(OrderModel, self.order_id)
            if order is None:
                return

            shipping = (
                db.session.get(Shipping, order.shipping_id)
                if order.shipping_id
                else None
            )

            if tracking_status == "paid" and shipping is None:
                shipping = Shipping(
                    shippingID=str(uuid4()),
                    order_id=order.id,
                    status="created",
                )
                tracking_ref = f"BX-{order.reference}"
                shipping.updateTrackingInfo(
                    self._CARRIER,
                    tracking_ref,
                    estimated_delivery=date.today() + timedelta(days=3),
                )
                db.session.add(shipping)
                order.shipping_id = shipping.shippingID

                if order.payment_id:
                    payment = db.session.get(Payment, order.payment_id)
                    if payment is not None:
                        payment.shipping_id = shipping.shippingID

            elif shipping is not None:
                tracking_ref = f"BX-{order.reference}"
                if tracking_status == "packed":
                    shipping.updateTrackingInfo(
                        self._CARRIER,
                        f"{tracking_ref}-PK",
                    )
                elif tracking_status == "shipped":
                    shipping.updateTrackingInfo(
                        self._CARRIER,
                        f"{tracking_ref}-SH",
                    )
                elif tracking_status == "delivered":
                    shipping.confirmDelivery()

            db.session.commit()
