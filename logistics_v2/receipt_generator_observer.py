from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from logistics_v2.checkout_receipt import CheckoutReceipt
from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.checkout_session_state import CheckoutSessionState, display


class ReceiptGeneratorObserver:
    def update(
        self,
        session: CheckoutSession,
        previous_state: CheckoutSessionState,
    ) -> None:
        if previous_state is not CheckoutSessionState.CHECKOUT_STARTED:
            return
        if session.state is not CheckoutSessionState.PAYMENT_CONFIRMED:
            return

        issued_at = session.payment_confirmed_at_utc or datetime.utcnow()
        receipt = CheckoutReceipt(
            reference=session.payment_reference,
            buyer_name=session.buyer_name,
            buyer_email=session.buyer_email,
            payment_method=session.payment_method,
            subtotal=Decimal(session.subtotal),
            fee=Decimal(session.fee),
            total=Decimal(session.total),
            issued_at_utc=issued_at,
            message=(
                f"{display(CheckoutSessionState.PAYMENT_CONFIRMED)} — "
                f"payment approved for {session.buyer_name}."
            ),
        )
        session.record_receipt(receipt)
