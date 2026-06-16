from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from logistics_v2.checkout_session_state import CheckoutSessionState

if TYPE_CHECKING:
    from logistics_v2.checkout_session import CheckoutSession


@runtime_checkable
class IObserver(Protocol):
    def update(
        self,
        session: CheckoutSession,
        previous_state: CheckoutSessionState,
    ) -> None:
        ...


@runtime_checkable
class ISubject(Protocol):
    def attach(self, observer: IObserver) -> None:
        ...

    def detach(self, observer: IObserver) -> None:
        ...

    def notify(self, previous_state: CheckoutSessionState) -> None:
        ...
