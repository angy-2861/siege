from abc import ABC, abstractmethod

from ..core.events import EventEnvelope, Request, Response

__all__ = [
    "API",
    "Observer"
]

class API(ABC):
    @abstractmethod
    def handle_input(self, input: Request) -> Response: ...

    @abstractmethod
    def handle_event(self, event: EventEnvelope) -> None: ...

class Observer(ABC):
    @abstractmethod
    def handle_event(self, event: EventEnvelope) -> None: ...