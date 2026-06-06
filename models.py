from __future__ import annotations

import json
from datetime import date, datetime
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
    legal_name = db.Column(db.String(140), nullable=True, default="")
    ic_number = db.Column(db.String(64), nullable=True, default="")
    home_address = db.Column(db.String(255), nullable=True, default="")
    city = db.Column(db.String(80), nullable=True, default="")
    region = db.Column(db.String(80), nullable=True, default="")
    phone_number = db.Column(db.String(40), nullable=True, default="")
    country = db.Column(db.String(80), nullable=True, default="")
    last_seen = db.Column(db.DateTime, nullable=True)

    listings = db.relationship("ListingModel", foreign_keys="[ListingModel.seller_id]", backref="seller", lazy=True, cascade="all, delete-orphan")

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
    # ── Primary key ──────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)                              # ITEMID (internal int; ITEMID UUID stored separately if needed)

    # ── Foreign keys ─────────────────────────────────────────────────────────
    seller_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)   # SELLERID → USER
    buyer_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True,  index=True)   # BUYERID  → USER (null until sold)

    # ── Category / subcategory (stored as strings; FK logic handled at app layer) ──
    category    = db.Column(db.String(80),  nullable=False, index=True)       # CATEGORYID
    subcategory = db.Column(db.String(120), nullable=False, default="")       # SUBCATEGORYID

    # ── Core listing fields ───────────────────────────────────────────────────
    title       = db.Column(db.String(100), nullable=False, index=True)       # TITLE    VARCHAR(100)
    price       = db.Column(db.Float,       nullable=False)                   # PRICE    FLOAT
    condition   = db.Column(db.String(10),  nullable=False)                   # CONDITION VARCHAR(10)
    listed_date = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow, index=True)  # LISTEDDATE
    description = db.Column(db.String(1000), nullable=False)                  # DESCRIPTION VARCHAR(1000)

    # ── Status & engagement ───────────────────────────────────────────────────
    likes    = db.Column(db.Integer, nullable=False, default=0)               # LIKES    INTEGER (≥ 0)
    reserved = db.Column(db.Boolean, nullable=False, default=False)           # RESERVED bool
    buyable  = db.Column(db.Boolean, nullable=False, default=True)            # BUYABLE  bool

    # ── Internal / legacy fields ──────────────────────────────────────────────
    kind           = db.Column(db.String(20),  nullable=False, default="standard")
    image_path     = db.Column(db.String(255), nullable=False, default="")
    seed_image_data = db.Column(db.Text,       nullable=False, default="")
    tags_csv       = db.Column(db.Text,        nullable=False, default="")
    location       = db.Column(db.String(80),  nullable=False, default="")
    quantity       = db.Column(db.Integer,     nullable=False, default=1)
    sku            = db.Column(db.String(64),  nullable=True,  default="")
    is_active      = db.Column(db.Boolean,     nullable=False, default=True)

    # Keep created_at as an alias so existing code referencing it still works
    created_at = db.synonym("listed_date")

    offers = db.relationship("Offer", backref="listing", lazy=True, cascade="all, delete-orphan")

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
        return f"S${float(self.price):,.2f}"

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


class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    message = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    buyer = db.relationship("User", foreign_keys=[buyer_id], backref="offers_made")

    @property
    def buyer_display(self) -> str:
        return self.buyer.username if getattr(self, "buyer", None) else "Unknown buyer"

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


# Aliases to match UML names
Item = ListingModel


class BankAccount(db.Model):
    __tablename__ = "bank_account"
    bankAccountNum = db.Column(db.String(64), primary_key=True)
    bankName = db.Column(db.String(140), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def addBankAccount(self) -> bool:
        return True

    def updateBankAccount(self) -> bool:
        return True

    def deleteBankAccount(self) -> bool:
        return True


class Review(db.Model):
    __tablename__ = "review"
    reviewID = db.Column(db.String(36), primary_key=True)
    ratingValue = db.Column(db.Float, nullable=False)
    comment = db.Column(db.String(500), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def addReview(self) -> bool:
        return True

    def editReview(self, new_rating: float, new_comment: str) -> bool:
        self.ratingValue = new_rating
        self.comment = new_comment
        return True


class Report(db.Model):
    __tablename__ = "report"
    reportID = db.Column(db.String(36), primary_key=True)
    reason = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    received_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def createReport(self) -> bool:
        return True


class Cart(db.Model):
    __tablename__ = "cart"
    cartID = db.Column(db.String(36), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    totalPrice = db.Column(db.Float, nullable=False, default=0.0)
    itemCount = db.Column(db.Integer, nullable=False, default=0)
    items_json = db.Column(db.Text, nullable=False, default="[]")

    def addItem(self, item_id: str) -> bool:
        self.itemCount += 1
        return True

    def removeItem(self, item_id: str) -> bool:
        if self.itemCount > 0:
            self.itemCount -= 1
        return True

    def checkout(self) -> bool:
        return True


class DealMethod(db.Model):
    __tablename__ = "deal_method"
    dealMethodID = db.Column(db.String(36), primary_key=True)
    methodType = db.Column(db.String(80), nullable=False)
    carrierName = db.Column(db.String(140), nullable=True)
    meetupLocation = db.Column(db.String(255), nullable=True)
    price = db.Column(db.Float, nullable=True, default=0.0)
    isDefault = db.Column(db.Boolean, nullable=False, default=False)
    item_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=True)

    def updateDealMethod(self) -> bool:
        return True

    def setAsDefault(self) -> bool:
        self.isDefault = True
        return True


class Category(db.Model):
    __tablename__ = "category"
    categoryID = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(140), nullable=False)

    def getItemsByCategory(self) -> list[Item]:
        return []


class Subcategory(db.Model):
    __tablename__ = "subcategory"
    subcategoryID = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    parent_id = db.Column(db.String(36), db.ForeignKey("category.categoryID"), nullable=False)

    def getItemBySubcategory(self) -> list[Item]:
        return []


class ChatSession(db.Model):
    __tablename__ = "chat_session"
    chatID = db.Column(db.String(36), primary_key=True)
    createdAt = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=True, index=True)

    messages = db.relationship("Message", backref="chat", lazy=True, cascade="all, delete-orphan")

    def createSession(self) -> bool:
        return True

    def getMessages(self) -> list:
        return []

    def deleteChatHistory(self) -> bool:
        return True


class Message(db.Model):
    __tablename__ = "message"
    messageID = db.Column(db.String(36), primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    session_id = db.Column(db.String(36), db.ForeignKey("chat_session.chatID"), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def sendMessage(self) -> bool:
        return True

    def deleteMessage(self) -> bool:
        return True


class Payment(db.Model):
    __tablename__ = "payment"
    paymentID = db.Column(db.String(36), primary_key=True)
    paymentType = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(80), nullable=False, default="created")
    transactionDate = db.Column(db.DateTime, nullable=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=True, index=True)
    gateway_reference = db.Column(db.String(64), nullable=True, default="")
    provider = db.Column(db.String(64), nullable=True, default="")

    def authorizePayment(self) -> bool:
        self.status = "authorized"
        self.transactionDate = datetime.utcnow()
        return True

    def refundPayment(self) -> bool:
        self.status = "refunded"
        return True


class Shipping(db.Model):
    __tablename__ = "shipping"
    shippingID = db.Column(db.String(36), primary_key=True)
    carrierName = db.Column(db.String(140), nullable=True)
    trackingNumber = db.Column(db.String(140), nullable=True)
    estimatedDeliveryDate = db.Column(db.Date, nullable=True)

    def updateTrackingInfo(self, tracking: str) -> bool:
        self.trackingNumber = tracking
        return True

    def confirmDelivery(self) -> bool:
        return True