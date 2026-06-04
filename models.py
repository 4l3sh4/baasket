from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.String(280), nullable=False, default="")
    profile_image = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    listings = db.relationship("ListingModel", backref="seller", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def profile_image_url(self) -> str:
        if self.profile_image:
            return f"/static/{self.profile_image}"
        return "/static/assets/logo/baasket_logo.png"


class ListingModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    condition = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="standard")
    image_path = db.Column(db.String(255), nullable=False, default="")
    seed_image_data = db.Column(db.Text, nullable=False, default="")
    tags_csv = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    offers = db.relationship("OfferModel", backref="listing", lazy=True, cascade="all, delete-orphan")

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(tag for tag in self.tags_csv.split(",") if tag)

    @property
    def badge(self) -> str:
        return {
            "featured": "Featured",
            "fresh": "Just In",
            "limited": "Limited Stock",
        }.get(self.kind, "Top Pick")

    @property
    def price_label(self) -> str:
        return f"S${Decimal(self.price):,.2f}"

    @property
    def seller_name(self) -> str:
        return self.seller.username if self.seller else "Unknown seller"

    @property
    def image_data(self) -> str:
        if self.image_path:
            return f"/static/{self.image_path}"
        return self.seed_image_data or "/static/assets/logo/baasket_logo.png"

    @property
    def offer_count(self) -> int:
        return len(self.offers)


class OfferModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    buyer_name = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    message = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    @property
    def amount_label(self) -> str:
        return f"S${Decimal(self.amount):,.2f}"


class OrderModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_name = db.Column(db.String(80), nullable=False)
    buyer_email = db.Column(db.String(120), nullable=False, default="")
    payment_method = db.Column(db.String(40), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    fee = db.Column(db.Numeric(10, 2), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    reference = db.Column(db.String(24), nullable=False, index=True)
    note = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    items = db.relationship("OrderItemModel", backref="order", lazy=True, cascade="all, delete-orphan")

    @property
    def subtotal_label(self) -> str:
        return f"S${Decimal(self.subtotal):,.2f}"

    @property
    def fee_label(self) -> str:
        return f"S${Decimal(self.fee):,.2f}"

    @property
    def total_label(self) -> str:
        return f"S${Decimal(self.total):,.2f}"


class OrderItemModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    line_total = db.Column(db.Numeric(10, 2), nullable=False)

    @property
    def unit_price_label(self) -> str:
        return f"S${Decimal(self.unit_price):,.2f}"

    @property
    def line_total_label(self) -> str:
        return f"S${Decimal(self.line_total):,.2f}"


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    if not user_id.isdigit():
        return None
    return db.session.get(User, int(user_id))


def serialize_tags(tags: list[str] | tuple[str, ...]) -> str:
    return ",".join(tag.strip() for tag in tags if tag.strip())


def deserialize_tags(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    data = json.loads(value)
    return tuple(str(item) for item in data)