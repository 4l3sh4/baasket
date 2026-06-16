from __future__ import annotations

from logistics_v2.automated_tracking_observer import AutomatedTrackingObserver
from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.receipt_generator_observer import ReceiptGeneratorObserver


def wire_standard_observers(
    session: CheckoutSession,
    *,
    step_delay_seconds: float = 10.0,
) -> tuple[ReceiptGeneratorObserver, AutomatedTrackingObserver]:
    """Equivalent to Baasket.LogisticsV2.LogisticsV2Factory.WireStandardObservers."""
    receipt_observer = ReceiptGeneratorObserver()
    tracking_observer = AutomatedTrackingObserver(step_delay_seconds=step_delay_seconds)

    session.attach(receipt_observer)
    session.attach(tracking_observer)

    return receipt_observer, tracking_observer
