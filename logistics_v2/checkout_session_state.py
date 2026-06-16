from __future__ import annotations

from enum import Enum


class CheckoutSessionState(str, Enum):
    CHECKOUT_STARTED = "checkout_started"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


_EMOJI = {
    CheckoutSessionState.CHECKOUT_STARTED: "🛒",
    CheckoutSessionState.PAYMENT_CONFIRMED: "💳",
    CheckoutSessionState.PACKED: "📦",
    CheckoutSessionState.SHIPPED: "🚚",
    CheckoutSessionState.DELIVERED: "✅",
}

_LABEL = {
    CheckoutSessionState.CHECKOUT_STARTED: "Checkout started",
    CheckoutSessionState.PAYMENT_CONFIRMED: "Paid",
    CheckoutSessionState.PACKED: "Packed",
    CheckoutSessionState.SHIPPED: "Shipped",
    CheckoutSessionState.DELIVERED: "Delivered",
}


def emoji(state: CheckoutSessionState) -> str:
    return _EMOJI.get(state, "🛒")


def label(state: CheckoutSessionState) -> str:
    return _LABEL.get(state, state.value)


def display(state: CheckoutSessionState) -> str:
    return f"{emoji(state)} {label(state)}"


def to_tracking_status(state: CheckoutSessionState) -> str | None:
    """Maps session state to legacy OrderModel.tracking_status values."""
    return {
        CheckoutSessionState.PAYMENT_CONFIRMED: "paid",
        CheckoutSessionState.PACKED: "packed",
        CheckoutSessionState.SHIPPED: "shipped",
        CheckoutSessionState.DELIVERED: "delivered",
    }.get(state)
