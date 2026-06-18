from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from logistics_v2.checkout_receipt import CheckoutReceipt
from logistics_v2.checkout_session_state import CheckoutSessionState, display
from logistics_v2.interfaces import IObserver


class CheckoutSession:
    """Subject for the LogisticsV2 checkout lifecycle."""

    _FORWARD_TRANSITIONS = {
        (CheckoutSessionState.PAYMENT_CONFIRMED, CheckoutSessionState.PACKED),
        (CheckoutSessionState.PACKED, CheckoutSessionState.SHIPPED),
        (CheckoutSessionState.SHIPPED, CheckoutSessionState.DELIVERED),
    }

    def __init__(
        self,
        *,
        session_id: UUID,
        buyer_id: int,
        buyer_name: str,
        buyer_email: str,
        payment_method: str,
        subtotal: Decimal,
        fee: Decimal,
        total: Decimal,
        payment_reference: str,
        offer_id: int | None = None,
        shipping_id: int | None = None,
    ) -> None:
        if buyer_id <= 0:
            raise ValueError("buyer_id must be positive")

        self.session_id = session_id
        self.buyer_id = buyer_id
        self.buyer_name = buyer_name
        self.buyer_email = buyer_email
        self.payment_method = payment_method
        self.subtotal = subtotal
        self.fee = fee
        self.total = total
        self.payment_reference = payment_reference
        self.offer_id = offer_id
        self.shipping_id = shipping_id
        self.state = CheckoutSessionState.CHECKOUT_STARTED
        self.created_at_utc = datetime.utcnow()
        self.payment_confirmed_at_utc: datetime | None = None
        self.tracking_updated_at_utc: datetime | None = None
        self.receipt: CheckoutReceipt | None = None
        self._observers: list[IObserver] = []

    @property
    def status_display(self) -> str:
        return display(self.state)

    def attach(self, observer: IObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: IObserver) -> None:
        self._observers.remove(observer)

    def notify(self, previous_state: CheckoutSessionState) -> None:
        for observer in list(self._observers):
            observer.update(self, previous_state)

    def confirm_payment(self, shipping_id: int | None = None) -> None:
        if self.state is not CheckoutSessionState.CHECKOUT_STARTED:
            raise RuntimeError(
                f"Payment can only be confirmed from {CheckoutSessionState.CHECKOUT_STARTED}. "
                f"Current state: {self.state}."
            )

        previous_state = self.state
        self.state = CheckoutSessionState.PAYMENT_CONFIRMED
        self.payment_confirmed_at_utc = datetime.utcnow()
        if shipping_id is not None:
            self.shipping_id = shipping_id
        self.notify(previous_state)

    def record_receipt(self, receipt: CheckoutReceipt) -> None:
        if self.state is not CheckoutSessionState.PAYMENT_CONFIRMED:
            raise RuntimeError("Receipt can only be recorded after payment is confirmed.")
        if self.receipt is not None:
            raise RuntimeError("Receipt has already been generated for this session.")
        self.receipt = receipt

    def advance_to(self, next_state: CheckoutSessionState) -> None:
        if (self.state, next_state) not in self._FORWARD_TRANSITIONS:
            raise RuntimeError(f"Invalid transition: {self.state} → {next_state}.")

        previous_state = self.state
        self.state = next_state
        self.tracking_updated_at_utc = datetime.utcnow()
        self.notify(previous_state)
