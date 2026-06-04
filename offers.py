from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from extensions import db
from models import ListingModel, OfferModel


@dataclass(slots=True)
class Offer:
    listing_id: int
    buyer_name: str
    amount: Decimal
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def amount_label(self) -> str:
        return f"S${self.amount:,.2f}"


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
        self.messages[event.listing_id].insert(0, f"{event.offer.buyer_name} offered {event.offer.amount_label} on {event.listing_title}")


class ActivityFeedObserver:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    def update(self, event: OfferEvent) -> None:
        self.entries.insert(
            0,
            {
                "listing_id": event.listing_id,
                "headline": f"Offer on {event.listing_title}",
                "detail": f"{event.offer.buyer_name} submitted {event.offer.amount_label}.",
                "timestamp": event.offer.created_at,
            },
        )


class OfferBoard:
    def __init__(self, observers: list[OfferObserver] | None = None) -> None:
        self._seller_inbox = SellerInboxObserver()
        self._activity_feed = ActivityFeedObserver()
        self._observers = observers or [self._seller_inbox, self._activity_feed]

    def submit_offer(self, listing: object, buyer_name: str, amount: Decimal, message: str) -> OfferModel:
        offer = OfferModel(
            listing_id=int(getattr(listing, "id")),
            buyer_name=buyer_name,
            amount=amount,
            message=message,
        )
        db.session.add(offer)
        db.session.commit()
        self._notify(OfferEvent(listing_id=listing.id, listing_title=listing.title, offer=offer))
        return offer

    def history(self, listing_id: int) -> tuple[OfferModel, ...]:
        return tuple(
            OfferModel.query.filter_by(listing_id=listing_id)
            .order_by(OfferModel.created_at.desc())
            .all()
        )

    def recent_activity(self, limit: int = 5) -> tuple[dict[str, object], ...]:
        recent_offers = (
            OfferModel.query.join(ListingModel, OfferModel.listing_id == ListingModel.id)
            .order_by(OfferModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return tuple(
            {
                "listing_id": offer.listing_id,
                "headline": f"Offer on {offer.listing.title}",
                "detail": f"{offer.buyer_name} submitted {offer.amount_label}.",
                "timestamp": offer.created_at,
            }
            for offer in recent_offers
        )

    def seller_messages(self, listing_id: int) -> tuple[str, ...]:
        offers = self.history(listing_id)
        return tuple(f"{offer.buyer_name} offered {offer.amount_label}" for offer in offers)

    def _notify(self, event: OfferEvent) -> None:
        for observer in self._observers:
            observer.update(event)