from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from extensions import db
from models import Item, Offer, User


@dataclass(slots=True)
class OfferEvent:
    listing_id: int
    listing_title: str
    offer: Offer


class OfferObserver(Protocol):
    def update(self, event: OfferEvent) -> None:
        ...


class SellerInboxObserver:
    def __init__(self) -> None:
        self.messages: dict[int, list[str]] = defaultdict(list)

    def update(self, event: OfferEvent) -> None:
        buyer = event.offer.buyer_display
        self.messages[event.listing_id].insert(0, f"{buyer} offered {event.offer.amount_label} on {event.listing_title}")


class ActivityFeedObserver:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    def update(self, event: OfferEvent) -> None:
        self.entries.insert(
            0,
            {
                "listing_id": event.listing_id,
                "headline": f"Offer on {event.listing_title}",
                "detail": f"{event.offer.buyer_display} submitted {event.offer.amount_label}.",
                "timestamp": event.offer.created_at,
            },
        )


class OfferBoard:
    def __init__(self, observers: list[OfferObserver] | None = None) -> None:
        self._seller_inbox = SellerInboxObserver()
        self._activity_feed = ActivityFeedObserver()
        self._observers = observers or [self._seller_inbox, self._activity_feed]

    def submit_offer(self, listing: object, buyer_name: str, amount: Decimal, message: str, buyer_id: int | None = None) -> Offer:
        offer = Offer(
            listing_id=int(getattr(listing, "id")),
            buyer_name=buyer_name,
            buyer_id=buyer_id,
            amount=amount,
            message=message,
        )
        db.session.add(offer)
        db.session.commit()
        self._notify(OfferEvent(listing_id=listing.id, listing_title=listing.title, offer=offer))
        return offer

    def history(self, listing_id: int) -> tuple[Offer, ...]:
        return tuple(
            Offer.query.filter_by(listing_id=listing_id)
            .order_by(Offer.created_at.desc())
            .all()
        )

    def recent_activity(self, limit: int = 5) -> tuple[dict[str, object], ...]:
        recent_offers = (
            Offer.query.join(Item, Offer.listing_id == Item.id)
            .order_by(Offer.created_at.desc())
            .limit(limit)
            .all()
        )
        return tuple(
            {
                "listing_id": offer.listing_id,
                "headline": f"Offer on {offer.listing.title}",
                "detail": f"{offer.buyer_display} submitted {offer.amount_label}.",
                "timestamp": offer.created_at,
            }
            for offer in recent_offers
        )

    def seller_messages(self, listing_id: int) -> tuple[str, ...]:
        offers = self.history(listing_id)
        return tuple(f"{offer.buyer_display} offered {offer.amount_label}" for offer in offers)

    def _notify(self, event: OfferEvent) -> None:
        for observer in self._observers:
            observer.update(event)