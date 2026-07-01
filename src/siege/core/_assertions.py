from __future__ import annotations

from typing import TYPE_CHECKING

from .events import EventEnvelope, CardDeclared, ActionCancelled
from .core import Phase
from .behaviors import CardBehavior, AttackBehavior, card_behaviors

if TYPE_CHECKING:
    from .engine import SiegeEngine

__all__ = [
    "assert_multi",
    "assert_usable_or_multi",
    "assert_usable",
    "cancel_action",
]

def assert_multi(
    engine: "SiegeEngine",
    /,
) -> bool:
    declared = engine.declared_claim
    if (
        declared is None or
        declared is not False
    ):
        cancel_action(engine)
        return False
    return True

def assert_usable_or_multi(
    engine: "SiegeEngine",
    /,
) -> bool:
    declared = engine.declared_claim
    if (
        declared is None or
        declared is not False and (
            not isinstance(behavior := card_behaviors[declared], AttackBehavior) or
            not behavior.can_use(engine)
        )
    ):
        cancel_action(engine)
        return False
    return True

def assert_usable(
    engine: "SiegeEngine",
    /,
    response: CardDeclared | None = None
) -> AttackBehavior | None:
    declared = response.declared_type if response else engine.declared_claim
    if (
        declared is None or declared is False or
        not isinstance(behavior := card_behaviors[declared], AttackBehavior) or
        not behavior.can_use(engine)
    ):
        cancel_action(engine, response is None)
        return
    return behavior

def cancel_action(
    engine: "SiegeEngine",
    /,
    kickback: bool = True
) -> None:
    engine.emit(
        EventEnvelope(
            id=engine.event_id,
            event=ActionCancelled(engine.current_player.id),
            recipients=None,
            is_private=False
        )
    )
    if kickback:
        engine.next_player()
        engine._reset_challenge_state()
        engine._reset_block_state()
        engine.phase = Phase.ACTION
