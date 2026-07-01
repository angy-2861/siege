from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from abc import ABC

from .cards import CardType, DeclorationType, CardTuple, CardPos

__all__ = [
    "EventEnvelope",
    "Request",
    "Response",
    "Event", 
    "ActionRequest",
    "DeclareRequest",
    "TargetRequest",
    "ChallengeRequest",
    "BlockRequest",
    "ChallengeMultiRequest",
    "BlockTripleRequest",
    "ChooseRelevantCard",
    "ActionChosen",
    "CardsDeclared",
    "CardDeclared",
    "TargetChosen",
    "ChallengeDecision",
    "ChosenNotBlock",
    "ChosenChallengeBlock",
    "ChosenBlock",
    "RelevantCardChosen",
    "Eliminated",
    "CardMoved",
    "MovedToMe",
    "MovedFromMe",
    "TokenStolen",
    "ActionPlayed",
    "PlayerChallenged",
    "PlayerBlocked",
    "CardRevealed",
    "ActionCancelled",
    "SkipAmtChanged",
    "SuddenSiege",
    "DeckReshuffled",
    "HandFullIgnored",
    "Error"
]

@dataclass
class EventEnvelope:
    id: int
    event: Event
    recipients: set[int] | None
    is_private: bool

@dataclass
class Request(ABC):
    player_id: int

class ActionRequest(Request): pass

@dataclass
class DeclareRequest(Request):
    hand: list[CardTuple]

@dataclass
class TargetRequest(Request):
    possible_targets: list[int]

@dataclass
class ChallengeRequest(Request):
    attacker_id: int
    claim: CardType

@dataclass
class BlockRequest(Request):
    attacker_id: int
    is_base_claim: bool
    claim: CardType
    myhand: list[CardTuple]

@dataclass
class ChallengeMultiRequest(Request):
    attacker_id: int
    claim: Literal["double", "triple"]

@dataclass
class BlockTripleRequest(Request):
    attacker_id: int
    myhand: list[CardTuple]

@dataclass
class ChooseRelevantCard(Request):
    source_hand: list[CardTuple]
    is_from_user: bool

@dataclass
class Response(ABC):
    player_id: int

@dataclass
class ActionChosen(Response):
    action: Literal["play", "draw"]

@dataclass
class CardsDeclared(Response):
    indices: list[int]

@dataclass
class CardDeclared(Response):
    index: int
    declared_type: CardType

@dataclass
class TargetChosen(Response):
    target_id: int

@dataclass
class ChallengeDecision(Response):
    challenge: bool

@dataclass
class ChosenNotBlock(Response): pass

@dataclass
class ChosenChallengeBlock(Response): pass

@dataclass
class ChosenBlock(Response):
    card: CardTuple
    claim: CardType

@dataclass
class RelevantCardChosen(Response):
    card: CardTuple

class Event(ABC): pass

@dataclass
class Eliminated(Event):
    id: int

@dataclass
class CardMoved(Event):
    from_pos: CardPos
    to_pos: CardPos

@dataclass
class MovedToMe(Event):
    card: CardTuple
    from_pos: CardPos

@dataclass        
class MovedFromMe(Event):
    card: CardTuple
    to_pos: CardPos

@dataclass
class TokenStolen(Event):
    from_id: int
    to_id: int

@dataclass
class ActionPlayed(Event):
    player_id: int
    cards: list[CardTuple]
    declared_type: DeclorationType
    target_id: int | None

@dataclass
class PlayerChallenged(Event):
    challenger_id: int
    challenged_id: int
    cards: list[CardTuple]
    truthtelling: bool

@dataclass
class PlayerBlocked(Event):
    blocker_id: int
    blocked_id: int
    block_claim: CardType

@dataclass
class CardRevealed(Event):
    card: CardTuple

@dataclass
class ActionCancelled(Event):
    player_id: int

@dataclass
class SkipAmtChanged(Event):
    player_id: int
    new_amt: int

@dataclass
class SuddenSiege(Event): pass

@dataclass
class DeckReshuffled(Event):
    new_deck: list[CardTuple]

@dataclass
class HandFullIgnored(Event):
    player_id: int

@dataclass
class Error(Event):
    type: str
    message: str