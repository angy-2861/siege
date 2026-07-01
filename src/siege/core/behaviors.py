from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, TYPE_CHECKING

from ._errors import fail

if TYPE_CHECKING:
    from .core import Player
    from .engine import SiegeEngine
    from .cards import CardType, Card

__all__ = [
    "CardBehavior",
    "AttackBehavior",
    "card_behaviors"
]

class CardBehavior(ABC):
    related_type: "CardType"
    
    def is_truthtelling(self, engine: "SiegeEngine", claim: "CardType"):
        return claim == self.related_type
    
    def is_truthtelling_multi(self, engine: "SiegeEngine", other: "CardBehavior"):
        return self.related_type == other.related_type
    
    def challenge_penalty(self, engine: "SiegeEngine") -> int:
        return 1

    def resolve_block(
        self,
        engine: "SiegeEngine",
        attacker: "Player",
        target: "Player",
        effect: Callable[[Player, Player], None]
    ):
        # default: do nothing special
        effect(attacker, target)

class AttackBehavior(CardBehavior):
    requires_target: bool = True
    requires_relevant_card: bool = False
    relevant_card_from_user: bool = False

    def get_targets(self, engine: "SiegeEngine") -> list["Player"]:
        if not self.requires_target:
            return []
        current_player = engine.current_player
        return [p for p in engine.players if p.id != current_player.id]

    def get_usable_relevant_cards(self, engine: "SiegeEngine", relevant_hand: list["Card"]):
        if not self.requires_relevant_card: raise ValueError("Cannot get usable relevant cards of a behavior that does not require one.")
        return relevant_hand

    def can_use(self, engine: "SiegeEngine") -> bool:
        return True

    @abstractmethod
    def use(self, engine: "SiegeEngine", attacker: "Player", target: "Player"):
        ...

# Non-attack card behaviors
class GuardBehavior(CardBehavior):
    related_type = "Guard"

    def resolve_block(
        self,
        engine: "SiegeEngine",
        attacker: "Player",
        target: "Player",
        effect: Callable[[Player, Player], None]
    ):
        return
    
class ReflectorBehavior(CardBehavior):
    related_type = "Reflector"

    def resolve_block(
        self,
        engine: "SiegeEngine",
        attacker: "Player",
        target: "Player",
        effect: Callable[[Player, Player], None]
    ):
        effect(target, attacker)

class JesterBehavior(CardBehavior):
    related_type = "Jester"

    def is_truthtelling(self, *args):
        return True
    
    def is_truthtelling_multi(self, *args):
        return True

class ScourgeBehavior(CardBehavior):
    related_type = "Scourge"

    def is_truthtelling(self, *args):
        return True

    def is_truthtelling_multi(self, *args):
        return True

    def challenge_penalty(self, engine: "SiegeEngine") -> int:
        return 2
    
# Attack card behaviors
class AssassinBehavior(AttackBehavior):
    related_type = "Assassin"

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        engine.steal_token(attacker, target)

class FoolBehavior(AttackBehavior):
    related_type = "Fool"

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        if not engine.played_cards:
            fail(engine, "InvalidPhase", "Card must be played during the resolution phase")
        played_card = engine.played_cards[-1]
        if played_card.type != "Fool":
            fail(engine, "InvalidCard", f"Looked for played card of type Fool, got {played_card.type}")
        engine.move_card(played_card.pos, (target.id, -1))  # Move the Fool card to the target's play area

class HeraldBehavior(AttackBehavior):
    related_type = "Herald"

    requires_target = False

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        engine.reshuffle_deck()

class InquisitorBehavior(AttackBehavior):
    related_type = "Inquisitor"

    requires_relevant_card = True
    relevant_card_from_user = True
    
    def can_use(self, engine: "SiegeEngine") -> bool:
        # check if user has a card in hand that can be the relevant card
        user = engine.current_player
        return len(user.hand) > 1  # user must have at least 2 cards in hand to use Inquisitor (Inquisitor + relevant card)

    def get_targets(self, engine: "SiegeEngine") -> list[Player]:
        return [p for p in super().get_targets(engine) if any(not c.revealed for c in p.hand)]  # Inquisitor can only target players with at least one unrevealed card in hand

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        relevant_card = engine.relevant_card
        if relevant_card is None:
            fail(engine, "InvalidPhase", "No relevant card found for Inquisitor")

        engine.move_card(relevant_card.pos, ("discard", -1))  # Discard the relevant card

        for card in target.hand:
            card.revealed = True  # Reveal the target's hand

class KingBehavior(AttackBehavior):
    related_type = "King"

    requires_relevant_card = True

    def get_targets(self, engine: "SiegeEngine") -> list[Player]:
        return [p for p in super().get_targets(engine) if len(p.hand) > 0]  # King can only target players with cards in hand
    
    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        stolen_card = engine.relevant_card
        if stolen_card is None:
            fail(engine, "InvalidPhase", "No relevant card found for King")
        if stolen_card not in target.hand:
            fail(engine, "InvalidTarget", "Target must have the stolen card in-hand for King")
        engine.move_card(stolen_card.pos, (attacker.id, -1))  # Move the targeted card to the attacker's play area
        if stolen_card.type == "Fool":
            engine.steal_token(attacker, target)
            stolen_card.revealed = True

class MerchantBehavior(AttackBehavior):
    related_type = "Merchant"

    requires_relevant_card = True
    relevant_card_from_user = True

    def can_use(self, engine: "SiegeEngine") -> bool:
        return len(engine.current_player.hand) > 1  # User must have at least 2 cards in hand to use Merchant (Merchant + card to give)

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        engine.steal_token(attacker, target)
        card_to_give = engine.relevant_card
        if card_to_give is None:
            fail(engine, "InvalidPhase", "No relevant card found for Merchant")

        engine.move_card(card_to_give.pos, (target.id, -1))  # Move the card to give to the target's play area

class SpyBehavior(AttackBehavior):
    related_type = "Spy"

    requires_relevant_card = True

    def get_targets(self, engine: "SiegeEngine") -> list[Player]:
        return [p for p in super().get_targets(engine) if any(not c.revealed for c in p.hand)]

    def get_usable_relevant_cards(self, engine: SiegeEngine, relevant_hand: list[Card]):
        hand = super().get_usable_relevant_cards(engine, relevant_hand)
        return [card for card in hand if not card.revealed]

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        if not engine.played_cards:
            fail(engine, "InvalidPhase", "Card must be played during the resolution phase")
        revealed_card = engine.relevant_card
        if revealed_card is None:
            fail(engine, "InvalidPhase", "No relevant card found for Spy")
        revealed_card.revealed = True

class WardenBehavior(AttackBehavior):
    related_type = "Warden"

    def use(self, engine: "SiegeEngine", attacker: Player, target: Player):
        engine.change_skip_amt(target, 1)  # Target must skip their next turn

cb: tuple[CardBehavior, ...] = (
    AssassinBehavior(),
    FoolBehavior(),
    GuardBehavior(),
    HeraldBehavior(),
    InquisitorBehavior(),
    JesterBehavior(),
    KingBehavior(),
    MerchantBehavior(),
    ReflectorBehavior(),
    ScourgeBehavior(),
    SpyBehavior(),
    WardenBehavior(),
)
card_behaviors: dict[CardType, CardBehavior] = {}
for card in cb:
    assert card.related_type not in card_behaviors, f"duplicate related_type: {card.related_type}"
    card_behaviors[card.related_type] = card
del cb