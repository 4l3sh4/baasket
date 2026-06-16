from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CheckoutReceipt:
    reference: str
    buyer_name: str
    buyer_email: str
    payment_method: str
    subtotal: Decimal
    fee: Decimal
    total: Decimal
    issued_at_utc: datetime
    message: str
