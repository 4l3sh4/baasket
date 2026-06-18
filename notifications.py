from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from extensions import db


# ── Observer Interface ─────────────────────────────────────────────────
class NotificationObserver(ABC):

    @abstractmethod
    def update(self, subject: NotificationSubject) -> None:
        """Called by the Subject when state changes.
        The observer pulls the current state via subject.get_state()."""
        raise NotImplementedError


# ── Subject ────────────────────────────────────────────────────────────
class NotificationSubject:

    def __init__(self) -> None:
        self._observers: list[NotificationObserver] = []
        self._state: dict = {}                

    # ── Attach(in Observer) ────────────────────────────────────────────────
    def attach(self, observer: NotificationObserver) -> None:
        self._observers.append(observer)

    # ── Detach(in Observer) ────────────────────────────────────────────────
    def detach(self, observer: NotificationObserver) -> None:
        self._observers.remove(observer)

    # ── GetState() — observer calls this inside Update() ───────────────────
    def get_state(self) -> dict:
        return self._state

    # ── SetState() — sets new state then fires Notify() ───────────────────
    def set_state(self, event: str, context: dict) -> None:
        self._state = {"event": event, **context}
        self._notify()

    def _notify(self) -> None:
        for observer in self._observers:
            observer.update(self)                

    def notify(self, event: str, context: dict) -> None:
        self.set_state(event, context)


# ── ConcreteObserver 1: Buyer ──────────────────────────────────────────────
class BuyerNotificationObserver(NotificationObserver):

    def update(self, subject: NotificationSubject) -> None:
        from models import Notification

        state = subject.get_state()

        event = state.get("event")
        buyer_id = state.get("buyer_id")
        if not buyer_id:
            return

        if event == "offer_accepted":
            msg = f"Your offer of {state.get('amount', '')} on \"{state.get('listing_title', 'an item')}\" was accepted!"
            category = "offer_accepted"
        elif event == "offer_declined":
            msg = f"Your offer of {state.get('amount', '')} on \"{state.get('listing_title', 'an item')}\" was declined."
            category = "offer_declined"
        else:
            return

        db.session.add(
            Notification(
                user_id=buyer_id,
                message=msg,
                category=category,
                related_id=state.get("offer_id"),
            )
        )


# ── ConcreteObserver 2: Seller ─────────────────────────────────────────────
class SellerNotificationObserver(NotificationObserver):

    def update(self, subject: NotificationSubject) -> None:
        from models import Notification

        state = subject.get_state()

        event = state.get("event")
        seller_id = state.get("seller_id")
        if not seller_id:
            return

        if event == "offer_accepted":
            msg = f"You accepted an offer of {state.get('amount', '')} on \"{state.get('listing_title', 'an item')}\"."
            category = "offer_accepted"
        elif event == "purchase":
            titles = state.get("titles", [])
            title_str = titles[0] if len(titles) == 1 else f"{len(titles)} items"
            msg = f"Your listing \"{title_str}\" was purchased!"
            category = "purchase"
        else:
            return

        db.session.add(Notification(user_id=seller_id, message=msg, category=category))


# ── ConcreteObserver 3: Admin ──────────────────────────────────────────────
class AdminNotificationObserver(NotificationObserver):

    def update(self, subject: NotificationSubject) -> None:
        from models import Notification

        # observerState = subject.GetState()  — GoF UML pull model
        state = subject.get_state()

        if state.get("event") != "report_received":
            return
        admin_id = state.get("admin_id")
        if not admin_id:
            return

        reporter = state.get("reporter_name", "A user")
        reason = state.get("reason", "Other")
        listing_title = state.get("listing_title", "a listing")
        msg = f"{reporter} reported \"{listing_title}\" for {reason}."

        db.session.add(
            Notification(
                user_id=admin_id,
                message=msg,
                category="report_received",
            )
        )


# ── Factory function ───────────────────────────────────────────────────────
def build_notification_subject() -> NotificationSubject:
    subject = NotificationSubject()
    subject.attach(BuyerNotificationObserver())
    subject.attach(SellerNotificationObserver())
    subject.attach(AdminNotificationObserver())
    return subject
