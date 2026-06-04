from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from urllib.parse import quote


@dataclass(slots=True)
class Listing:
    id: int
    title: str
    category: str
    price: Decimal
    condition: str
    location: str
    seller: str
    description: str
    image_data: str
    kind: str = "standard"
    tags: tuple[str, ...] = ()

    @property
    def badge(self) -> str:
        return {"featured": "Featured", "fresh": "Just In", "limited": "Limited Stock"}.get(self.kind, "Top Pick")

    @property
    def price_label(self) -> str:
        return f"S${self.price:,.2f}"


@dataclass(slots=True)
class FeaturedListing(Listing):
    kind: str = "featured"


@dataclass(slots=True)
class FreshListing(Listing):
    kind: str = "fresh"


@dataclass(slots=True)
class LimitedListing(Listing):
    kind: str = "limited"


class ListingFactory:
    def create(self, payload: dict[str, object]) -> Listing:
        kind = str(payload.get("kind", "standard")).lower()
        listing_class = {"featured": FeaturedListing, "fresh": FreshListing, "limited": LimitedListing}.get(kind, Listing)

        return listing_class(
            id=int(payload["id"]),
            title=str(payload["title"]),
            category=str(payload["category"]),
            price=Decimal(str(payload["price"])),
            condition=str(payload["condition"]),
            location=str(payload["location"]),
            seller=str(payload["seller"]),
            description=str(payload["description"]),
            image_data=str(payload["image_data"]),
            kind=kind,
            tags=tuple(str(tag) for tag in payload.get("tags", ())),
        )


class CatalogRepository:
    def __init__(self, listings: Iterable[Listing]) -> None:
        self._listings = list(listings)

    def all(self) -> tuple[Listing, ...]:
        return tuple(self._listings)

    def add(self, listing: Listing) -> Listing:
        self._listings.insert(0, listing)
        return listing

    def next_id(self) -> int:
        return max((listing.id for listing in self._listings), default=0) + 1

    def count(self) -> int:
        return len(self._listings)

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({listing.category for listing in self._listings}))

    def get(self, listing_id: int) -> Listing | None:
        for listing in self._listings:
            if listing.id == listing_id:
                return listing
        return None

    def search(self, search: str = "", category: str = "") -> tuple[Listing, ...]:
        search_term = search.casefold().strip()
        category_term = category.casefold().strip()
        results = [listing for listing in self._listings if self._matches(listing, search_term, category_term)]
        return tuple(self._sort_results(results))

    def related(self, listing: Listing, limit: int = 3) -> tuple[Listing, ...]:
        matches = [candidate for candidate in self._listings if candidate.id != listing.id and candidate.category == listing.category]
        if len(matches) < limit:
            matches.extend(candidate for candidate in self._listings if candidate.id != listing.id and candidate not in matches)
        return tuple(self._sort_results(matches)[:limit])

    def featured(self, limit: int = 4) -> tuple[Listing, ...]:
        featured_listings = [listing for listing in self._listings if listing.kind == "featured"]
        return tuple(self._sort_results(featured_listings)[:limit])

    def _matches(self, listing: Listing, search: str, category: str) -> bool:
        if category and listing.category.casefold() != category:
            return False
        if not search:
            return True
        haystack = " ".join(
            [listing.title, listing.category, listing.condition, listing.location, listing.seller, listing.description, " ".join(listing.tags)]
        ).casefold()
        return search in haystack

    def _sort_results(self, listings: list[Listing]) -> list[Listing]:
        priority = {"featured": 0, "fresh": 1, "limited": 2, "standard": 3}
        return sorted(listings, key=lambda item: (priority.get(item.kind, 9), item.price, item.title))


def _build_art(title: str, accent_a: str, accent_b: str) -> str:
    initials = "".join(part[0] for part in title.split()[:2]).upper()
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600'>
      <defs>
        <linearGradient id='paint' x1='0%' y1='0%' x2='100%' y2='100%'>
          <stop offset='0%' stop-color='{accent_a}' />
          <stop offset='100%' stop-color='{accent_b}' />
        </linearGradient>
      </defs>
      <rect width='800' height='600' rx='48' fill='url(#paint)' />
      <circle cx='660' cy='120' r='92' fill='rgba(255,255,255,0.18)' />
      <circle cx='120' cy='470' r='128' fill='rgba(255,255,255,0.12)' />
      <rect x='90' y='100' width='620' height='400' rx='40' fill='rgba(255,255,255,0.14)' stroke='rgba(255,255,255,0.28)' />
      <text x='125' y='215' fill='white' font-size='120' font-family='Georgia, serif' font-weight='700'>{initials}</text>
      <text x='125' y='300' fill='white' font-size='46' font-family='Trebuchet MS, sans-serif' letter-spacing='4'>{title}</text>
    </svg>
    """.strip()
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def build_seeded_catalog(factory: ListingFactory) -> CatalogRepository:
    raw_listings = [
        {"id": 1, "title": "Retro Film Camera", "category": "Electronics", "price": "189.00", "condition": "Like new", "location": "Downtown", "seller": "Mika Studio", "description": "Manual film camera with a clean lens, extra batteries, and a leather strap.", "kind": "featured", "tags": ("camera", "vintage", "photo"), "image_data": _build_art("Retro Film Camera", "#ff7a59", "#ffb347")},
        {"id": 2, "title": "Minimal Desk Lamp", "category": "Home", "price": "48.50", "condition": "Good", "location": "Bukit Timah", "seller": "Nora Loft", "description": "Warm LED lamp with adjustable arm and matte white finish.", "kind": "fresh", "tags": ("home", "desk", "light"), "image_data": _build_art("Minimal Desk Lamp", "#1f6f78", "#72c9c4")},
        {"id": 3, "title": "Streetwear Overshirt", "category": "Fashion", "price": "72.00", "condition": "New with tags", "location": "Kallang", "seller": "North Loop", "description": "Relaxed fit overshirt that layers well over tees and hoodies.", "kind": "featured", "tags": ("fashion", "jacket", "menswear"), "image_data": _build_art("Streetwear Overshirt", "#493657", "#8e5cff")},
        {"id": 4, "title": "Mechanical Keyboard", "category": "Electronics", "price": "128.90", "condition": "Excellent", "location": "Queenstown", "seller": "Keycraft", "description": "Hot-swappable keyboard with tactile switches and custom keycaps.", "kind": "limited", "tags": ("keyboard", "pc", "gaming"), "image_data": _build_art("Mechanical Keyboard", "#23395d", "#4cc9f0")},
        {"id": 5, "title": "Electric Scooter", "category": "Travel", "price": "399.00", "condition": "Good", "location": "Tampines", "seller": "Motion Mart", "description": "Foldable scooter with a bright display and new brake pads.", "kind": "featured", "tags": ("travel", "ride", "urban"), "image_data": _build_art("Electric Scooter", "#aa4465", "#f48c06")},
        {"id": 6, "title": "Vinyl Record Player", "category": "Collectibles", "price": "215.00", "condition": "Very good", "location": "Bugis", "seller": "Analog House", "description": "Classic turntable with stereo speakers and a dust cover.", "kind": "fresh", "tags": ("music", "vinyl", "retro"), "image_data": _build_art("Vinyl Record Player", "#4f6d7a", "#89b0ae")},
        {"id": 7, "title": "Trail Backpack", "category": "Outdoors", "price": "58.00", "condition": "Good", "location": "Jurong East", "seller": "Peak Supply", "description": "Lightweight pack with water resistance and padded straps.", "kind": "standard", "tags": ("bag", "hiking", "camp"), "image_data": _build_art("Trail Backpack", "#2d6a4f", "#95d5b2")},
        {"id": 8, "title": "Smart Watch Series", "category": "Wearables", "price": "165.75", "condition": "Like new", "location": "Bedok", "seller": "Pulse Gear", "description": "Fitness-ready smartwatch with GPS, sleep tracking, and fast charging.", "kind": "limited", "tags": ("watch", "health", "fitness"), "image_data": _build_art("Smart Watch Series", "#1d3557", "#457b9d")},
    ]

    return CatalogRepository(factory.create(payload) for payload in raw_listings)