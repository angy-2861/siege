from __future__ import annotations

from typing import Literal, Union

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Player
    from .engine import SiegeEngine

__all__ = [
    "CardCategory",
    "CardType",
    "DeclorationType",
    "DeckType",
    "CardTuple",
    "ValidPile",
    "ValidPileId",
    "CardPos",
    "card_amts",
    "decks",
    "Card"
]

CardCategory = Literal["attack", "defense", "wild"]
CardType = Literal[
    "Assassin",
    "King",
    "Spy",
    "Warden",
    "Inquisitor",
    "Herald",
    "Merchant",
    "Fool",
    "Guard",
    "Reflector",
    "Jester",
    "Scourge"
]
DeclorationType = CardType | Literal[False]
DeckType = Literal[
    "Classic",
    "Normal",
    "Supremacy"
]
ValidPile = Union["Player", Literal['deck', 'discard']]
ValidPileId = int | Literal["deck", "discard"]
CardPos = tuple[ValidPileId, int] # tuple of (cardholder id, card index)
CardTuple = tuple[CardType, bool, CardPos] # tuple of (card type, revealed, position)

card_symbols: dict[CardType, str] = {
    "Assassin": "As",
    "King": "Kn",
    "Spy": "Sp",
    "Warden": "Wd",
    "Inquisitor": "Iq",
    "Herald": "Hd",
    "Merchant": "Mc",
    "Fool": "Fl",
    "Guard": "Gd",
    "Reflector": "Rf",
    "Jester": "Js",
    "Scourge": "Sc"
}

falls_in_category: dict[CardCategory, set[CardType]] = {
    "attack": {"Assassin", "Fool", "Herald", "Inquisitor", "King", "Merchant", "Spy", "Warden"},
    "defense": {"Guard", "Reflector"},
    "wild": {"Jester", "Scourge"}
}
category_of_type: dict[CardType, CardCategory] = {}

for cat, types in falls_in_category.items():
    for ctype in types:
        category_of_type[ctype] = cat

card_amts: dict[CardType, int] = {
    "Assassin": 4,
    "Fool": 1,
    "Guard": 4,
    "Herald": 4,
    "Inquisitor": 2,
    "Jester": 2,
    "King": 4,
    "Merchant": 4,
    "Reflector": 4,
    "Scourge": 2,
    "Spy": 4,
    "Warden": 4
}

decks: dict[DeckType, set[CardType]] = {
    "Classic": {"Assassin", "Guard", "Jester", "King", "Spy", "Warden"},
    "Normal": {"Assassin", "Guard", "Jester", "King", "Spy", "Warden", "Fool", "Inquisitor"},
    "Supremacy": {"Assassin", "Fool", "Guard", "Herald", "Inquisitor", "Jester", "King", "Merchant", "Reflector", "Scourge", "Spy", "Warden"}
}

class Card:
    def __init__(self, ctype: CardType, /, pos: CardPos, revealed: bool = False) -> None:
        self.type: CardType = ctype
        self.revealed = revealed
        self.pos = pos

    def to_tuple(self) -> CardTuple:
        return (self.type, self.revealed, self.pos)
    
    @classmethod
    def from_tuple(cls, tuple: CardTuple) -> Card:
        return Card(tuple[0], tuple[2], tuple[1])
    
    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Card):
            return NotImplemented
        return value.type == self.type and self.pos == value.pos and self.revealed == value.revealed
    
    def __repr__(self) -> str:
        return f"Card({self.type!r}, pos={self.pos}, revealed={self.revealed})"
        
    def __str__(self) -> str:
        status = '!' if self.revealed else '?'
        return f"[{card_symbols[self.type]} ({status})]"
