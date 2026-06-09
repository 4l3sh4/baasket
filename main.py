from __future__ import annotations

import os
from collections import Counter
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, text
from werkzeug.utils import secure_filename

from catalog import ListingFactory, _build_art, build_seeded_catalog
from extensions import db, login_manager
from models import Item, Notification, Offer, OrderItemModel, OrderModel, User, ChatSession, Message, Review
from notifications import build_notification_subject
from offers import OfferBoard
from payment import build_payment_gateway


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
LISTING_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "listings"
PROFILE_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "pfp"

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

# Placeholder emoji icons for each category (shown in the carousel)
CATEGORY_ICONS: dict[str, str] = {
	"Computers & Tech":        "💻",
	"Mobile Phones & Gadgets": "📱",
	"Women's Fashion":         "👗",
	"Men's Fashion":           "👔",
	"Beauty & Personal Care":  "💄",
	"Luxury":                  "👜",
	"Video Gaming":            "🎮",
	"Audio":                   "🎧",
	"Photography":             "📷",
	"Furniture & Home Living": "🛋️",
	"TV & Home Appliances":    "📺",
	"Babies & Kids":           "🍼",
	"Hobbies & Toys":          "🎨",
	"Health & Nutrition":      "💊",
	"Sports Equipment":        "⚽",
	"Auto Accessories":        "🚗",
	"Pet Supplies":            "🐾",
}

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
		{"name": name, "icon": CATEGORY_ICONS.get(name, "🏷️")}
		for name in CATEGORIES_MAP
	]


def _ensure_storage() -> None:
	INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
	LISTING_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
	PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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


def _money(value: object) -> str:
	amount = Decimal(str(value))
	return f"RM{amount:,.2f}"


def _create_cart_lines() -> tuple[list[dict[str, object]], Decimal]:
	cart_ids = [int(listing_id) for listing_id in session.get("cart", [])]
	counts = Counter(cart_ids)
	lines: list[dict[str, object]] = []
	subtotal = Decimal("0.00")

	for listing_id, quantity in counts.items():
		listing = db.session.get(Item, listing_id)
		if listing is None:
			continue
		line_total = Decimal(listing.price) * quantity
		subtotal += line_total
		lines.append({"listing": listing, "quantity": quantity, "line_total": line_total})

	return lines, subtotal


def _search_listings(search: str = "", category: str = "") -> list[Item]:
	query = Item.query
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
		Item.query.order_by(Item.created_at.desc())
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


def _seed_database() -> None:
	if User.query.count() == 0:
		demo_user = User(username="baasket", email="hello@baasket.local", bio="Baasket demo storefront")
		demo_user.set_password("baasket123")
		db.session.add(demo_user)
		db.session.flush()
	else:
		demo_user = User.query.filter_by(username="baasket").first() or User.query.first()

	# Remove all listings owned by the demo/seed account so only real users' items remain
	if demo_user is not None:
		seed_listings = Item.query.filter_by(seller_id=demo_user.id).all()
		for listing in seed_listings:
			db.session.delete(listing)
		if seed_listings:
			db.session.commit()

	# Only seed if there are still no listings (i.e. no real users have posted yet).
	# Once a real user creates a listing this block never runs again.
	if Item.query.count() == 0 and demo_user is not None:
		seed_repository = build_seeded_catalog(ListingFactory())
		for seed_listing in seed_repository.all():
			db.session.add(
				Item(
					seller_id=demo_user.id,
					title=seed_listing.title,
					category=seed_listing.category,
					price=seed_listing.price,
					condition=seed_listing.condition,
					location=seed_listing.location,
					description=seed_listing.description,
					image_path="",
					seed_image_data=seed_listing.image_data,
				)
			)
	db.session.commit()


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
		_seed_database()

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
				],
				"listing_model": [
					("quantity", "INTEGER"),
					("sku", "TEXT"),
					("is_active", "INTEGER"),
					("subcategory", "TEXT"),
					("buyer_id", "INTEGER"),
					("likes", "INTEGER DEFAULT 0"),
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

	@app.get("/")
	def index() -> str:
		search = request.args.get("q", "").strip()
		category = request.args.get("category", "").strip()
		listings = _search_listings(search=search, category=category)

		return render_template(
			"index.html",
			title="Baasket | Marketplace",
			search=search,
			category=category,
			listings=listings,
			featured=_featured_listings(limit=4),
			categories=list(CATEGORIES_MAP.keys()),
			listing_count=Item.query.count(),
			category_list=_build_category_list(),
		)

	@app.get("/listing/<int:listing_id>")
	def listing_detail(listing_id: int) -> str:
		listing = db.session.get(Item, listing_id)
		if listing is None:
			flash("That listing is no longer available.", "warning")
			return redirect(url_for("index"))

		return render_template(
			"listing.html",
			title=f"{listing.title} | Baasket",
			listing=listing,
			related=_related_listings(listing, limit=3),
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

	@app.route("/sell", methods=["GET", "POST"])
	@login_required
	def sell() -> str:
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
			image_path = _save_upload(request.files.get("image"), LISTING_UPLOAD_DIR)
			seed_image_data = "" if image_path else _build_art(title[:24] or category[:24] or "Listing", "#1f6f78", "#e26d5c")

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

			listing = Item(
				seller_id=current_user.id,
				title=title,
				category=category,
				subcategory=subcategory,
				price=price,
				condition=condition,
				location=location,
				description=description,
				image_path=image_path or "",
				seed_image_data=seed_image_data,
				likes=0,
				buyable=buyable,
			)
			db.session.add(listing)
			db.session.commit()
			flash("Your listing is now live on Baasket.", "success")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		return render_template(
			"sell.html",
			title="Sell on Baasket",
			categories_map=CATEGORIES_MAP,
		)

	@app.get("/cart")
	@login_required
	def cart_view() -> str:
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
	def checkout():
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

		order = OrderModel(
			buyer_name=buyer_name,
			buyer_email=buyer_email,
			payment_method=receipt.strategy_code,
			subtotal=receipt.subtotal,
			fee=receipt.fee,
			total=receipt.total,
			reference=receipt.reference,
			note=note,
		)
		db.session.add(order)
		db.session.flush()
		for line in lines:
			listing = line["listing"]
			listing.buyer_id = current_user.id
			listing.buyable = False
			db.session.add(
				OrderItemModel(
					order_id=order.id,
					listing_id=listing.id,
					title=listing.title,
					quantity=line["quantity"],
					unit_price=listing.price,
					line_total=line["line_total"],
				)
			)
		db.session.commit()

		# Notify each seller whose item was purchased
		seller_titles: dict[int, list[str]] = {}
		for line in lines:
			listing = line["listing"]
			seller_titles.setdefault(listing.seller_id, []).append(listing.title)
		for seller_id, titles in seller_titles.items():
			notification_subject.notify("purchase", {
				"seller_id": seller_id,
				"titles": titles,
			})
		db.session.commit()

		session.pop("cart", None)
		flash("Payment processed successfully.", "success")
		return render_template(
			"checkout.html",
			title="Checkout Complete | Baasket",
			receipt=receipt,
			lines=lines,
			buyer_name=buyer_name,
			buyer_email=buyer_email,
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
		chat = ChatSession(chatID=uuid4().hex, creator_id=current_user.id, buyer_id=current_user.id, seller_id=listing.seller_id, listing_id=listing.id)
		db.session.add(chat)
		db.session.commit()
		flash("Chat started with the seller.", "success")
		return redirect(url_for("chat_view", chat_id=chat.chatID))

	@app.get("/chat/<string:chat_id>")
	@login_required
	def chat_view(chat_id: str):
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
	def messages_inbox() -> str:
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
		msg = Message(messageID=uuid4().hex, content=content, session_id=chat.chatID, creator_id=current_user.id)
		db.session.add(msg)
		db.session.commit()
		flash("Message sent.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer")
	@login_required
	def chat_offer(chat_id: str):
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
		offer = Offer(listing_id=listing.id, sender_id=current_user.id, receiver_id=listing.seller_id, amount=amount)
		db.session.add(offer)
		db.session.flush()  # populate offer.id before commit
		# Post a message into the chat thread so the offer appears inline
		offer_msg = Message(
			messageID=uuid4().hex,
			content=f"OFFER:{offer.id}",
			session_id=chat.chatID,
			creator_id=current_user.id,
		)
		db.session.add(offer_msg)
		db.session.commit()
		flash("Your offer was sent in chat.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer/<int:offer_id>/accept")
	@login_required
	def accept_offer(chat_id: str, offer_id: int):
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None or current_user.id != chat.seller_id:
			flash("Not authorised.", "warning")
			return redirect(url_for("index"))
		offer = db.session.get(Offer, offer_id)
		if offer is None or offer.acceptanceStatus != "pending":
			flash("Offer not found or already resolved.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		offer.acceptanceStatus = "accepted"
		notify = Message(
			messageID=uuid4().hex,
			content=f"✓ Offer of {offer.amount_label} accepted! Please proceed with payment.",
			session_id=chat.chatID,
			creator_id=current_user.id,
		)
		db.session.add(notify)
		listing = db.session.get(Item, offer.listing_id)
		notification_subject.notify("offer_accepted", {
			"buyer_id": offer.sender_id,
			"seller_id": current_user.id,
			"amount": offer.amount_label,
			"listing_title": listing.title if listing else "an item",
		})
		db.session.commit()
		flash("Offer accepted.", "success")
		return redirect(url_for("chat_view", chat_id=chat_id))

	@app.post("/chat/<string:chat_id>/offer/<int:offer_id>/decline")
	@login_required
	def decline_offer(chat_id: str, offer_id: int):
		chat = ChatSession.query.filter_by(chatID=chat_id).first()
		if chat is None or current_user.id != chat.seller_id:
			flash("Not authorised.", "warning")
			return redirect(url_for("index"))
		offer = db.session.get(Offer, offer_id)
		if offer is None or offer.acceptanceStatus != "pending":
			flash("Offer not found or already resolved.", "warning")
			return redirect(url_for("chat_view", chat_id=chat_id))
		offer.acceptanceStatus = "declined"
		notify = Message(
			messageID=uuid4().hex,
			content=f"✕ The offer of {offer.amount_label} was declined.",
			session_id=chat.chatID,
			creator_id=current_user.id,
		)
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
	def register() -> str:
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

			user = User(username=username, email=email, bio=bio, profile_image=profile_image or "")
			user.set_password(password)
			db.session.add(user)
			db.session.commit()
			login_user(user)
			flash("Welcome to Baasket.", "success")
			return redirect(url_for("dashboard"))

		return render_template("register.html", title="Create Account | Baasket")

	@app.route("/login", methods=["GET", "POST"])
	def login() -> str:
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
	def logout() -> str:
		logout_user()
		flash("You have been signed out.", "info")
		return redirect(url_for("index"))

	@app.route("/dashboard", methods=["GET", "POST"])
	@login_required
	def dashboard() -> str:
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
			current_password = request.form.get("current_password", "")
			new_password = request.form.get("new_password", "")
			confirm_password = request.form.get("confirm_password", "")
			if current_password or new_password or confirm_password:
				if not current_password or not new_password or not confirm_password:
					flash("Fill in all password fields to change your password.", "warning")
					return redirect(url_for("dashboard"))
				if not current_user.check_password(current_password):
					flash("Current password is incorrect.", "warning")
					return redirect(url_for("dashboard"))
				if new_password != confirm_password:
					flash("New passwords do not match.", "warning")
					return redirect(url_for("dashboard"))
				current_user.set_password(new_password)
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
		# Total reviews received by the current user
		reviews_count = Review.query.filter_by(created_by=current_user.id).count()
		return render_template(
			"dashboard.html",
			title="Seller Dashboard | Baasket",
			listings=listings,
			sales_history=sales_history,
			stats=stats,
			reviews_count=reviews_count,
			category_list=_build_category_list(),
		)

	@app.route("/dashboard/listings/<int:listing_id>/edit", methods=["GET", "POST"])
	@login_required
	def edit_listing(listing_id: int) -> str:
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

			replacement_image = _save_upload(request.files.get("image"), LISTING_UPLOAD_DIR)
			if replacement_image:
				listing.image_path = replacement_image
				listing.seed_image_data = ""

			db.session.commit()
			flash("Listing updated.", "success")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		return render_template(
			"edit_listing.html",
			title="Edit Listing | Baasket",
			listing=listing,
			categories_map=CATEGORIES_MAP,
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
	def browse_category(category: str) -> str:
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
		query = Item.query.filter(Item.category == category)
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

		category_icon = CATEGORY_ICONS.get(category, "🏷️")

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
	def notifications_view() -> str:
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

	return app


app = create_app()


if __name__ == "__main__":
	app.run(debug=True)