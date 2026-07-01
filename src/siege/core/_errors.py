from __future__ import annotations

from typing import TYPE_CHECKING, Never
from .events import EventEnvelope, Error, CardDeclared

if TYPE_CHECKING:
    from .engine import SiegeEngine

__all__ = [
    "fail"
]


def fail(
        engine: "SiegeEngine",
        /,
        error_type: str,
        message: str,
        *,
        python_error_type: type[BaseException] = ValueError
    ) -> Never:
    engine.emit(EventEnvelope(
        engine.event_id,
        Error(error_type, message),
        recipients=None,
        is_private=False
    ))
    raise python_error_type(message)\
    
