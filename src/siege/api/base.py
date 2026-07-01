from __future__ import annotations

from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from ..core.events import EventEnvelope, Request, Response

__all__ = [
    "API",
    "Observer"
]

class API(ABC):
    host_id: int

    @abstractmethod
    def handle_input(self, input: "Request") -> "Response": ...

    @abstractmethod
    def handle_event(self, event: "EventEnvelope") -> None: ...

class Observer(ABC):
    @abstractmethod
    def handle_event(self, event: "EventEnvelope") -> None: ...