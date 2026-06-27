from dataclasses import dataclass
from typing import Literal
from abc import ABC

from .cards import CardType, CardTuple, CardPos

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
    "ChooseRelevantCard",
    "ActionChosen",
    "CardsDeclared",
    "TargetChosen",
    "ChallengeDecision",
    "BlockDecision",
    "RelevantCardChosen",
    "StartingCards",
    "Eliminated",
    "CardMoved",
    "MovedToMe",
    "MovedFromMe",
    "TokenStolen",
    "ActionPlayed",
    "CardRevealed",
    "UnusableNowCancelled",
    "SkipAmtChanged",
    "HandFullIgnored",
    "Error"
]

@dataclass
class EventEnvelope:
    id: int  # unique per logical event
    event: Event  # the actual event object
    recipients: set[int] | None
    is_private: bool  # explicit flag for whether this event is private or not, for ease of use by observers

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
class ChallengeRequest(Request): pass

@dataclass
class BlockRequest(Request):
    attacker_id: int
    claim: CardType | Literal[2, 3]

@dataclass
class ChooseRelevantCard(Request):
    source_player: int

@dataclass
class Response(ABC):
    player_id: int

@dataclass
class ActionChosen(Response):
    action: Literal["play", "draw"]

@dataclass
class CardsDeclared(Response):
    indices: list[int]
    declared_type: CardType

@dataclass
class TargetChosen(Response):
    target_id: int

@dataclass
class ChallengeDecision(Response):
    challenge: bool

@dataclass
class BlockDecision(Response):
    block: bool
    challenge: bool
    card_pos: CardPos | None
    claim: CardType

@dataclass
class RelevantCardChosen(Response):
    card_pos: CardPos

class Event(ABC): pass

@dataclass
class StartingCards(Event):
    cards: list[CardTuple]

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
    declared_type: CardType
    target_id: int | None

@dataclass
class CardRevealed(Event):
    pos: CardPos
    card: CardTuple

@dataclass
class UnusableNowCancelled(Event):
    player_id: int

@dataclass
class SkipAmtChanged(Event):
    player_id: int
    new_amt: int

@dataclass
class HandFullIgnored(Event):
    player_id: int

@dataclass
class Error(Event):
    type: str
    message: str