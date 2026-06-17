# Factory Pattern for creating Listing objects from raw data, and a simple in-memory CatalogRepository

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable
from urllib.parse import quote


@dataclass(slots=True)
class Listing:
    # Core identity
    id: str                          # ITEMID  — VARCHAR(36) PK
    seller_id: str                   # SELLERID — FK → USER(USERID)
    category_id: str                 # CATEGORYID — FK → CATEGORY(CATEGORYID)
    subcategory_id: str              # SUBCATEGORYID — FK → SUBCATEGORY(SUBCATEGORYID)
    title: str                       # TITLE — VARCHAR(100)
    price: Decimal                   # PRICE — FLOAT
    condition: str                   # CONDITION — VARCHAR(10)
    listed_date: str                 # LISTEDDATE — YYYY-MM-DD HH:MM:SS
    description: str                 # DESCRIPTION — VARCHAR(1000)
    likes: int                       # LIKES — INTEGER (≥ 0)
    reserved: bool                   # RESERVED — bool
    buyable: bool                    # BUYABLE — bool
    image_data: str
    buyer_id: str = ""               # BUYERID — FK → USER(USERID), nullable

    # Legacy aliases kept so existing templates/routes that reference
    # .category, .location, .seller still work without changes.
    @property
    def category(self) -> str:
        return self.category_id

    @property
    def location(self) -> str:
        # location is not in the spec; return empty string for compatibility
        return ""

    @property
    def seller(self) -> str:
        return self.seller_id

    @property
    def price_label(self) -> str:
        return f"RM{self.price:,.2f}"


class ListingFactory:
    def create(self, payload: dict[str, object]) -> Listing:
        return Listing(
            id=str(payload["id"]),
            seller_id=str(payload.get("seller_id", payload.get("seller", ""))),
            category_id=str(payload.get("category_id", payload.get("category", ""))),
            subcategory_id=str(payload.get("subcategory_id", payload.get("subcategory", ""))),
            title=str(payload["title"])[:100],
            price=Decimal(str(payload["price"])),
            condition=str(payload.get("condition", ""))[:10],
            listed_date=str(payload.get("listed_date", "")),
            description=str(payload.get("description", ""))[:1000],
            likes=max(0, int(payload.get("likes", 0))),
            reserved=bool(payload.get("reserved", False)),
            buyable=bool(payload.get("buyable", True)),
            image_data=str(payload.get("image_data", "")),
            buyer_id=str(payload.get("buyer_id", "")),
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
        return max((int(listing.id) for listing in self._listings), default=0) + 1

    def count(self) -> int:
        return len(self._listings)

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({listing.category_id for listing in self._listings}))

    def get(self, listing_id: str) -> Listing | None:
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
        matches = [
            candidate for candidate in self._listings
            if candidate.id != listing.id and candidate.category_id == listing.category_id
        ]
        if len(matches) < limit:
            matches.extend(
                candidate for candidate in self._listings
                if candidate.id != listing.id and candidate not in matches
            )
        return tuple(self._sort_results(matches)[:limit])

    def featured(self, limit: int = 4) -> tuple[Listing, ...]:
        return tuple(self._sort_results(list(self._listings))[:limit])

    def _matches(self, listing: Listing, search: str, category: str) -> bool:
        if category and listing.category_id.casefold() != category:
            return False
        if not search:
            return True
        haystack = " ".join(
            [listing.title, listing.category_id, listing.subcategory_id,
             listing.condition, listing.seller_id, listing.description]
        ).casefold()
        return search in haystack

    def _sort_results(self, listings: list[Listing]) -> list[Listing]:
        return sorted(listings, key=lambda item: (item.price, item.title))


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