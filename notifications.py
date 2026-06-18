from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from extensions import db


class NotificationObserver(ABC):
    """Abstract observer — concrete subclasses decide what to do with an event."""

    @abstractmethod
    def update(self, event: str, context: dict) -> None:
        raise NotImplementedError

class BuyerNotificationObserver(NotificationObserver):
    """Creates an in-app notification for the buyer."""

    def update(self, event: str, context: dict) -> None:
        from models import Notification

        buyer_id = context.get("buyer_id")
        if not buyer_id:
            return

        if event == "offer_accepted":
            msg = f"Your offer of {context.get('amount', '')} on \"{context.get('listing_title', 'an item')}\" was accepted!"
            category = "offer_accepted"
            related_id = context.get("offer_id")
        elif event == "offer_declined":
            msg = f"Your offer of {context.get('amount', '')} on \"{context.get('listing_title', 'an item')}\" was declined."
            category = "offer_declined"
            related_id = None
        else:
            return

        db.session.add(
            Notification(
                user_id=buyer_id,
                message=msg,
                category=category,
                related_id=related_id,
            )
        )


class SellerNotificationObserver(NotificationObserver):
    """Creates an in-app notification for the seller."""

    def update(self, event: str, context: dict) -> None:
        from models import Notification

        seller_id = context.get("seller_id")
        if not seller_id:
            return

        if event == "offer_accepted":
            msg = f"You accepted an offer of {context.get('amount', '')} on \"{context.get('listing_title', 'an item')}\"."
            category = "offer_accepted"
        elif event == "purchase":
            titles = context.get("titles", [])
            title_str = titles[0] if len(titles) == 1 else f"{len(titles)} items"
            msg = f"Your listing \"{title_str}\" was purchased!"
            category = "purchase"
        else:
            return

        db.session.add(Notification(user_id=seller_id, message=msg, category=category))


class AdminNotificationObserver(NotificationObserver):
    """Creates an in-app notification for the admin a report was routed to."""

    def update(self, event: str, context: dict) -> None:
        from models import Notification

        if event != "report_received":
            return

        admin_id = context.get("admin_id")
        if not admin_id:
            return

        reporter = context.get("reporter_name", "A user")
        reason = context.get("reason", "Other")
        listing_title = context.get("listing_title", "a listing")
        msg = f"{reporter} reported \"{listing_title}\" for {reason}."

        db.session.add(
            Notification(
                user_id=admin_id,
                message=msg,
                category="report_received",
            )
        )


class NotificationSubject:
    """Subject that manages observers and dispatches events."""

    def __init__(self) -> None:
        self._observers: list[NotificationObserver] = []

    def attach(self, observer: NotificationObserver) -> None:
        self._observers.append(observer)

    def detach(self, observer: NotificationObserver) -> None:
        self._observers.remove(observer)

    def notify(self, event: str, context: dict) -> None:
        for observer in self._observers:
            observer.update(event, context)


def build_notification_subject() -> NotificationSubject:
    subject = NotificationSubject()
    subject.attach(BuyerNotificationObserver())
    subject.attach(SellerNotificationObserver())
    subject.attach(AdminNotificationObserver())
    return subject