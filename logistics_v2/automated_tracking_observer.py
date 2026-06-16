from __future__ import annotations

import threading
import time
from uuid import UUID

from logistics_v2.checkout_session import CheckoutSession
from logistics_v2.checkout_session_state import CheckoutSessionState


class AutomatedTrackingObserver:
    """Timed 💳 Paid → 📦 Packed → 🚚 Shipped → ✅ Delivered simulation."""

    _TRACKING_SEQUENCE = (
        CheckoutSessionState.PACKED,
        CheckoutSessionState.SHIPPED,
        CheckoutSessionState.DELIVERED,
    )

    def __init__(self, step_delay_seconds: float = 10.0) -> None:
        self.step_delay_seconds = step_delay_seconds
        self._gate = threading.Lock()
        self._active: set[UUID] = set()

    def update(
        self,
        session: CheckoutSession,
        previous_state: CheckoutSessionState,
    ) -> None:
        if previous_state is not CheckoutSessionState.CHECKOUT_STARTED:
            return
        if session.state is not CheckoutSessionState.PAYMENT_CONFIRMED:
            return

        with self._gate:
            if session.session_id in self._active:
                return
            self._active.add(session.session_id)

        thread = threading.Thread(
            target=self._run_simulation,
            args=(session.session_id, session),
            daemon=True,
        )
        thread.start()

    def _run_simulation(self, session_id: UUID, session: CheckoutSession) -> None:
        try:
            for next_state in self._TRACKING_SEQUENCE:
                time.sleep(self.step_delay_seconds)
                session.advance_to(next_state)
        except Exception:
            return
        finally:
            with self._gate:
                self._active.discard(session_id)

    def cancel_session(self, session_id: UUID) -> None:
        with self._gate:
            self._active.discard(session_id)
