from __future__ import annotations

import os
from collections import Counter
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import case, or_
from werkzeug.utils import secure_filename

from catalog import ListingFactory, _build_art, build_seeded_catalog
from extensions import db, login_manager
from models import ListingModel, OfferModel, OrderItemModel, OrderModel, User, serialize_tags
from offers import OfferBoard
from payment import build_payment_gateway


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
LISTING_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "listings"
PROFILE_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "pfp"


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
	return f"S${amount:,.2f}"


def _create_cart_lines() -> tuple[list[dict[str, object]], Decimal]:
	cart_ids = [int(listing_id) for listing_id in session.get("cart", [])]
	counts = Counter(cart_ids)
	lines: list[dict[str, object]] = []
	subtotal = Decimal("0.00")

	for listing_id, quantity in counts.items():
		listing = db.session.get(ListingModel, listing_id)
		if listing is None:
			continue
		line_total = Decimal(listing.price) * quantity
		subtotal += line_total
		lines.append({"listing": listing, "quantity": quantity, "line_total": line_total})

	return lines, subtotal


def _sort_kind_expression():
	return case(
		(ListingModel.kind == "featured", 0),
		(ListingModel.kind == "fresh", 1),
		(ListingModel.kind == "limited", 2),
		else_=3,
	)


def _search_listings(search: str = "", category: str = "") -> list[ListingModel]:
	query = ListingModel.query
	if category:
		query = query.filter(ListingModel.category == category)
	if search:
		pattern = f"%{search}%"
		query = query.filter(
			or_(
				ListingModel.title.ilike(pattern),
				ListingModel.category.ilike(pattern),
				ListingModel.condition.ilike(pattern),
				ListingModel.location.ilike(pattern),
				ListingModel.description.ilike(pattern),
				ListingModel.tags_csv.ilike(pattern),
			)
		)
	return query.order_by(_sort_kind_expression(), ListingModel.created_at.desc()).all()


def _featured_listings(limit: int = 4) -> list[ListingModel]:
	return (
		ListingModel.query.order_by(_sort_kind_expression(), ListingModel.created_at.desc())
		.limit(limit)
		.all()
	)


def _related_listings(listing: ListingModel, limit: int = 3) -> list[ListingModel]:
	query = (
		ListingModel.query.filter(ListingModel.id != listing.id, ListingModel.category == listing.category)
		.order_by(_sort_kind_expression(), ListingModel.created_at.desc())
		.limit(limit)
	)
	results = query.all()
	if len(results) < limit:
		fallback = (
			ListingModel.query.filter(ListingModel.id != listing.id)
			.order_by(_sort_kind_expression(), ListingModel.created_at.desc())
			.all()
		)
		for candidate in fallback:
			if candidate not in results:
				results.append(candidate)
			if len(results) >= limit:
				break
	return results[:limit]


def _listing_stats_for_user(user_id: int) -> dict[str, int]:
	listings = ListingModel.query.filter_by(seller_id=user_id).all()
	offer_count = sum(len(listing.offers) for listing in listings)
	return {
		"listings": len(listings),
		"offers": offer_count,
	}


def _sales_history_for_user(user_id: int) -> list[dict[str, object]]:
	order_items = (
		OrderItemModel.query.join(ListingModel, OrderItemModel.listing_id == ListingModel.id)
		.join(OrderModel, OrderItemModel.order_id == OrderModel.id)
		.filter(ListingModel.seller_id == user_id)
		.order_by(OrderModel.created_at.desc(), OrderItemModel.id.desc())
		.all()
	)
	return [
		{
			"order": item.order,
			"item": item,
			"listing": db.session.get(ListingModel, item.listing_id),
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

	if ListingModel.query.count() == 0 and demo_user is not None:
		seed_repository = build_seeded_catalog(ListingFactory())
		for seed_listing in seed_repository.all():
			db.session.add(
				ListingModel(
					seller_id=demo_user.id,
					title=seed_listing.title,
					category=seed_listing.category,
					price=seed_listing.price,
					condition=seed_listing.condition,
					location=seed_listing.location,
					description=seed_listing.description,
					kind=seed_listing.kind,
					image_path="",
					seed_image_data=seed_listing.image_data,
					tags_csv=serialize_tags(seed_listing.tags),
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

	@app.template_filter("money")
	def money_filter(value: object) -> str:
		return _money(value)

	@app.context_processor
	def inject_globals() -> dict[str, object]:
		return {
			"cart_count": len(session.get("cart", [])),
			"payment_methods": payment_gateway.options(),
			"brand_logo": url_for("static", filename="assets/logo/baasket_logo.png"),
		}

	with app.app_context():
		db.create_all()
		_seed_database()

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
			categories=tuple(sorted({listing.category for listing in ListingModel.query.all()})),
			activity_feed=offer_board.recent_activity(limit=5),
			listing_count=ListingModel.query.count(),
		)

	@app.get("/listing/<int:listing_id>")
	def listing_detail(listing_id: int) -> str:
		listing = db.session.get(ListingModel, listing_id)
		if listing is None:
			flash("That listing is no longer available.", "warning")
			return redirect(url_for("index"))

		offers = (
			OfferModel.query.filter_by(listing_id=listing.id)
			.order_by(OfferModel.created_at.desc())
			.all()
		)
		return render_template(
			"listing.html",
			title=f"{listing.title} | Baasket",
			listing=listing,
			related=_related_listings(listing, limit=3),
			offers=offers,
		)

	@app.post("/listing/<int:listing_id>/cart")
	def add_to_cart(listing_id: int):
		listing = db.session.get(ListingModel, listing_id)
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
			title = request.form.get("title", "").strip()
			category = request.form.get("category", "").strip()
			price_text = request.form.get("price", "").strip()
			condition = request.form.get("condition", "").strip() or "Good"
			location = request.form.get("location", "").strip() or "Local pickup"
			description = request.form.get("description", "").strip()
			kind = request.form.get("kind", "standard").strip() or "standard"
			tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]
			image_path = _save_upload(request.files.get("image"), LISTING_UPLOAD_DIR)
			seed_image_data = "" if image_path else _build_art(title[:24] or category[:24] or "Listing", "#1f6f78", "#e26d5c")

			if not title or not category or not price_text or not description:
				flash("Title, category, price, and description are required.", "warning")
				return redirect(url_for("sell"))

			try:
				price = Decimal(price_text)
			except Exception:
				flash("Enter a valid asking price.", "warning")
				return redirect(url_for("sell"))

			listing = ListingModel(
				seller_id=current_user.id,
				title=title,
				category=category,
				price=price,
				condition=condition,
				location=location,
				description=description,
				kind=kind,
				image_path=image_path or "",
				seed_image_data=seed_image_data,
				tags_csv=serialize_tags(tags),
			)
			db.session.add(listing)
			db.session.commit()
			flash("Your listing is now live on Baasket.", "success")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		return render_template(
			"sell.html",
			title="Sell on Baasket",
			categories=tuple(sorted({listing.category for listing in ListingModel.query.all()})),
		)

	@app.get("/cart")
	def cart_view() -> str:
		lines, subtotal = _create_cart_lines()
		return render_template("cart.html", title="Your Basket | Baasket", lines=lines, subtotal=subtotal)

	@app.post("/cart/remove/<int:listing_id>")
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
			buyer_name=buyer_name,
			buyer_email=buyer_email,
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
	def submit_offer(listing_id: int):
		listing = db.session.get(ListingModel, listing_id)
		if listing is None:
			flash("That listing cannot receive offers right now.", "warning")
			return redirect(url_for("index"))

		buyer_name = request.form.get("buyer_name", "Anonymous").strip() or "Anonymous"
		message = request.form.get("message", "").strip()
		amount_text = request.form.get("amount", "").strip()

		try:
			amount = Decimal(amount_text)
		except Exception:
			flash("Enter a valid offer amount.", "warning")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		if amount <= 0:
			flash("Offer amounts must be greater than zero.", "warning")
			return redirect(url_for("listing_detail", listing_id=listing.id))

		offer_board.submit_offer(listing, buyer_name, amount, message)
		flash("Your offer was shared with the seller and watchers.", "success")
		return redirect(url_for("listing_detail", listing_id=listing.id))

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
			current_user.bio = request.form.get("bio", "").strip()
			new_profile_image = _save_upload(request.files.get("profile_image"), PROFILE_UPLOAD_DIR)
			if new_profile_image:
				current_user.profile_image = new_profile_image
			db.session.commit()
			flash("Your profile has been updated.", "success")
			return redirect(url_for("dashboard"))

		listings = (
			ListingModel.query.filter_by(seller_id=current_user.id)
			.order_by(ListingModel.created_at.desc())
			.all()
		)
		recent_offers = (
			OfferModel.query.join(ListingModel)
			.filter(ListingModel.seller_id == current_user.id)
			.order_by(OfferModel.created_at.desc())
			.limit(12)
			.all()
		)
		sales_history = _sales_history_for_user(current_user.id)
		stats = _listing_stats_for_user(current_user.id)
		return render_template(
			"dashboard.html",
			title="Seller Dashboard | Baasket",
			listings=listings,
			recent_offers=recent_offers,
			sales_history=sales_history,
			stats=stats,
		)

	@app.route("/dashboard/listings/<int:listing_id>/edit", methods=["GET", "POST"])
	@login_required
	def edit_listing(listing_id: int) -> str:
		listing = db.session.get(ListingModel, listing_id)
		if listing is None or listing.seller_id != current_user.id:
			flash("That listing cannot be edited.", "warning")
			return redirect(url_for("dashboard"))

		if request.method == "POST":
			listing.title = request.form.get("title", "").strip() or listing.title
			listing.category = request.form.get("category", "").strip() or listing.category
			listing.condition = request.form.get("condition", "").strip() or listing.condition
			listing.location = request.form.get("location", "").strip() or listing.location
			listing.description = request.form.get("description", "").strip() or listing.description
			listing.kind = request.form.get("kind", listing.kind).strip() or listing.kind
			tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]
			if tags:
				listing.tags_csv = serialize_tags(tags)

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
			categories=tuple(sorted({item.category for item in ListingModel.query.all()})),
		)

	@app.post("/dashboard/listings/<int:listing_id>/delete")
	@login_required
	def delete_listing(listing_id: int):
		listing = db.session.get(ListingModel, listing_id)
		if listing is None or listing.seller_id != current_user.id:
			flash("That listing cannot be removed.", "warning")
			return redirect(url_for("dashboard"))

		db.session.delete(listing)
		db.session.commit()
		flash("Listing removed.", "info")
		return redirect(url_for("dashboard"))

	return app


app = create_app()


if __name__ == "__main__":
	app.run(debug=True)
