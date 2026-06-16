from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from flask import current_app

from extensions import db
from models import OrderModel, OrderTracking, Offer


class LogisticsObserver:
    def update(self, event: str, context: dict[str, Any]) -> None:
        raise NotImplementedError


class ReceiptObserver(LogisticsObserver):
    """Minimal receipt observer: placeholder for future persistence or hooks."""

    def update(self, event: str, context: dict[str, Any]) -> None:
        # Receipt data already produced by `payment_gateway.charge` and rendered by checkout.
        return


class TrackingSimulatorObserver(LogisticsObserver):
    """Simulates tracking transitions and persists them to the DB.

    This uses in-process timers and should only be used for demo purposes.
    """

    def __init__(self, delays: tuple[int, ...] | None = None) -> None:
        # delays between transitions in seconds: packed, shipped, delivered
        # Default to 10 seconds per step for testing/demo visibility.
        self.delays = delays or (10, 10, 10)

    def update(self, event: str, context: dict[str, Any]) -> None:
        if event != "payment_confirmed":
            return

        order_id = context.get("order_id")
        if not order_id:
            return

        # create initial tracking row as 'paid'
        with current_app.app_context():
            order = db.session.get(OrderModel, int(order_id))
            if order is None:
                return
            now = datetime.utcnow()
            order.tracking_status = "paid"
            order.tracking_updated_at = now
            db.session.add(OrderTracking(order_id=order.id, status="paid", timestamp=now))
            db.session.commit()

        # spawn background thread to carry out timed transitions
        thread = threading.Thread(target=self._run_transitions, args=(order_id,))
        thread.daemon = True
        thread.start()

    def _run_transitions(self, order_id: int) -> None:
        # sequence of statuses to apply
        statuses = ["packed", "shipped", "delivered"]
        for delay, status in zip(self.delays, statuses):
            time.sleep(delay)
            try:
                with current_app.app_context():
                    order = db.session.get(OrderModel, int(order_id))
                    if order is None:
                        return
                    # only advance forward
                    current = order.tracking_status
                    sequence = ["paid", "packed", "shipped", "delivered"]
                    if sequence.index(status) <= sequence.index(current):
                        continue
                    now = datetime.utcnow()
                    order.tracking_status = status
                    order.tracking_updated_at = now
                    db.session.add(OrderTracking(order_id=order.id, status=status, timestamp=now))
                    db.session.commit()
            except Exception:
                # keep demo robust - swallow exceptions
                return


class LogisticsSubject:
    def __init__(self) -> None:
        self._observers: list[LogisticsObserver] = []

    def attach(self, observer: LogisticsObserver) -> None:
        self._observers.append(observer)

    def detach(self, observer: LogisticsObserver) -> None:
        self._observers.remove(observer)

    def notify(self, event: str, context: dict[str, Any]) -> None:
        for o in list(self._observers):
            try:
                o.update(event, context)
            except Exception:
                # keep observers isolated
                continue


def build_logistics_subject() -> LogisticsSubject:
    subject = LogisticsSubject()
    subject.attach(ReceiptObserver())
    subject.attach(TrackingSimulatorObserver())
    return subject
