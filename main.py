from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, text
from werkzeug.utils import secure_filename
from typing import TypedDict

from catalog import _build_art
from extensions import db, login_manager
from models import Item, Like, ListingImage, Notification, Offer, OrderItemModel, OrderModel, User, ChatSession, Message, Review, ReviewImage, Report
from notifications import build_notification_subject
from logistics_v2.flask_adapter import run_checkout_logistics_v2
from offers import OfferBoard, get_redeemable_offer
from payment import PaymentReceipt, build_payment_gateway


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
LISTING_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "listings"
PROFILE_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "pfp"
REVIEW_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "reviews"

# ── Category / subcategory taxonomy ──────────────────────────────────────────
CATEGORIES_MAP: dict[str, list[str]] = {
	"Computers & Tech": [
		"Desktops",
		"Laptops & Notebooks",
		"Parts & Accessories",
		"Printers, Scanners & Copiers",
		"Business & Business Technology",
	],
	"Mobile Phones & Gadgets": [
		"Mobile Phones",
		"Tablets",
		"E-Readers",
		"Wearables & Smart Watches",
		"Mobile & Gadget Accessories",
		"Walkie-Talkie",
		"Other Gadgets",
	],
	"Women's Fashion": [
		"Activewear",
		"Maternity Wear",
		"Tops",
		"Bottoms",
		"Dresses & Sets",
		"Footwear",
		"Swimwear",
		"Muslimah Fashion",
		"Coats, Jackets and Outerwear",
		"Bags & Wallets",
		"Jewelry & Organisers",
		"Watches & Accessories",
		"New Undergarments & Loungewear",
	],
	"Men's Fashion": [
		"Activewear",
		"Tops & Sets",
		"Bottoms",
		"Footwear",
		"Muslim Wear",
		"Coats, Jackets & Outerwear",
		"Bags",
		"Watches & Accessories",
	],
	"Beauty & Personal Care": [
		"Sanitisers & Disinfectants",
		"Hands & Nails",
		"Ear Care",
		"Vision Care",
		"Foot Care",
		"Oral Care",
		"Sanitary Hygiene",
		"Fragrance & Deodorants",
		"Bath & Body",
		"Face",
		"Hair",
		"Men's Grooming",
	],
	"Luxury": [
		"Bags & Wallets",
		"Apparel",
		"Accessories",
		"Watches",
		"Sneakers & Footwear",
	],
	"Video Gaming": [
		"Video Game Consoles",
		"Video Games",
		"Gaming Accessories",
	],
	"Audio": [
		"Earphones",
		"Headphones & Headsets",
		"Microphones",
		"Voice Recorders",
		"Portable Music Players",
		"Portable Audio Accessories",
		"Soundbars, Speakers & Amplifiers",
		"Other Audio Equipment",
	],
	"Photography": [
		"Cameras",
		"Lens & Kits",
		"Drones",
		"Video Cameras",
		"Photography Accessories",
	],
	"Furniture & Home Living": [
		"Furniture",
		"Outdoor Furniture",
		"Lighting & Fans",
		"Home Decor",
		"Home Fragrance",
		"Bedding & Towels",
		"Bathroom & Kitchen Fixtures",
		"Home Improvement & Organisation",
		"Cleaning & Homecare Supplies",
		"Kitchenware & Tableware",
		"Security & Locks",
		"Gardening",
	],
	"TV & Home Appliances": [
		"TV & Entertainment",
		"Kitchen Appliances",
		"Air Conditioners & Heating",
		"Washing Machines & Dryers",
		"Vacuum Cleaner & Housekeeping",
		"Water Heater & Instant Showers",
		"Air Purifiers & Dehumidifiers",
		"Electrical, Adapters & Sockets",
		"Iron & Steamers",
		"Other Home Appliances",
	],
	"Babies & Kids": [
		"Babies & Kids Fashion",
		"Baby Nursery & Kids Furniture",
		"Going Out",
		"Bathing & Changing",
		"Nursing & Feeding",
		"Baby Monitors",
		"Maternity Care",
		"Infant Playtime",
	],
	"Hobbies & Toys": [
		"Toys & Games",
		"Music & Media",
		"Books & Magazines",
		"Stationary & Craft",
		"Collectibles & Memorabilia",
		"Travel",
	],
	"Health & Nutrition": [
		"Insect Repellent",
		"Massage Devices",
		"Assistive & Rehabilatory Aids",
		"Face Masks & Face Shields",
		"Thermometers",
		"Medical Supplies & Tools",
		"Health Supplements",
		"Braces, Support & Protection",
		"Health Monitors & Weighing Scales",
	],
	"Sports Equipment": [
		"Sports & Games",
		"Exercise & Fitness",
		"Bicycles & Parts",
		"Fishing",
		"Hiking & Camping",
		"Other Sports Equipment and Supplies",
	],
	"Auto Accessories": [],
	"Pet Supplies": [
		"Homes & Other Pet Accessories",
		"Pet Food",
		"Health & Grooming",
	],
}

VALID_CATEGORIES: frozenset[str] = frozenset(CATEGORIES_MAP.keys())

# PNG icon filenames for each category (served from static/assets/categories/, shown in the carousel)
CATEGORY_ICONS: dict[str, str] = {
	"Computers & Tech":        "tech.png",
	"Mobile Phones & Gadgets": "gadget.png",
	"Women's Fashion":         "womens_fashion.png",
	"Men's Fashion":           "mens_fashion.png",
	"Beauty & Personal Care":  "beauty.png",
	"Luxury":                  "luxury.png",
	"Video Gaming":            "gaming.png",
	"Audio":                   "audio.png",
	"Photography":             "photography.png",
	"Furniture & Home Living": "furniture.png",
	"TV & Home Appliances":    "TV.png",
	"Babies & Kids":           "kids.png",
	"Hobbies & Toys":          "toys.png",
	"Health & Nutrition":      "health.png",
	"Sports Equipment":        "sports.png",
	"Auto Accessories":        "auto.png",
	"Pet Supplies":            "pet.png",
}
CATEGORY_ICON_FALLBACK = "tech.png"

# Conditions as stored in the database (condition field is VARCHAR(10), so values are truncated)
# These match what sell.html offers, after the [:10] slice applied in the sell route.
BROWSE_CONDITIONS: list[str] = [
	"Brand New",   # 9  chars – unchanged
	"Like New",    # 8  chars – unchanged
	"Lightly Us",  # truncated from "Lightly Used"
	"Well Used",   # 9  chars – unchanged
	"Heavily Us",  # truncated from "Heavily Used"
	"For Parts",   # 9  chars – unchanged
]


def _build_category_list() -> list[dict[str, str]]:
	"""Return ordered list of dicts with name + icon for the carousel."""
	return [
		{
			"name": name,
			"icon": url_for(
				"static",
				filename=f"assets/categories/{CATEGORY_ICONS.get(name, CATEGORY_ICON_FALLBACK)}",
			),
		}
		for name in CATEGORIES_MAP
	]


def _ensure_storage() -> None:
	INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
	LISTING_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
	PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
	REVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _save_upload(file_storage, folder: Path) -> str | None:
	if not file_storage or not getattr(file_storage, "filename", ""):
		return None
	original_name = secure_filename(file_storage.filename)
	if not original_name:
		return None
	unique_name = f"{uuid4().hex}_{original_name}"
	destination = folder / unique_name
	file_storage.save(destination)
	return f"uploads/{folder.name}/{unique_name}"


def _save_uploads(file_storages, folder: Path, limit: int) -> list[str]:
	"""Save up to `limit` uploaded files (skipping any with no filename) and
	return their relative static paths, in the same order they were received."""
	saved: list[str] = []
	for file_storage in file_storages:
		if len(saved) >= limit:
			break
		saved_path = _save_upload(file_storage, folder)
		if saved_path:
			saved.append(saved_path)
	return saved


def _money(value: object) -> str:
	amount = Decimal(str(value))
	return f"RM{amount:,.2f}"


def _timeago(value: object) -> str:
	"""Render a datetime as a relative 'x ago' string, e.g. for listing posted
	times and review timestamps."""
	if not isinstance(value, datetime):
		return ""
	delta = datetime.utcnow() - value
	seconds = int(delta.total_seconds())
	if seconds < 60:
		return "moments ago"
	minutes = seconds // 60
	if minutes < 60:
		return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
	hours = minutes // 60
	if hours < 24:
		return f"{hours} hour{'s' if hours != 1 else ''} ago"
	days = hours // 24
	if days < 30:
		return f"{days} day{'s' if days != 1 else ''} ago"
	months = days // 30
	if months < 12:
		return f"{months} month{'s' if months != 1 else ''} ago"
	years = months // 12
	return f"{years} year{'s' if years != 1 else ''} ago"


def _safe_redirect_target(candidate: str | None, fallback: str) -> str:
	"""Only follow same-site relative paths from a posted 'next' value (used
	by the like button so it can return the shopper to whichever grid or
	detail page they clicked it from); anything else falls back to a
	known-safe target instead of redirecting off-site."""
	if candidate and candidate.startswith("/") and not candidate.startswith("//"):
		return candidate
	return fallback


class CartLine(TypedDict):
	listing: Item
	quantity: int
	line_total: Decimal


class OrderLine(TypedDict):
	listing: Item
	quantity: int
	line_total: Decimal
	unit_price: Decimal


def _persist_order(
	*,
	buyer_name: str,
	buyer_email: str,
	receipt: PaymentReceipt,
	note: str,
	lines: list[OrderLine],
	buyer_id: int | None = None,
	offer_id: int | None = None,
) -> OrderModel:
	order = OrderModel()
	order.buyer_id = buyer_id
	order.buyer_name = buyer_name
	order.buyer_email = buyer_email
	order.payment_method = receipt.strategy_code
	order.subtotal = receipt.subtotal
	order.fee = receipt.fee
	order.total = receipt.total
	order.reference = receipt.reference
	order.note = note
	order.offer_id = offer_id
	db.session.add(order)
	db.session.flush()

	for line in lines:
		listing = line["listing"]
		order_item = OrderItemModel()
		order_item.order_id = order.id
		order_item.listing_id = listing.id
		order_item.title = listing.title
		order_item.quantity = line["quantity"]
		order_item.unit_price = line["unit_price"]
		order_item.line_total = line["line_total"]
		db.session.add(order_item)

	return order


def _notify_sellers_purchase(lines: list[OrderLine], notification_subject: object) -> None:
	seller_titles: dict[int, list[str]] = {}
	for line in lines:
		listing = line["listing"]
		seller_titles.setdefault(listing.seller_id, []).append(listing.title)
	for seller_id, titles in seller_titles.items():
		notification_subject.notify("purchase", {
			"seller_id": seller_id,
			"titles": titles,
		})


def _mark_listings_sold(lines: list[OrderLine], buyer_id: int) -> None:
	for line in lines:
		listing = line["listing"]
		listing.buyer_id = buyer_id
		listing.buyable = False


def _create_cart_lines() -> tuple[list[CartLine], Decimal]:
	raw_ids = session.get("cart", [])
	cart_ids = [int(listing_id) for listing_id in raw_ids]
	counts = Counter(cart_ids)
	lines: list[CartLine] = []
	subtotal = Decimal("0.00")
	sellable_ids: set[int] = set()

	for listing_id, quantity in counts.items():
		listing = db.session.get(Item, listing_id)
		if listing is None or listing.buyer_id is not None:
			# Missing or already-sold listings are dropped from the basket
			# instead of being shown or charged for.
			continue
		sellable_ids.add(listing_id)
		line_total = Decimal(listing.price) * quantity
		subtotal += line_total
		lines.append({"listing": listing, "quantity": quantity, "line_total": line_total})

	# Keep the session cart in sync so the basket badge/count and any later
	# checkout attempt never reference a listing that's no longer available.
	cleaned_ids = [listing_id for listing_id in cart_ids if listing_id in sellable_ids]
	if cleaned_ids != cart_ids:
		session["cart"] = cleaned_ids
		session.modified = True

	return lines, subtotal


def _search_listings(search: str = "", category: str = "") -> list[Item]:
	query = Item.query.filter(Item.buyer_id.is_(None))
	if category:
		query = query.filter(Item.category == category)
	if search:
		pattern = f"%{search}%"
		query = query.filter(
			or_(
				Item.title.ilike(pattern),
				Item.category.ilike(pattern),
				Item.condition.ilike(pattern),
				Item.location.ilike(pattern),
				Item.description.ilike(pattern),
			)
		)
	return query.order_by(Item.created_at.desc()).all()


def _featured_listings(limit: int = 4) -> list[Item]:
	return (
		Item.query.filter(Item.buyer_id.is_(None))
		.order_by(Item.created_at.desc())
		.limit(limit)
		.all()
	)


def _related_listings(listing: Item, limit: int = 3) -> list[Item]:
	query = (
		Item.query.filter(Item.id != listing.id, Item.category == listing.category)
		.order_by(Item.created_at.desc())
		.limit(limit)
	)
	results = query.all()
	if len(results) < limit:
		fallback = (
			Item.query.filter(Item.id != listing.id)
			.order_by(Item.created_at.desc())
			.all()
		)
		for candidate in fallback:
			if candidate not in results:
				results.append(candidate)
			if len(results) >= limit:
				break
	return results[:limit]


def _seller_profile_stats(seller_id: int) -> dict[str, object]:
	"""Stats shown on the 'Meet the seller' card. Everything here comes from
	real rows (listings, orders, reviews) rather than placeholder numbers."""
	seller = db.session.get(User, seller_id)
	active_listings = Item.query.filter_by(seller_id=seller_id, buyer_id=None).count()
	sales_count = (
		OrderItemModel.query.join(Item, OrderItemModel.listing_id == Item.id)
		.filter(Item.seller_id == seller_id)
		.count()
	)
	reviews = Review.query.filter_by(seller_id=seller_id).all()
	rating_count = len(reviews)
	rating_avg = (sum(review.ratingValue for review in reviews) / rating_count) if rating_count else 0.0
	return {
		"seller": seller,
		"active_listings": active_listings,
		"sales_count": sales_count,
		"rating_avg": rating_avg,
		"rating_count": rating_count,
		"member_since": seller.created_at.strftime("%b %Y") if seller else "",
	}


def _seller_reviews(seller_id: int, limit: int = 5) -> list[Review]:
	return (
		Review.query.filter_by(seller_id=seller_id)
		.order_by(Review.created_at.desc())
		.limit(limit)
		.all()
	)


def _related_search_terms(listing: Item, limit: int = 8) -> list[dict[str, str]]:
	"""Build a small set of taxonomy-derived search suggestions for the
	'What others also search for' row. Baasket has no search-suggestion log
	to draw from, so this leans on the category/subcategory tree instead of
	inventing numbers."""
	terms: list[dict[str, str]] = []
	seen: set[str] = set()

	def _add(label: str, sub: str = "") -> None:
		key = label.casefold().strip()
		if not key or key in seen:
			return
		seen.add(key)
		terms.append({"label": label, "sub": sub})

	if listing.subcategory:
		_add(listing.subcategory, listing.subcategory)
	for sibling in CATEGORIES_MAP.get(listing.category, []):
		if len(terms) >= limit:
			break
		_add(sibling, sibling)
	_add(listing.category)
	return terms[:limit]


def _listing_stats_for_user(user_id: int) -> dict[str, int]:
	listings = Item.query.filter_by(seller_id=user_id).all()
	offer_count = sum(len(listing.offers) for listing in listings)
	return {
		"listings": len(listings),
		"offers": offer_count,
	}


def _sales_history_for_user(user_id: int) -> list[dict[str, object]]:
	order_items = (
		OrderItemModel.query.join(Item, OrderItemModel.listing_id == Item.id)
		.join(OrderModel, OrderItemModel.order_id == OrderModel.id)
		.filter(Item.seller_id == user_id)
		.order_by(OrderModel.created_at.desc(), OrderItemModel.id.desc())
		.all()
	)
	return [
		{
			"order": item.order,
			"item": item,
			"listing": db.session.get(Item, item.listing_id),
		}
		for item in order_items
	]


def _orders_for_buyer(user_id: int) -> list[OrderModel]:
	"""All orders placed by this user, current and past, most recent first."""
	return (
		OrderModel.query.filter_by(buyer_id=user_id)
		.order_by(OrderModel.created_at.desc())
		.all()
	)


def _liked_listings_for_user(user_id: int) -> list[Item]:
	"""A user's own liked items, most recently liked first. Only ever
	filtered by the requesting user's id — there is no route that exposes
	*who* liked a listing, so this stays private to each shopper."""
	return (
		Item.query.join(Like, Like.listing_id == Item.id)
		.filter(Like.user_id == user_id)
		.order_by(Like.created_at.desc())
		.all()
	)


def _seed_database() -> None:
	if User.query.count() == 0:
		demo_user = User()
		demo_user.username = "baasket"
		demo_user.email = "hello@baasket.local"
		demo_user.bio = "Baasket demo storefront"
		demo_user.set_password("baasket123")
		demo_user.role = "user"
		db.session.add(demo_user)
		db.session.flush()
	else:
		demo_user = User.query.filter_by(username="baasket").first() or User.query.first()

	# Demo catalog listings are intentionally not generated here — the
	# database starts with no listings beyond whatever real users create.

	# Seed a few reviews for the demo storefront so the seller + reviews
	# sections on the listing page have real content. Reviews are keyed on
	# seller_id, so a newly registered seller correctly starts with the
	# "no reviews yet" empty state instead of fake numbers.
	if demo_user is not None and Review.query.filter_by(seller_id=demo_user.id).count() == 0:
		demo_reviewers = []
		for username, email in (
			("mei_ling87", "mei.ling@example.com"),
			("arif_hassan", "arif.hassan@example.com"),
			("teh_aiping", "teh.aiping@example.com"),
		):
			reviewer = User.query.filter_by(username=username).first()
			if reviewer is None:
				reviewer = User()
				reviewer.username = username
				reviewer.email = email
				reviewer.bio = "Baasket shopper"
				reviewer.set_password("baasket123")
				db.session.add(reviewer)
				db.session.flush()
			demo_reviewers.append(reviewer)

		demo_listings = Item.query.filter_by(seller_id=demo_user.id).order_by(Item.id).all()
		seed_reviews = [
			(5.0, "Item matched the photos exactly and the handover was quick.", 0, 2),
			(4.5, "Good communication throughout, slightly late to the meetup but worth it.", 1, 10),
			(5.0, "Second time buying from this seller \u2014 packaging was careful both times.", 2, 25),
			(4.0, "Fair price and the listing description was accurate.", 0, 40),
		]
		for index, (rating, comment, reviewer_idx, days_ago) in enumerate(seed_reviews):
			review = Review()
			review.reviewID = uuid4().hex
			review.ratingValue = rating
			review.comment = comment
			review.created_by = demo_reviewers[reviewer_idx % len(demo_reviewers)].id
			review.seller_id = demo_user.id
			if demo_listings:
				review.listing_id = demo_listings[index % len(demo_listings)].id
			review.created_at = datetime.utcnow() - timedelta(days=days_ago)
			db.session.add(review)

	db.session.commit()


def _authorize_report_action(report_id: str) -> Report | None:
	"""Shared guard for the two admin report-action routes: only the admin
	a report was actually routed to may act on it, mirroring the filter
	already used to build the /admin/reports inbox."""
	if not current_user.is_admin:
		flash("That action is only available to admins.", "warning")
		return None
	report = db.session.get(Report, report_id)
	if report is None or report.received_by != current_user.id:
		flash("That report could not be found.", "warning")
		return None
	return report


def create_app() -> Flask:
	_ensure_storage()

	app = Flask(__name__)
	app.config["SECRET_KEY"] = os.environ.get("BAASKET_SECRET_KEY", "baasket-development-secret")
	app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{(INSTANCE_DIR / 'baasket.db').as_posix()}"
	app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

	db.init_app(app)
	login_manager.init_app(app)

	payment_gateway = build_payment_gateway()
	offer_board = OfferBoard()
	notification_subject = build_notification_subject()

	@app.template_filter("money")
	def money_filter(value: object) -> str:
		return _money(value)

	@app.template_filter("timeago")
	def timeago_filter(value: object) -> str:
		return _timeago(value)

	@app.context_processor
	def inject_globals() -> dict[str, object]:
		chat_count = 0
		unread_count = 0
		if current_user.is_authenticated:
			chat_count = ChatSession.query.filter(
				or_(
					ChatSession.buyer_id == current_user.id,
					ChatSession.seller_id == current_user.id,
				)
			).count()
			unread_count = Notification.query.filter_by(
				user_id=current_user.id, is_read=False
			).count()
		return {
			"cart_count": len(session.get("cart", [])),
			"chat_count": chat_count,
			"unread_count": unread_count,
			"payment_methods": payment_gateway.options(),
			"brand_logo": url_for("static", filename="assets/logo/baasket_logo.png"),
		}

	with app.app_context():
		db.create_all()

		# Ensure chat_session table has the new columns added to the model
		def _ensure_chat_session_columns():
			inspector = db.session.execute(text("PRAGMA table_info('chat_session')")).all()
			cols = {row[1] for row in inspector} if inspector else set()
			to_add = []
			for col in ("buyer_id", "seller_id", "listing_id"):
				if col not in cols:
					to_add.append(col)
			if not to_add:
				return
			# SQLite supports simple ALTER TABLE ADD COLUMN statements for new columns
			for col in to_add:
				try:
					db.session.execute(text(f"ALTER TABLE chat_session ADD COLUMN {col} INTEGER"))
					db.session.commit()
				except Exception:
					db.session.rollback()

		_ensure_chat_session_columns()

		# Lightweight schema updates for newly added model fields
		def _ensure_schema_columns():
			table_columns = {
				"user": [
					("legal_name", "TEXT"),
					("ic_number", "TEXT"),
					("home_address", "TEXT"),
					("city", "TEXT"),
					("region", "TEXT"),
					("phone_number", "TEXT"),
					("country", "TEXT"),
					("last_seen", "TEXT"),
					("role", "TEXT DEFAULT 'user'"),
				],
				"listing_model": [
					("quantity", "INTEGER"),
					("sku", "TEXT"),
					("is_active", "INTEGER"),
					("subcategory", "TEXT"),
					("buyer_id", "INTEGER"),
					("reserved", "INTEGER DEFAULT 0"),
					("buyable", "INTEGER DEFAULT 1"),
					("listed_date", "TEXT"),
					("location", "TEXT"),
				],
				"offer": [
					("buyer_id", "INTEGER"),
					("status", "TEXT"),
				],
				"cart": [
					("items_json", "TEXT"),
				],
				"payment": [
					("buyer_id", "INTEGER"),
					("order_id", "INTEGER"),
					("gateway_reference", "TEXT"),
					("provider", "TEXT"),
				],
				"notification": [
					("category", "TEXT"),
					("is_read", "INTEGER DEFAULT 0"),
					("related_id", "INTEGER"),
				],
				"review": [
					("seller_id", "INTEGER"),
					("listing_id", "INTEGER"),
					("created_at", "TEXT"),
				],
				"report": [
					("reporter_id", "INTEGER"),
					("listing_id", "INTEGER"),
				],
			}

			for table, cols in table_columns.items():
				inspector = db.session.execute(text(f"PRAGMA table_info('{table}')")).all()
				existing = {row[1] for row in inspector} if inspector else set()
				for col_name, col_type in cols:
					if col_name not in existing:
						try:
							db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
							db.session.commit()
						except Exception:
							db.session.rollback()

		_ensure_schema_columns()

		# Seed demo data only after the schema is fully migrated, otherwise a
		# pre-existing database (created before newer columns like
		# review.seller_id existed) would fail here with "no such column".
		_seed_database()

	@app.get("/")
	def index() -> ResponseReturnValue:
		search = request.args.get("q", "").strip()
		category = request.args.get("category", "").strip()
		listings = _search_listings(search=search, category=category)

		return render_template(
			"index.html",
			title="Baasket | Marketplace",
			search=search,
			category=category,
			listings=listings,
			featured=_featured_listings(limit=1),
			categories=list(CATEGORIES_MAP.keys()),
			category_list=_build_category_list(),
		)

	@app.get("/listing/<int:listing_id>")
	def listing_detail(listing_id: int) -> ResponseReturnValue:
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("That listing is no longer available.", "warning")
			return redirect(url_for("index"))

		seller_stats = _seller_profile_stats(listing.seller_id)

		return render_template(
			"listing.html",
			title=f"{listing.title} | Baasket",
			listing=listing,
			related=_related_listings(listing, limit=4),
			seller_stats=seller_stats,
			seller_reviews=_seller_reviews(listing.seller_id, limit=4),
			search_terms=_related_search_terms(listing),
		)

	@app.post("/listing/<int:listing_id>/cart")
	@login_required
	def add_to_cart(listing_id: int):
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("The item you tried to add could not be found.", "warning")
			return redirect(url_for("index"))

		cart = session.setdefault("cart", [])
		cart.append(listing.id)
		session.modified = True
		flash(f"{listing.title} was added to your basket.", "success")
		return redirect(url_for("cart_view"))

	@app.post("/listing/<int:listing_id>/like")
	@login_required
	def toggle_like(listing_id: int):
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("That listing could not be found.", "warning")
			return redirect(url_for("index"))

		fallback = url_for("listing_detail", listing_id=listing.id)
		destination = _safe_redirect_target(request.form.get("next"), fallback)

		if listing.seller_id == current_user.id:
			flash("You cannot like your own listing.", "warning")
			return redirect(destination)

		existing = Like.query.filter_by(user_id=current_user.id, listing_id=listing.id).first()
		if existing is not None:
			db.session.delete(existing)
		else:
			db.session.add(Like(user_id=current_user.id, listing_id=listing.id))
		db.session.commit()

		return redirect(destination)

	@app.post("/listing/<int:listing_id>/report")
	@login_required
	def report_listing(listing_id: int):
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("That listing could not be found.", "warning")
			return redirect(url_for("index"))

		reason = request.form.get("reason", "").strip() or "Other"
		details = request.form.get("details", "").strip()[:1000]

		admin = User.query.filter_by(role="admin").first()

		report = Report()
		report.reportID = uuid4().hex
		report.reason = reason
		report.details = details
		report.received_by = admin.id if admin else None
		report.reporter_id = current_user.id
		report.listing_id = listing.id
		db.session.add(report)
		db.session.commit()

		flash("Thanks — your report has been sent to the Baasket team.", "success")
		return redirect(url_for("listing_detail", listing_id=listing_id))

	@app.get("/users/<int:user_id>")
	def user_profile(user_id: int) -> ResponseReturnValue:
		"""Public profile for any user — reachable by clicking their profile
		picture anywhere on the site. Shows their star rating, the reviews
		they've received, and their current (unsold) listings. This is
		read-only and separate from /dashboard, which stays private to the
		logged-in account it belongs to."""
		profile_user = db.session.get(User, user_id)
		if profile_user is None:
			flash("That user could not be found.", "warning")
			return redirect(url_for("index"))

		current_listings = (
			Item.query.filter_by(seller_id=profile_user.id, buyer_id=None)
			.order_by(Item.created_at.desc())
			.all()
		)

		return render_template(
			"user_profile.html",
			title=f"{profile_user.username} | Baasket",
			profile_user=profile_user,
			is_own_profile=current_user.is_authenticated and current_user.id == profile_user.id,
			seller_stats=_seller_profile_stats(profile_user.id),
			seller_reviews=_seller_reviews(profile_user.id, limit=20),
			listings=current_listings,
		)

	@app.route("/sell", methods=["GET", "POST"])
	@login_required
	def sell() -> ResponseReturnValue:
		if request.method == "POST":
			title = request.form.get("title", "").strip()[:100]
			category = request.form.get("category", "").strip()
			subcategory = request.form.get("subcategory", "").strip()
			price_text = request.form.get("price", "").strip()
			condition = request.form.get("condition", "").strip() or "Good"
			condition = condition[:10]  # enforce VARCHAR(10)
			location = request.form.get("location", "").strip() or "Local pickup"
			description = request.form.get("description", "").strip()[:1000]
			buyable  = request.form.get("buyable",  "1") == "1"

			if not title or not category or not price_text or not description:
				flash("Title, category, price, and description are required.", "warning")
				return redirect(url_for("sell"))

			if category not in VALID_CATEGORIES:
				flash("Please select a valid category.", "warning")
				return redirect(url_for("sell"))

			valid_subs = CATEGORIES_MAP.get(category, [])
			if valid_subs and subcategory not in valid_subs:
				subcategory = ""

			try:
				price = float(price_text)
			except Exception:
				flash("Enter a valid asking price.", "warning")
				return redirect(url_for("sell"))

			uploaded_files = [f for f in request.files.getlist("images") if getattr(f, "filename", "")]
			if len(uploaded_files) > Item.MAX_IMAGES:
				flash(f"You can upload up to {Item.MAX_IMAGES} images per listing — only the first {Item.MAX_IMAGES} were used.", "warning")
			image_paths = _save_uploads(uploaded_files, LISTING_UPLOAD_DIR, Item.MAX_IMAGES)
			seed_image_data = "" if image_paths else _build_art(title[:24] or category[:24] or "Listing", "#1f6f78", "#e26d5c")

			listing = Item()
			listing.seller_id = current_user.id
			listing.title = title
			listing.category = category
			listing.subcategory = subcategory
			listing.price = price
			listing.condition = condition
			listing.location = location
			listing.description = description
			listing.image_path = ""
			listing.seed_image_data = seed_image_data
			listing.buyable = buyable
			for position, image_path in enumerate(image_paths):
				listing.images.append(ListingImage(image_path=image_path, position=position))
			db.session.add(listing)
			db.session.commit()
			flash("Your listing is now live on Baasket.", "success")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		return render_template(
			"sell.html",
			title="Sell on Baasket",
			categories_map=CATEGORIES_MAP,
			max_images=Item.MAX_IMAGES,
		)

	@app.get("/cart")
	@login_required
	def cart_view() -> ResponseReturnValue:
		lines, subtotal = _create_cart_lines()
		return render_template("cart.html", title="Your Basket | Baasket", lines=lines, subtotal=subtotal)

	@app.post("/cart/remove/<int:listing_id>")
	@login_required
	def remove_from_cart(listing_id: int):
		cart = list(session.get("cart", []))
		try:
			cart.remove(listing_id)
		except ValueError:
			flash("That item was not in your basket.", "warning")
		else:
			flash("Item removed from your basket.", "info")
		session["cart"] = cart
		session.modified = True
		return redirect(url_for("cart_view"))

	@app.post("/checkout")
	@login_required
	def checkout() -> ResponseReturnValue:
		lines, subtotal = _create_cart_lines()
		if not lines:
			flash("Add a few items before checking out.", "warning")
			return redirect(url_for("cart_view"))

		buyer_name = request.form.get("buyer_name", "Guest Buyer").strip() or "Guest Buyer"
		buyer_email = request.form.get("buyer_email", "").strip()
		payment_method = request.form.get("payment_method", "card")
		note = request.form.get("note", "").strip()

		receipt = payment_gateway.charge(
			payment_method,
			subtotal,
			sender_name=buyer_name,
			sender_email=buyer_email,
			note=note,
			items=[line["listing"].title for line in lines],
		)

		order_lines: list[OrderLine] = [
			{
				"listing": line["listing"],
				"quantity": line["quantity"],
				"line_total": line["line_total"],
				"unit_price": Decimal(str(line["listing"].price)),
			}
			for line in lines
		]
		order = _persist_order(
			buyer_name=buyer_name,
			buyer_email=buyer_email,
			receipt=receipt,
			note=note,
			lines=order_lines,
			buyer_id=current_user.id,
		)
		_mark_listings_sold(order_lines, current_user.id)
		db.session.commit()

		_notify_sellers_purchase(order_lines, notification_subject)

		offer_id_raw = request.form.get("offer_id")
		offer_id = int(offer_id_raw) if offer_id_raw else None

		try:
			run_checkout_logistics_v2(
				app=app,
				order_id=order.id,
				buyer_id=current_user.id,
				buyer_name=buyer_name,
				buyer_email=buyer_email,
				payment_method=receipt.strategy_code,
				receipt=receipt,
				offer_id=offer_id,
			)
		except Exception:
			pass
		db.session.commit()

		session.pop("cart", None)
		flash("Payment processed successfully.", "success")

		if offer_id:
			try:
				offer = db.session.get(Offer, offer_id)
				if offer and not getattr(offer, "redeemed", False):
					offer.redeemed = True
					offer.redeemed_at = datetime.utcnow()
				db.session.commit()
			except Exception:
				pass

		return render_template(
			"checkout.html",
			title="Checkout Complete | Baasket",
			receipt=receipt,
			lines=lines,
			buyer_name=buyer_name,
			buyer_email=buyer_email,
			tracking_link=url_for("order_detail", order_id=order.id),
		)

	@app.route("/offers/<int:offer_id>/checkout", methods=["GET", "POST"])
	@login_required
	def offer_checkout(offer_id: int) -> ResponseReturnValue:
		offer = get_redeemable_offer(offer_id, current_user.id)
		if offer is None:
			flash("This offer is not available for purchase.", "warning")
			return redirect(url_for("notifications_view"))

		listing = db.session.get(Item, offer.listing_id)
		if listing is None:
			flash("The listing for this offer is no longer available.", "warning")
			return redirect(url_for("index"))

		offer_subtotal = Decimal(str(offer.amount))

		if request.method == "GET":
			return render_template(
				"offer_checkout.html",
				title=f"Buy at Offer Price | Baasket",
				offer=offer,
				listing=listing,
				subtotal=offer_subtotal,
			)

		buyer_name = request.form.get("buyer_name", current_user.username).strip() or current_user.username
		buyer_email = request.form.get("buyer_email", current_user.email).strip() or current_user.email
		payment_method = request.form.get("payment_method", "card")
		note = request.form.get("note", "").strip()

		receipt = payment_gateway.charge(
			payment_method,
			offer_subtotal,
			sender_name=buyer_name,
			sender_email=buyer_email,
			note=note,
			items=[listing.title],
		)

		order_lines: list[OrderLine] = [{
			"listing": listing,
			"quantity": 1,
			"line_total": offer_subtotal,
			"unit_price": offer_subtotal,
		}]
		order = _persist_order(
			buyer_name=buyer_name,
			buyer_email=buyer_email,
			receipt=receipt,
			note=note,
			lines=order_lines,
			buyer_id=current_user.id,
			offer_id=offer.id,
		)
		_mark_listings_sold(order_lines, current_user.id)
		_notify_sellers_purchase(order_lines, notification_subject)

		try:
			run_checkout_logistics_v2(
				app=app,
				order_id=order.id,
				buyer_id=current_user.id,
				buyer_name=buyer_name,
				buyer_email=buyer_email,
				payment_method=receipt.strategy_code,
				receipt=receipt,
				offer_id=offer.id,
			)
		except Exception:
			pass

		offer.redeemed = True
		offer.redeemed_at = datetime.utcnow()
		db.session.commit()

		flash("Payment processed successfully.", "success")
		checkout_lines = [{
			"listing": listing,
			"quantity": 1,
			"line_total": offer_subtotal,
		}]
		return render_template(
			"checkout.html",
			title="Checkout Complete | Baasket",
			receipt=receipt,
			lines=checkout_lines,
			buyer_name=buyer_name,
			buyer_email=buyer_email,
			tracking_link=url_for("order_detail", order_id=order.id),
		)

	@app.post("/listing/<int:listing_id>/offer")
	@login_required
	def submit_offer(listing_id: int):
		# Deprecated: offers should be created inside chat sessions.
		flash("Please start a chat with the seller to make offers.", "info")
		return redirect(url_for("listing_detail", listing_id=listing_id))

	@app.post("/listing/<int:listing_id>/chat")
	@login_required
	def start_chat(listing_id: int):
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("That listing is no longer available.", "warning")
			return redirect(url_for("index"))
		if listing.seller_id == current_user.id:
			flash("You cannot start a chat on your own listing.", "warning")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		# Check for existing chat between these participants for this listing
		existing = (
			ChatSession.query.filter_by(listing_id=listing.id, buyer_id=current_user.id, seller_id=listing.seller_id)
			.first()
		)
		if existing:
			return redirect(url_for("chat_view", chat_id=existing.chatID))

		from uuid import uuid4
		chat = ChatSession()
		chat.chatID = uuid4().hex
		chat.creator_id = current_user.id
		chat.buyer_id = current_user.id
		chat.seller_id = listing.seller_id
		chat.listing_id = listing.id
		db.session.add(chat)
		db.session.commit()
		flash("Chat started with the seller.", "success")
		return redirect(url_for("chat_view", chat_id=chat.chatID))

	@app.get("/chat/<string:chat_id>")
	@login_required
	def chat_view(chat_id: str) -> ResponseReturnValue:
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None:
			flash("Chat session not found.", "warning")
			return redirect(url_for("index"))
		if current_user.id not in (chat.buyer_id, chat.seller_id):
			flash("You are not a participant in this chat.", "warning")
			return redirect(url_for("index"))

		messages = Message.query.filter_by(session_id=chat.chatID).order_by(Message.timestamp.asc()).all()
		listing = db.session.get(Item, chat.listing_id) if chat.listing_id else None
		return render_template(
			"chat.html",
			title="Chat",
			chat=chat,
			messages=messages,
			listing=listing,
		)

	@app.get("/messages")
	@login_required
	def messages_inbox() -> ResponseReturnValue:
		chats = (
			ChatSession.query.filter(
				or_(
					ChatSession.buyer_id == current_user.id,
					ChatSession.seller_id == current_user.id,
				)
			)
			.order_by(ChatSession.createdAt.desc())
			.all()
		)

		inbox = []
		for chat in chats:
			listing = db.session.get(Item, chat.listing_id) if chat.listing_id else None
			last_msg = (
				Message.query.filter_by(session_id=chat.chatID)
				.order_by(Message.timestamp.desc())
				.first()
			)
			other_id = chat.seller_id if current_user.id == chat.buyer_id else chat.buyer_id
			other = db.session.get(User, other_id) if other_id else None
			inbox.append({
				"chat": chat,
				"listing": listing,
				"last_message": last_msg,
				"other_party": other,
			})

		return render_template(
			"messages.html",
			title="Messages | Baasket",
			chats=inbox,
		)

	@app.post("/chat/<string:chat_id>/message")
	@login_required
	def post_message(chat_id: str):
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None or current_user.id not in (chat.buyer_id, chat.seller_id):
			flash("Invalid chat session.", "warning")
			return redirect(url_for("index"))
		content = request.form.get("content", "").strip()
		if not content:
			flash("Message cannot be empty.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		from uuid import uuid4
		msg = Message()
		msg.messageID = uuid4().hex
		msg.content = content
		msg.session_id = chat.chatID
		msg.creator_id = current_user.id
		db.session.add(msg)
		db.session.commit()
		flash("Message sent.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer")
	@login_required
	def chat_offer(chat_id: str) -> ResponseReturnValue:
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None:
			flash("Invalid chat session.", "warning")
			return redirect(url_for("index"))
		listing = db.session.get(Item, chat.listing_id) if chat.listing_id else None
		if listing is None:
			flash("Associated listing not found.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		if current_user.id == listing.seller_id:
			flash("Sellers cannot make offers on their own listings.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		amount_text = request.form.get("amount", "").strip()
		try:
			amount = Decimal(amount_text)
		except Exception:
			flash("Enter a valid offer amount.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		if amount <= 0:
			flash("Offer amounts must be greater than zero.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		offer = Offer()
		offer.listing_id = listing.id
		offer.sender_id = current_user.id
		offer.receiver_id = listing.seller_id
		offer.amount = amount
		db.session.add(offer)
		db.session.flush()  # populate offer.id before commit
		# Post a message into the chat thread so the offer appears inline
		offer_msg = Message()
		offer_msg.messageID = uuid4().hex
		offer_msg.content = f"OFFER:{offer.id}"
		offer_msg.session_id = chat.chatID
		offer_msg.creator_id = current_user.id
		db.session.add(offer_msg)
		db.session.commit()
		flash("Your offer was sent in chat.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer/<int:offer_id>/accept")
	@login_required
	def accept_offer(chat_id: str, offer_id: int) -> ResponseReturnValue:
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None or current_user.id != chat.seller_id:
			flash("Not authorised.", "warning")
			return redirect(url_for("index"))
		offer = db.session.get(Offer, offer_id)
		if offer is None or offer.acceptanceStatus != "pending":
			flash("Offer not found or already resolved.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		offer.acceptanceStatus = "accepted"
		offer.accepted_at = datetime.utcnow()
		notify = Message()
		notify.messageID = uuid4().hex
		notify.content = f"✓ Offer of {offer.amount_label} accepted! Please proceed with payment."
		notify.session_id = chat.chatID
		notify.creator_id = current_user.id
		db.session.add(notify)
		listing = db.session.get(Item, offer.listing_id)
		notification_subject.notify("offer_accepted", {
			"buyer_id": offer.sender_id,
			"seller_id": current_user.id,
			"offer_id": offer.id,
			"amount": offer.amount_label,
			"listing_title": listing.title if listing else "an item",
		})
		db.session.commit()
		flash("Offer accepted.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer/<int:offer_id>/decline")
	@login_required
	def decline_offer(chat_id: str, offer_id: int) -> ResponseReturnValue:
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None or current_user.id != chat.seller_id:
			flash("Not authorised.", "warning")
			return redirect(url_for("index"))
		offer = db.session.get(Offer, offer_id)
		if offer is None or offer.acceptanceStatus != "pending":
			flash("Offer not found or already resolved.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		offer.acceptanceStatus = "declined"
		notify = Message()
		notify.messageID = uuid4().hex
		notify.content = f"✕ The offer of {offer.amount_label} was declined."
		notify.session_id = chat.chatID
		notify.creator_id = current_user.id
		db.session.add(notify)
		listing = db.session.get(Item, offer.listing_id)
		notification_subject.notify("offer_declined", {
			"buyer_id": offer.sender_id,
			"amount": offer.amount_label,
			"listing_title": listing.title if listing else "an item",
		})
		db.session.commit()
		flash("Offer declined.", "info")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.route("/register", methods=["GET", "POST"])
	def register() -> ResponseReturnValue:
		if request.method == "POST":
			username = request.form.get("username", "").strip()
			email = request.form.get("email", "").strip().lower()
			password = request.form.get("password", "")
			bio = request.form.get("bio", "").strip()
			profile_image = _save_upload(request.files.get("profile_image"), PROFILE_UPLOAD_DIR)

			if not username or not email or not password:
				flash("Username, email, and password are required.", "warning")
				return redirect(url_for("register"))

			if User.query.filter(or_(User.username == username, User.email == email)).first():
				flash("A user with that username or email already exists.", "warning")
				return redirect(url_for("register"))

			user = User()
			user.username = username
			user.email = email
			user.bio = bio
			user.profile_image = profile_image or ""
			user.set_password(password)
			# The very first real account on the site automatically becomes the
			# admin. The seeded demo "baasket" account (created on first app
			# startup, see _seed_database) is deliberately excluded from this
			# check, so admin status goes to the first person who actually signs
			# up rather than the demo storefront.
			if User.query.filter_by(role="admin").first() is None:
				user.role = "admin"
			db.session.add(user)
			db.session.commit()
			login_user(user)
			if user.is_admin:
				flash("Welcome to Baasket. You're the first account, so you've been made an admin.", "success")
			else:
				flash("Welcome to Baasket.", "success")
			return redirect(url_for("dashboard"))

		return render_template("register.html", title="Create Account | Baasket")

	@app.route("/login", methods=["GET", "POST"])
	def login() -> ResponseReturnValue:
		if request.method == "POST":
			identifier = request.form.get("identifier", "").strip().lower()
			password = request.form.get("password", "")
			user = User.query.filter(or_(User.username == identifier, User.email == identifier)).first()

			if user is None or not user.check_password(password):
				flash("Invalid login details.", "warning")
				return redirect(url_for("login"))

			login_user(user)
			flash("You are signed in.", "success")
			return redirect(request.args.get("next") or url_for("dashboard"))

		return render_template("login.html", title="Sign In | Baasket")

	@app.get("/logout")
	@login_required
	def logout() -> ResponseReturnValue:
		logout_user()
		flash("You have been signed out.", "info")
		return redirect(url_for("index"))

	@app.route("/dashboard", methods=["GET", "POST"])
	@login_required
	def dashboard() -> ResponseReturnValue:
		if request.method == "POST":
			new_username = request.form.get("username", "").strip()
			if not new_username:
				flash("Username cannot be empty.", "warning")
				return redirect(url_for("dashboard"))
			if new_username != current_user.username:
				existing_user = User.query.filter(User.username == new_username, User.id != current_user.id).first()
				if existing_user is not None:
					flash("That username is already taken.", "warning")
					return redirect(url_for("dashboard"))
				current_user.username = new_username
			current_user.bio = request.form.get("bio", "").strip()
			new_profile_image = _save_upload(request.files.get("profile_image"), PROFILE_UPLOAD_DIR)
			if new_profile_image:
				current_user.profile_image = new_profile_image
			db.session.commit()
			flash("Your profile has been updated.", "success")
			return redirect(url_for("dashboard"))

		listings = (
			Item.query.filter_by(seller_id=current_user.id)
			.order_by(Item.created_at.desc())
			.all()
		)
		sales_history = _sales_history_for_user(current_user.id)
		stats = _listing_stats_for_user(current_user.id)
		# Reviews other people have left on this user's listings (as a seller)
		reviews_received = (
			Review.query.filter_by(seller_id=current_user.id)
			.order_by(Review.created_at.desc())
			.all()
		)
		# Reviews this user has left on their own purchases (as a buyer)
		reviews_made = (
			Review.query.filter_by(created_by=current_user.id)
			.order_by(Review.created_at.desc())
			.all()
		)
		reviews_count = len(reviews_received)
		liked_listings = _liked_listings_for_user(current_user.id)
		return render_template(
			"dashboard.html",
			title="Seller Dashboard | Baasket",
			listings=listings,
			sales_history=sales_history,
			stats=stats,
			reviews_count=reviews_count,
			reviews_received=reviews_received,
			reviews_made=reviews_made,
			liked_listings=liked_listings,
			category_list=_build_category_list(),
		)

	@app.post("/dashboard/change_password")
	@login_required
	def change_password():
		current_password = request.form.get("current_password", "")
		new_password = request.form.get("new_password", "")
		confirm_password = request.form.get("confirm_password", "")
		if not (current_password and new_password and confirm_password):
			flash("Fill in all password fields to change your password.", "warning")
			return redirect(url_for("dashboard"))
		if not current_user.check_password(current_password):
			flash("Current password is incorrect.", "warning")
			return redirect(url_for("dashboard"))
		if new_password != confirm_password:
			flash("New passwords do not match.", "warning")
			return redirect(url_for("dashboard"))
		current_user.set_password(new_password)
		db.session.commit()
		flash("Your password has been changed.", "success")
		return redirect(url_for("dashboard"))

	@app.route("/dashboard/listings/<int:listing_id>/edit", methods=["GET", "POST"])
	@login_required
	def edit_listing(listing_id: int) -> ResponseReturnValue:
		listing = db.session.get(Item, listing_id)
		if listing is None or listing.seller_id != current_user.id:
			flash("That listing cannot be edited.", "warning")
			return redirect(url_for("dashboard"))

		if request.method == "POST":
			new_category = request.form.get("category", "").strip()
			if new_category and new_category in VALID_CATEGORIES:
				listing.category = new_category
			elif new_category:
				flash("Please select a valid category.", "warning")
				return redirect(url_for("edit_listing", listing_id=listing.id))

			new_subcategory = request.form.get("subcategory", "").strip()
			valid_subs = CATEGORIES_MAP.get(listing.category, [])
			if hasattr(listing, "subcategory"):
				listing.subcategory = new_subcategory if new_subcategory in valid_subs else ""

			listing.title = request.form.get("title", "").strip() or listing.title
			listing.condition = request.form.get("condition", "").strip() or listing.condition
			listing.location = request.form.get("location", "").strip() or listing.location
			listing.description = request.form.get("description", "").strip() or listing.description

			price_text = request.form.get("price", "").strip()
			if price_text:
				try:
					listing.price = Decimal(price_text)
				except Exception:
					flash("Enter a valid price.", "warning")
					return redirect(url_for("edit_listing", listing_id=listing.id))

			# Existing images the seller chose to remove (checkboxes posted as
			# "remove_image" with the ListingImage id as the value).
			remove_ids = {int(value) for value in request.form.getlist("remove_image") if value.isdigit()}
			remaining_images = [img for img in sorted(listing.images, key=lambda i: i.position) if img.id not in remove_ids]
			for img in list(listing.images):
				if img.id in remove_ids:
					listing.images.remove(img)
					db.session.delete(img)

			new_files = [f for f in request.files.getlist("images") if getattr(f, "filename", "")]
			available_slots = max(0, Item.MAX_IMAGES - len(remaining_images))
			if len(new_files) > available_slots:
				flash(f"A listing can have at most {Item.MAX_IMAGES} images — some new photos were not added.", "warning")
			new_paths = _save_uploads(new_files, LISTING_UPLOAD_DIR, available_slots)

			for position, img in enumerate(remaining_images):
				img.position = position
			next_position = len(remaining_images)
			for offset, image_path in enumerate(new_paths):
				listing.images.append(ListingImage(image_path=image_path, position=next_position + offset))

			if listing.images:
				listing.seed_image_data = ""

			db.session.commit()
			flash("Listing updated.", "success")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		return render_template(
			"edit_listing.html",
			title="Edit Listing | Baasket",
			listing=listing,
			categories_map=CATEGORIES_MAP,
			max_images=Item.MAX_IMAGES,
		)

	@app.post("/dashboard/listings/<int:listing_id>/delete")
	@login_required
	def delete_listing(listing_id: int):
		listing = db.session.get(Item, listing_id)
		if listing is None or listing.seller_id != current_user.id:
			flash("That listing cannot be removed.", "warning")
			return redirect(url_for("dashboard"))

		db.session.delete(listing)
		db.session.commit()
		flash("Listing removed.", "info")
		return redirect(url_for("dashboard"))

	@app.get("/browse/<path:category>")
	def browse_category(category: str) -> ResponseReturnValue:
		"""Category browse page with subcategory, sort, condition, and price filters."""
		if category not in VALID_CATEGORIES:
			flash("That category does not exist.", "warning")
			return redirect(url_for("index"))

		subcategories = CATEGORIES_MAP.get(category, [])

		# Query params
		selected_sub       = request.args.get("sub", "").strip()
		sort               = request.args.get("sort", "best_match").strip()
		selected_condition = request.args.get("condition", "").strip()
		price_min_raw      = request.args.get("price_min", "").strip()
		price_max_raw      = request.args.get("price_max", "").strip()

		# Validate sub
		if selected_sub and selected_sub not in subcategories:
			selected_sub = ""

		# Validate condition
		if selected_condition and selected_condition not in BROWSE_CONDITIONS:
			selected_condition = ""

		# Parse price bounds
		try:
			price_min = Decimal(price_min_raw) if price_min_raw else None
		except Exception:
			price_min = None
		try:
			price_max = Decimal(price_max_raw) if price_max_raw else None
		except Exception:
			price_max = None

		# Build query
		query = Item.query.filter(Item.category == category, Item.buyer_id.is_(None))
		if selected_sub:
			query = query.filter(Item.subcategory == selected_sub)
		if selected_condition:
			query = query.filter(Item.condition == selected_condition)
		if price_min is not None:
			query = query.filter(Item.price >= float(price_min))
		if price_max is not None:
			query = query.filter(Item.price <= float(price_max))

		# Apply sort
		if sort == "recent":
			query = query.order_by(Item.created_at.desc())
		elif sort == "price_high":
			query = query.order_by(Item.price.desc())
		elif sort == "price_low":
			query = query.order_by(Item.price.asc())
		else:
			# best_match: most recently created first
			query = query.order_by(Item.created_at.desc())

		listings = query.all()

		category_icon = url_for(
			"static",
			filename=f"assets/categories/{CATEGORY_ICONS.get(category, CATEGORY_ICON_FALLBACK)}",
		)

		return render_template(
			"browse.html",
			title=f"{category} | Baasket",
			category=category,
			category_icon=category_icon,
			subcategories=subcategories,
			selected_sub=selected_sub,
			sort=sort,
			conditions=BROWSE_CONDITIONS,
			selected_condition=selected_condition,
			price_min=price_min_raw,
			price_max=price_max_raw,
			listings=listings,
		)

	@app.get("/notifications")
	@login_required
	def notifications_view() -> ResponseReturnValue:
		notifs = (
			Notification.query.filter_by(user_id=current_user.id)
			.order_by(Notification.created_at.desc())
			.all()
		)
		# Mark all as read
		for n in notifs:
			n.is_read = True
		db.session.commit()
		return render_template(
			"notifications.html",
			title="Notifications | Baasket",
			notifications=notifs,
		)

	@app.get("/admin/reports")
	@login_required
	def admin_reports() -> ResponseReturnValue:
		if not current_user.is_admin:
			flash("That page is only available to admins.", "warning")
			return redirect(url_for("index"))

		reports = (
			Report.query.filter_by(received_by=current_user.id)
			.order_by(Report.timestamp.desc())
			.all()
		)
		return render_template(
			"admin_reports.html",
			title="Reports | Baasket",
			reports=reports,
		)

	@app.post("/admin/reports/<string:report_id>/remove-listing")
	@login_required
	def admin_remove_reported_listing(report_id: str) -> ResponseReturnValue:
		report = _authorize_report_action(report_id)
		if report is None:
			return redirect(url_for("index") if not current_user.is_admin else url_for("admin_reports"))

		listing = report.listing
		if listing is None:
			db.session.delete(report)
			db.session.commit()
			flash("That listing was already removed. The report has been cleared.", "info")
			return redirect(url_for("admin_reports"))

		listing_title = listing.title
		# Every report pointing at this listing is now moot, not just the one
		# the admin clicked through from — clear them all out of the inbox.
		Report.query.filter_by(listing_id=listing.id).delete(synchronize_session=False)
		db.session.delete(listing)  # cascades to its offers, likes, and images
		db.session.commit()

		flash(f'Removed the listing "{listing_title}" and cleared related reports.', "success")
		return redirect(url_for("admin_reports"))

	@app.post("/admin/reports/<string:report_id>/remove-user")
	@login_required
	def admin_remove_reported_user(report_id: str) -> ResponseReturnValue:
		report = _authorize_report_action(report_id)
		if report is None:
			return redirect(url_for("index") if not current_user.is_admin else url_for("admin_reports"))

		listing = report.listing
		if listing is None:
			db.session.delete(report)
			db.session.commit()
			flash("That listing was already removed, so there's no seller left to act on. The report has been cleared.", "info")
			return redirect(url_for("admin_reports"))

		seller = listing.seller
		if seller is None:
			flash("That listing's seller could not be found.", "warning")
			return redirect(url_for("admin_reports"))
		if seller.is_admin:
			flash("Admin accounts can't be removed this way.", "warning")
			return redirect(url_for("admin_reports"))

		seller_username = seller.username
		seller_listing_ids = [item.id for item in seller.listings]
		if seller_listing_ids:
			# Clear out every report tied to any of this seller's listings —
			# they're all about to be deleted along with the seller.
			Report.query.filter(Report.listing_id.in_(seller_listing_ids)).delete(synchronize_session=False)
		db.session.delete(seller)  # cascades to their listings, offers, likes, and images
		db.session.commit()

		flash(f'Removed the user "{seller_username}" and their listings.', "success")
		return redirect(url_for("admin_reports"))


	@app.get('/orders')
	@login_required
	def orders_list() -> ResponseReturnValue:
		orders = _orders_for_buyer(current_user.id)
		return render_template(
			'orders.html',
			title='Your Orders | Baasket',
			orders=orders,
		)

	@app.get('/orders/<int:order_id>') # logistic
	@login_required
	def order_detail(order_id: int) -> ResponseReturnValue:
		order = db.session.get(OrderModel, order_id)
		if order is None:
			flash('Order not found', 'warning')
			return redirect(url_for('index'))
		if order.buyer_id is not None and order.buyer_id != current_user.id:
			flash('You can only view your own orders.', 'warning')
			return redirect(url_for('index'))

		order_item_ids = [item.id for item in order.items]
		reviews_by_item = {
			review.order_item_id: review
			for review in Review.query.filter(Review.order_item_id.in_(order_item_ids)).all()
		} if order_item_ids else {}

		return render_template(
			'order_detail.html',
			order=order,
			title='Order Details',
			reviews_by_item=reviews_by_item,
			review_max_images=Review.MAX_IMAGES,
		)


	@app.get('/orders/<int:order_id>/status')
	@login_required
	def order_status(order_id: int):
		order = db.session.get(OrderModel, order_id)
		if order is None:
			return {'error': 'not found'}, 404
		return {
			'order_id': order.id,
			'tracking_status': order.tracking_status,
			'tracking_updated_at': order.tracking_updated_at.isoformat() if order.tracking_updated_at else None,
		}

	@app.post('/orders/<int:order_id>/items/<int:order_item_id>/review')
	@login_required
	def submit_review(order_id: int, order_item_id: int) -> ResponseReturnValue:
		order = db.session.get(OrderModel, order_id)
		if order is None:
			flash('Order not found.', 'warning')
			return redirect(url_for('index'))
		if order.buyer_id is not None and order.buyer_id != current_user.id:
			flash('You can only review your own orders.', 'warning')
			return redirect(url_for('index'))
		if order.tracking_status != 'delivered':
			flash('You can leave a review once this order has been delivered.', 'warning')
			return redirect(url_for('order_detail', order_id=order_id))

		order_item = db.session.get(OrderItemModel, order_item_id)
		if order_item is None or order_item.order_id != order.id:
			flash('That item could not be found on this order.', 'warning')
			return redirect(url_for('order_detail', order_id=order_id))

		if Review.query.filter_by(order_item_id=order_item.id).first() is not None:
			flash('You have already reviewed this item.', 'info')
			return redirect(url_for('order_detail', order_id=order_id))

		try:
			rating = float(request.form.get('rating', ''))
		except ValueError:
			rating = 0.0
		rating = max(1, min(5, round(rating)))
		comment = request.form.get('comment', '').strip()[:500]

		listing = db.session.get(Item, order_item.listing_id)
		uploaded_files = [f for f in request.files.getlist('images') if getattr(f, 'filename', '')]
		if len(uploaded_files) > Review.MAX_IMAGES:
			flash(f'You can attach up to {Review.MAX_IMAGES} photos per review — only the first {Review.MAX_IMAGES} were used.', 'warning')
		image_paths = _save_uploads(uploaded_files, REVIEW_UPLOAD_DIR, Review.MAX_IMAGES)

		review = Review()
		review.reviewID = uuid4().hex
		review.ratingValue = rating
		review.comment = comment
		review.created_by = current_user.id
		review.seller_id = listing.seller_id if listing else None
		review.listing_id = listing.id if listing else None
		review.order_id = order.id
		review.order_item_id = order_item.id
		for position, image_path in enumerate(image_paths):
			review.images.append(ReviewImage(image_path=image_path, position=position))
		db.session.add(review)
		db.session.commit()

		flash('Thanks for your review!', 'success')
		return redirect(url_for('order_detail', order_id=order_id))

	return app


app = create_app()


if __name__ == "__main__":
	# app.run(debug=True)
	import os
	port = int(os.environ.get("PORT", 5000))
	app.run(debug=True, port=port)