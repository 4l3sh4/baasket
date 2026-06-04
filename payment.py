from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol
from uuid import uuid4


@dataclass(slots=True)
class PaymentReceipt:
    strategy_code: str
    strategy_label: str
    subtotal: Decimal
    fee: Decimal
    total: Decimal
    reference: str
    message: str


class PaymentStrategy(Protocol):
    code: str
    label: str

    def process(self, subtotal: Decimal, **context: object) -> PaymentReceipt:
        ...


class BasePaymentStrategy(ABC):
    code: str
    label: str
    fee_rate: Decimal = Decimal("0.00")

    def _build_receipt(self, subtotal: Decimal, message: str) -> PaymentReceipt:
        fee = (subtotal * self.fee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (subtotal + fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return PaymentReceipt(
            strategy_code=self.code,
            strategy_label=self.label,
            subtotal=subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            fee=fee,
            total=total,
            reference=uuid4().hex[:10].upper(),
            message=message,
        )


class CardPaymentStrategy(BasePaymentStrategy):
    code = "card"
    label = "Card"
    fee_rate = Decimal("0.025")

    def process(self, subtotal: Decimal, **context: object) -> PaymentReceipt:
        buyer = str(context.get("buyer_name", "Customer"))
        return self._build_receipt(subtotal, f"Card payment approved for {buyer}.")


class WalletPaymentStrategy(BasePaymentStrategy):
    code = "wallet"
    label = "Digital Wallet"
    fee_rate = Decimal("0.010")

    def process(self, subtotal: Decimal, **context: object) -> PaymentReceipt:
        email = str(context.get("buyer_email", ""))
        suffix = f" for {email}" if email else ""
        return self._build_receipt(subtotal, f"Wallet transfer confirmed{suffix}.")


class CashOnDeliveryStrategy(BasePaymentStrategy):
    code = "cod"
    label = "Cash on Delivery"
    fee_rate = Decimal("0.000")

    def process(self, subtotal: Decimal, **context: object) -> PaymentReceipt:
        return self._build_receipt(subtotal, "Cash on delivery reserved for dispatch.")


class PaymentGateway:
    def __init__(self, strategies: list[PaymentStrategy]) -> None:
        self._strategies = {strategy.code: strategy for strategy in strategies}

    def options(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "code": strategy.code,
                "label": strategy.label,
                "fee_rate": getattr(strategy, "fee_rate", Decimal("0.00")),
            }
            for strategy in self._strategies.values()
        )

    def charge(self, strategy_code: str, subtotal: Decimal, **context: object) -> PaymentReceipt:
        strategy = self._strategies.get(strategy_code)
        if strategy is None:
            strategy = next(iter(self._strategies.values()))
        return strategy.process(subtotal, **context)


def build_payment_gateway() -> PaymentGateway:
    return PaymentGateway([CardPaymentStrategy(), WalletPaymentStrategy(), CashOnDeliveryStrategy()])