from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager

followers_association = db.Table(
    'follow',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
)


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
    role = db.Column(db.String(20), nullable=False, default="user", server_default="user")

    listings = db.relationship("ListingModel", foreign_keys="[ListingModel.seller_id]", backref="seller", lazy=True, cascade="all, delete-orphan")
    followers = db.relationship(
        "User",
        secondary=followers_association,
        primaryjoin=id == followers_association.c.followed_id,
        secondaryjoin=id == followers_association.c.follower_id,
        backref=db.backref("following", lazy="dynamic"),
        lazy="dynamic",
    )

    def is_following(self, user: "User") -> bool:
        if user is None:
            return False
        return self.following.filter(followers_association.c.followed_id == user.id).count() > 0

    def follow(self, user: "User") -> None:
        if user is None or user.id == self.id:
            return
        if not self.is_following(user):
            self.following.append(user)

    def unfollow(self, user: "User") -> None:
        if user is None:
            return
        if self.is_following(user):
            self.following.remove(user)

    @property
    def follower_count(self) -> int:
        return self.followers.count()

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def profile_image_url(self) -> str:
        if self.profile_image:
            return f"/static/{self.profile_image}"
        return "/static/assets/logo/baasket_logo.png"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


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
    condition   = db.Column(db.String(15),  nullable=False)                   # CONDITION VARCHAR(15)
    listed_date = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow, index=True)  # LISTEDDATE
    description = db.Column(db.String(1000), nullable=False)                  # DESCRIPTION VARCHAR(1000)

    # ── Status & engagement ───────────────────────────────────────────────────
    reserved = db.Column(db.Boolean, nullable=False, default=False)           # RESERVED bool
    buyable  = db.Column(db.Boolean, nullable=False, default=True)            # BUYABLE  bool

    # ── Internal / legacy fields ──────────────────────────────────────────────
    # image_path / seed_image_data are kept for backward compatibility with the
    # seeded demo catalog (see catalog.py) and any listing created before the
    # multi-image gallery existed. Once a listing has rows in `images`, those
    # take priority — see image_data / gallery_images below.
    image_path     = db.Column(db.String(255), nullable=False, default="")
    seed_image_data = db.Column(db.Text,       nullable=False, default="")
    location       = db.Column(db.String(80),  nullable=False, default="")
    quantity       = db.Column(db.Integer,     nullable=False, default=1)
    sku            = db.Column(db.String(64),  nullable=True,  default="")
    is_active      = db.Column(db.Boolean,     nullable=False, default=True)

    # Keep created_at as an alias so existing code referencing it still works
    created_at = db.synonym("listed_date")

    offers = db.relationship("Offer", backref="listing", lazy=True, cascade="all, delete-orphan")
    deal_methods = db.relationship("DealMethod", backref="listing", lazy=True, cascade="all, delete-orphan")
    likes = db.relationship("Like", backref="listing", lazy=True, cascade="all, delete-orphan")
    images = db.relationship(
        "ListingImage",
        backref="listing",
        lazy=True,
        order_by="ListingImage.position",
        cascade="all, delete-orphan",
    )

    MAX_IMAGES = 10

    @property
    def price_label(self) -> str:
        return f"RM{float(self.price):,.2f}"

    @property
    def seller_name(self) -> str:
        return self.seller.username if self.seller else "Unknown seller"

    @property
    def image_data(self) -> str:
        """Cover photo — the first uploaded image, or a legacy/seeded fallback."""
        ordered = sorted(self.images, key=lambda img: img.position) if self.images else []
        if ordered:
            return ordered[0].url
        if self.image_path:
            return f"/static/{self.image_path}"
        return self.seed_image_data or "/static/assets/logo/baasket_logo.png"

    @property
    def offer_count(self) -> int:
        return len(self.offers)

    @property
    def default_deal_method(self) -> "DealMethod | None":
        for method in self.deal_methods:
            if method.isDefault:
                return method
        return self.deal_methods[0] if self.deal_methods else None

    @property
    def like_count(self) -> int:
        return len(self.likes)

    def is_liked_by(self, user: "User | None") -> bool:
        """Whether `user` has personally liked this listing. Only ever
        checks the requesting user's own like — there is no method or
        route that lists *other* users' likes, which is what keeps a
        shopper's liked items private to them."""
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return any(like.user_id == user.id for like in self.likes)

    @property
    def gallery_images(self) -> tuple[str, ...]:
        """All photos for this listing, cover first. Falls back to the single
        legacy image (uploaded path or seeded artwork) when no rows exist in
        `images`, so older/seeded listings still render correctly."""
        ordered = sorted(self.images, key=lambda img: img.position) if self.images else []
        if ordered:
            return tuple(img.url for img in ordered)
        return (self.image_data,)

    @property
    def posted_label(self) -> str:
        return self.listed_date.strftime("%d %b %Y") if self.listed_date else ""


class ListingImage(db.Model):
    """One photo belonging to a listing. A listing can have up to
    ListingModel.MAX_IMAGES of these; `position` controls display order,
    with position 0 acting as the cover photo shown in cards/thumbnails."""
    __tablename__ = "listing_image"
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    image_path = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def url(self) -> str:
        return f"/static/{self.image_path}"


class Like(db.Model):
    """One row per (user, listing) like. This is what makes the heart
    button a real per-user toggle instead of a single shared counter:
    re-liking can't inflate the count, and a listing's like_count is just
    len(self.likes). The unique constraint stops duplicate rows, and the
    only way to look these up by user (see User.liked_listings and the
    dashboard route) is filtered to that user's own id — there is no
    route that exposes which users liked a given listing, so each
    shopper's liked items stay private to them."""
    __tablename__ = "like"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "listing_id", name="uq_like_user_listing"),
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("liked_listings", lazy=True, cascade="all, delete-orphan"),
    )


class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    acceptanceStatus = db.Column(db.String(20), nullable=False, default="pending")
    accepted_at = db.Column(db.DateTime, nullable=True)
    redeemed = db.Column(db.Boolean, nullable=False, default=False)
    redeemed_at = db.Column(db.DateTime, nullable=True)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="offers_sent")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="offers_received")

    @property
    def buyer_display(self) -> str:
        return self.sender.username if getattr(self, "sender", None) else "Unknown buyer"

    @property
    def amount_label(self) -> str:
        return f"RM{Decimal(self.amount):,.2f}"


class OrderModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    buyer_name = db.Column(db.String(80), nullable=False)
    buyer_email = db.Column(db.String(120), nullable=False, default="")
    payment_method = db.Column(db.String(40), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    fee = db.Column(db.Numeric(10, 2), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    reference = db.Column(db.String(24), nullable=False, index=True)
    note = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    # Tracking fields for logistics simulator
    tracking_status = db.Column(db.String(40), nullable=False, default="paid")
    tracking_updated_at = db.Column(db.DateTime, nullable=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=True, index=True)
    payment_id = db.Column(db.String(36), db.ForeignKey("payment.paymentID"), nullable=True, index=True)
    shipping_id = db.Column(db.String(36), db.ForeignKey("shipping.shippingID"), nullable=True, index=True)

    buyer = db.relationship("User", foreign_keys=[buyer_id], backref="orders")
    items = db.relationship("OrderItemModel", backref="order", lazy=True, cascade="all, delete-orphan")

    @property
    def subtotal_label(self) -> str:
        return f"RM{Decimal(self.subtotal):,.2f}"

    @property
    def fee_label(self) -> str:
        return f"RM{Decimal(self.fee):,.2f}"

    @property
    def total_label(self) -> str:
        return f"RM{Decimal(self.total):,.2f}"


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
        return f"RM{Decimal(self.unit_price):,.2f}"

    @property
    def line_total_label(self) -> str:
        return f"RM{Decimal(self.line_total):,.2f}"


class OrderTracking(db.Model):
    __tablename__ = "order_tracking"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    meta = db.Column(db.Text, nullable=True)

    order = db.relationship("OrderModel", backref="tracking_history")


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

    # The seller being reviewed, and (optionally) the listing the review is
    # about. Both are nullable so existing rows created before this column
    # existed keep working; the seller's review feed simply skips them.
    seller_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Ties a review to the specific purchase it was left for. order_item_id
    # is what the "leave a review" button on the order page is keyed on, so
    # a buyer gets exactly one review per purchased item.
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=True, index=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item_model.id"), nullable=True, index=True, unique=True)

    reviewer = db.relationship("User", foreign_keys=[created_by])
    seller = db.relationship("User", foreign_keys=[seller_id])
    listing = db.relationship("ListingModel", foreign_keys=[listing_id])
    order = db.relationship("OrderModel", foreign_keys=[order_id])
    order_item = db.relationship("OrderItemModel", foreign_keys=[order_item_id])
    images = db.relationship(
        "ReviewImage",
        backref="review",
        lazy=True,
        order_by="ReviewImage.position",
        cascade="all, delete-orphan",
    )

    MAX_IMAGES = 5

    def addReview(self) -> bool:
        return True

    def editReview(self, new_rating: float, new_comment: str) -> bool:
        self.ratingValue = new_rating
        self.comment = new_comment
        return True

    @property
    def reviewer_name(self) -> str:
        return self.reviewer.username if self.reviewer else "Baasket user"

    @property
    def full_stars(self) -> int:
        return max(0, min(5, round(self.ratingValue)))

    @property
    def image_urls(self) -> tuple[str, ...]:
        ordered = sorted(self.images, key=lambda img: img.position) if self.images else []
        return tuple(img.url for img in ordered)


class ReviewImage(db.Model):
    """One photo attached to a review. A review can have up to
    Review.MAX_IMAGES of these; `position` controls display order."""
    __tablename__ = "review_image"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.String(36), db.ForeignKey("review.reviewID"), nullable=False, index=True)
    image_path = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def url(self) -> str:
        return f"/static/{self.image_path}"


class Report(db.Model):
    __tablename__ = "report"
    reportID = db.Column(db.String(36), primary_key=True)
    reason = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    received_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=True)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    recipient = db.relationship("User", foreign_keys=[received_by])
    listing = db.relationship("ListingModel", foreign_keys=[listing_id])

    def createReport(self) -> bool:
        return True

    @property
    def reporter_name(self) -> str:
        return self.reporter.username if self.reporter else "Unknown user"

    @property
    def listing_title(self) -> str:
        return self.listing.title if self.listing else "Listing no longer available"


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
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=True, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("listing_model.id"), nullable=True, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    senderBankAccountNum = db.Column(db.String(64), db.ForeignKey("bank_account.bankAccountNum"), nullable=True)
    receiverBankAccountNum = db.Column(db.String(64), db.ForeignKey("bank_account.bankAccountNum"), nullable=True)
    paymentType = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(80), nullable=False, default="created")
    transactionDate = db.Column(db.DateTime, nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=True, index=True)
    shipping_id = db.Column(db.String(36), db.ForeignKey("shipping.shippingID"), nullable=True, index=True)

    shipping = db.relationship("Shipping", foreign_keys=[shipping_id], backref="payment", uselist=False)

    def authorizePayment(self) -> bool:
        self.status = "authorized"
        self.transactionDate = datetime.utcnow()
        return True

    def refundPayment(self) -> bool:
        self.status = "refunded"
        return True


class Notification(db.Model):
    __tablename__ = "notification"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="general")
    related_id = db.Column(db.Integer, nullable=True, index=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship("User", foreign_keys=[user_id], backref="notifications")


class Shipping(db.Model):
    __tablename__ = "shipping"
    shippingID = db.Column(db.String(36), primary_key=True)
    carrierName = db.Column(db.String(140), nullable=True)
    trackingNumber = db.Column(db.String(140), nullable=True)
    estimatedDeliveryDate = db.Column(db.Date, nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order_model.id"), nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, default="created")
    delivered_at = db.Column(db.DateTime, nullable=True)

    order = db.relationship("OrderModel", foreign_keys=[order_id], backref="shipping_record", uselist=False)

    def updateTrackingInfo(
        self,
        carrier_name: str,
        tracking_number: str,
        *,
        estimated_delivery: date | None = None,
    ) -> bool:
        self.carrierName = carrier_name
        self.trackingNumber = tracking_number
        if estimated_delivery is not None:
            self.estimatedDeliveryDate = estimated_delivery
        if self.status == "created":
            self.status = "in_transit"
        return True

    def confirmDelivery(self) -> bool:
        self.status = "delivered"
        self.delivered_at = datetime.utcnow()
        return True