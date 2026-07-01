from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from enum import Enum

import random as r

from typing import TYPE_CHECKING

from ..api.base import API

if TYPE_CHECKING:
    from cards import Card, CardType, CardTuple

__all__ = [
    "set_id_offset",
    "generate_id",
    "Player",
    "Phase",
    "BlockStackItem"
]

_next_id = 0

def set_id_offset(offset: int):
    global _next_id
    _next_id = offset

def generate_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id

class Player:
    def __init__(self, api: "API", player_id: int | None = None) -> None:
        self.hand: list[Card] = []
        self.tokens: int = 3
        self.skip_amt: int = 0
        self.api: "API" = api
        self.id = player_id or generate_id()
        self.api.host_id = self.id

    def reset(self) -> None:
        self.hand = []
        self.tokens = 3
        self.is_skipped = False
        self.api.host_id = self.id
        api_reset = getattr(self.api, "reset", None)
        if callable(api_reset):
            api_reset()

    def __eq__(self, value: object) -> bool:
        if isinstance(value, Player):
            return value.id == self.id
        if isinstance(value, int):
            return value == self.id
        return NotImplemented

    def __hash__(self):
        return hash(self.id)

class Phase(Enum):
    """Determines the current phase of the game."""

    ACTION = "action"
    """Player chooses to play or draw"""
    DECLARE = "declare"
    """Player declares cards they are playing and their claim"""
    TARGET = "target"
    """Player chooses target for card effect if necessary"""
    BLOCK = "block"
    """Players choose whether to block the action or not, if applicable"""
    CHALLENGE = "challenge"
    """Players choose whether to challenge the claim or not, if applicable"""
    RESOLUTION = "resolution"
    """Action effects are resolved, players lose tokens as necessary, and elimination is checked for"""
    GAME_OVER = "game_over"
    """Game is over, winner is announced, and no more actions can be taken"""

    # Extra note:
    # when a player plays 2 or 3 cards, there is no target phase, and the challenge phase happens immediately after declaration.
    # this is for different reasons for different amounts of cards:
    #    - 2 cards: there are no targets, the player needs to draw 3 new cards
    #    - 3 cards: everyone is a target, blocking happens in a round robin format like challenges, and everyone who doesn't block must give a token to the aittacker

@dataclass
class BlockStackItem:
    blocker_id: int
    target_id: int
    claim: "CardType"
    card: "CardTuple"