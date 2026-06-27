from abc import ABC, abstractmethod
from typing import Callable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Player
    from .engine import SiegeEngine
    from .cards import CardType

__all__ = [
    "CardBehavior",
    "AttackBehavior",
    "card_behaviors"
]

class CardBehavior(ABC):
    is_claimable: bool = True

    def can_use(self, engine: "SiegeEngine") -> bool:
        return True
    
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

    @abstractmethod
    def use(self, engine: "SiegeEngine", attacker: "Player", target: "Player"):
        ...

# Non-attack card behaviors
class GuardBehavior(CardBehavior):
    def resolve_block(
        self,
        engine: "SiegeEngine",
        attacker: "Player",
        target: "Player",
        effect: Callable[[Player, Player], None]
    ):
        return  # Guard blocks all attacks without penalty
    
class ReflectorBehavior(CardBehavior):
    def resolve_block(
        self,
        engine: "SiegeEngine",
        attacker: "Player",
        target: "Player",
        effect: Callable[[Player, Player], None]
    ):
        effect(target, attacker)  # Reflector reflects the attack back to the attacker

class JesterBehavior(CardBehavior):
    pass

class ScourgeBehavior(CardBehavior):
    def challenge_penalty(self, engine: SiegeEngine) -> int:
        return 2  # Scourge has a higher challenge penalty
    
# Attack card behaviors
class AssassinBehavior(AttackBehavior):
    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine.steal_token(attacker, target)

class FoolBehavior(AttackBehavior):
    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine._assert(bool(engine.played_cards), "InvalidPhase", "Card must be played during the resolution phase")
        assert engine.played_cards
        played_card = engine.played_cards[-1]
        engine._assert(played_card.type == "Fool", "InvalidCard", f"Looked for played card of type Fool, got {played_card.type}")
        assert played_card.type == "Fool"
        engine.move_card(played_card.pos, (target.id, -1))  # Move the Fool card to the target's play area

class HeraldBehavior(AttackBehavior):
    requires_target = False

    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine.reshuffle_deck()

class InquisitorBehavior(AttackBehavior):
    requires_relevant_card = True
    relevant_card_from_user = True
    
    def can_use(self, engine: SiegeEngine) -> bool:
        # check if user has a card in hand that can be the relevant card
        user = engine.current_player
        return len(user.hand) > 1  # user must have at least 2 cards in hand to use Inquisitor (Inquisitor + relevant card)

    def get_targets(self, engine: SiegeEngine) -> list[Player]:
        return [p for p in super().get_targets(engine) if any(not c.revealed for c in p.hand)]  # Inquisitor can only target players with at least one unrevealed card in hand

    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        relevant_card = engine.relevant_card
        engine._assert(relevant_card is not None, "InvalidPhase", "No relevant card found for Inquisitor")
        assert relevant_card is not None

        engine.move_card(relevant_card.pos, ("discard", -1))  # Discard the relevant card

        for card in target.hand:
            card.revealed = True  # Reveal the target's hand

class KingBehavior(AttackBehavior):
    def get_targets(self, engine: SiegeEngine) -> list[Player]:
        return [p for p in super().get_targets(engine) if len(p.hand) > 0]  # King can only target players with cards in hand
    
    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine._assert(len(target.hand) > 0, "InvalidTarget", "Target must have at least one card in hand for King")
        assert len(target.hand) > 0
        target_card = target.hand[0]  # Target the first card in the target's hand
        engine.move_card(target_card.pos, (attacker.id, -1))  # Move the targeted card to the attacker's play area

class MerchantBehavior(AttackBehavior):
    requires_relevant_card = True
    relevant_card_from_user = True

    def can_use(self, engine: SiegeEngine) -> bool:
        return len(engine.current_player.hand) > 1  # User must have at least 2 cards in hand to use Merchant (Merchant + card to give)

    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine._assert(len(attacker.hand) > 1, "InvalidPhase", "Attacker must have at least 2 cards in hand to use Merchant (Merchant + card to give)")
        assert len(attacker.hand) > 1
        engine.steal_token(attacker, target)
        card_to_give = engine.relevant_card
        engine._assert(card_to_give is not None, "InvalidPhase", "No relevant card found for Merchant")
        assert card_to_give is not None

        engine.move_card(card_to_give.pos, (target.id, -1))  # Move the card to give to the target's play area

class SpyBehavior(AttackBehavior):
    requires_relevant_card = True
    relevant_card_from_user = False  # Spy's relevant card is the card from the target to be revealed, so it is not from the user

    def get_targets(self, engine: SiegeEngine) -> list[Player]:
        return [p for p in super().get_targets(engine) if any(not c.revealed for c in p.hand)]  # Spy can only target players with at least one unrevealed card in hand

    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine._assert(bool(engine.played_cards), "InvalidPhase", "Card must be played during the resolution phase")
        assert engine.played_cards
        revealed_card = engine.relevant_card
        engine._assert(revealed_card is not None, "InvalidPhase", "No relevant card found for Spy")
        assert revealed_card is not None
        revealed_card.revealed = True  # Reveal the Spy card

class WardenBehavior(AttackBehavior):
    def use(self, engine: SiegeEngine, attacker: Player, target: Player):
        engine.change_skip_amt(target, 1)  # Target must skip their next turn

card_behaviors: dict[CardType, CardBehavior] = {
    "Assassin": AssassinBehavior(),
    "Fool": FoolBehavior(),
    "Guard": GuardBehavior(),
    "Herald": HeraldBehavior(),
    "Inquisitor": InquisitorBehavior(),
    "Jester": JesterBehavior(),
    "King": KingBehavior(),
    "Merchant": MerchantBehavior(),
    "Reflector": ReflectorBehavior(),
    "Scourge": ScourgeBehavior(),
    "Spy": SpyBehavior(),
    "Warden": WardenBehavior()
}