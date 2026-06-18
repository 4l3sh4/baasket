# Observer Pattern for offer events. When an offer is submitted,
# observers are notified and can create notifications for the seller and activity feed entries.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from extensions import db
from models import Item, Offer, User


def get_redeemable_offer(offer_id: int, buyer_id: int) -> Offer | None:
    """Return an accepted, unredeemed offer the buyer may purchase at offer price.

    Works for both delivery listings (buyable=True) and meet-up-only listings
    (buyable=False, since buyable only reflects whether a Delivery deal method
    is attached).  The only hard gate is that the listing must not already have
    been sold (buyer_id is None).
    """
    offer = db.session.get(Offer, offer_id)
    if offer is None:
        return None
    if offer.sender_id != buyer_id:
        return None
    if offer.acceptanceStatus != "accepted":
        return None
    if offer.redeemed:
        return None

    listing = db.session.get(Item, offer.listing_id)
    if listing is None or listing.buyer_id is not None:
        return None

    return offer


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

    def submit_offer(self, listing: object, amount: Decimal, sender_id: int | None = None, receiver_id: int | None = None) -> Offer:
        offer = Offer(
            listing_id=int(getattr(listing, "id")),
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount=amount,
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

    def seller_messages(self, listing_id: int) -> tuple[str, ...]:
        offers = self.history(listing_id)
        return tuple(f"{offer.buyer_display} offered {offer.amount_label}" for offer in offers)

    def activity_feed(self, limit: int = 8) -> tuple[dict[str, object], ...]:
        return tuple(self._activity_feed.entries[:limit])

    def _notify(self, event: OfferEvent) -> None:
        for observer in self._observers:
            observer.update(event)