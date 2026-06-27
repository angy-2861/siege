from dataclasses import dataclass
from typing import Callable
from enum import Enum

import random as r

from typing import TYPE_CHECKING

from ..api.base import API

if TYPE_CHECKING:
    from cards import Card, CardType, CardPos

__all__ = [
    "generate_id",
    "Player",
    "Phase",
    "BlockStackItem"
]

used_ids: set[int] = set()

def generate_id() -> int:
    new_id = r.randint(1, 999_999)
    while new_id in used_ids:
        new_id += 1
    used_ids.add(new_id)
    return new_id

class Player:
    def __init__(self, api: "API", player_id: int | None = None) -> None:
        self.hand: list[Card] = []
        self.tokens: int = 3
        self.skip_amt: int = 0
        self.api: "API" = api
        self.id = player_id or generate_id()

    def reset(self) -> None:
        self.hand = []
        self.tokens = 3
        self.is_skipped = False
        api_reset = getattr(self.api, "reset", None)
        if callable(api_reset):
            api_reset()

class Phase(Enum):
    ACTION = "action" # Player chooses to play or draw
    DECLARE = "declare" # Player declares cards they are playing and their claim
    TARGET = "target" # Player chooses target for card effect if necessary
    CHALLENGE = "challenge" # Players choose whether to challenge the claim or not, if applicable
    BLOCK = "block" # Players choose whether to block the action or not, if applicable
    RESOLUTION = "resolution" # Action effects are resolved, players lose tokens as necessary, and elimination is checked for
    GAME_OVER = "game_over" # Game is over, winner is announced, and no more actions can be taken

    # Extra note:
    # when a player plays 2 or 3 cards, there is no target phase, and the challenge phase happens immediately after declaration.
    # this is for different reasons for different amounts of cards:
    #    - 2 cards: there are no targets, the player needs to draw 3 new cards
    #    - 3 cards: everyone is a target, blocking happens in a round robin format like challenges, and everyone who doesn't block must give a token to the aittacker

@dataclass
class BlockStackItem:
    blocker_id: int
    target_id: int
    claim: CardType
    pos: CardPos