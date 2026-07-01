from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Self, TYPE_CHECKING, TypeVar, cast, overload

from .base import API
from ..core.events import *
from ..core.cards import CardTuple, card_symbols, falls_in_category

str_cases = Literal["lower", "upper", "title"]
_T_str = TypeVar("_T_str", bound=str)

@overload
def get_input(
    valid_responses: set[_T_str],
    prompt: str | None = None,
    case: str_cases = "lower"
) -> _T_str: ...
@overload
def get_input(
    valid_responses: None = None,
    prompt: str | None = None,
    case: str_cases = "lower"
) -> str: ...

def get_input(
    valid_responses: set[str] | None = None,
    prompt: str | None = None,
    case: str_cases = "lower"
) -> str:
    if prompt is not None:
        print(prompt)
    resp = input("> ")
    if case == "lower":
        resp = resp.lower().strip()
    elif case == "upper":
        resp = resp.upper().strip()
    elif case == "title":
        resp = resp.title().strip()
    if valid_responses is not None and resp not in valid_responses:
        print("Invalid response.")
        return get_input(valid_responses, prompt, case)
    return resp

def card_tuple_str(card: CardTuple, unknown: bool = False) -> str:
    status = '!' if card[1] else '?'
    return f"[{card_symbols[card[0]] + ' ' if not unknown or card[1] else ''}({status})]"

def index_list(prompt: str, length: int) -> list[int]:
    print(prompt)
    resp = input("> ")
    seperated: list[str] = [val.strip() for val in resp.strip().split(",")]
    idxes: list[int] = []
    for val in seperated:
        if not val.isdecimal() or not 0 <= (idx := int(val) - 1) < length:
            print("Invalid response.")
            return index_list(prompt, length)
        idxes.append(idx)
    return idxes

def single_index(prompt: str, length: int) -> int:
    print(prompt)
    resp = input("> ")
    if not resp.isdecimal() or not 0 <= (idx := int(resp) - 1) < length:
        print("Invalid response.")
        return single_index(prompt, length)
    return idx

def handle_action_request(api: DebugAPI, request: ActionRequest) -> ActionChosen:
    valid: set[Literal["play", "draw"]] = {"play", "draw"}
    resp = get_input(prompt=f"Play or draw this turn, Player {request.player_id}?", valid_responses=valid)
    return ActionChosen(request.player_id, resp)

def handle_declare_request(api: DebugAPI, request: DeclareRequest) -> CardsDeclared | CardDeclared:
    prompt = f"Which card(s) would you like to use, Player {request.player_id}?\n"
    for i, card in enumerate(request.hand):
        prompt += f"{i+1}. {card_tuple_str(card)}\n"
    idxes = index_list(prompt, len(request.hand))
    while len(idxes) > 3:
        print("Invalid response.")
        idxes = index_list(prompt, len(request.hand))
    if len(idxes) > 1:
        return CardsDeclared(request.player_id, idxes)
    prompt = "What would you like to declare this card as?\n"
    for ctype in falls_in_category["attack"]:
        prompt += f"- {ctype}\n"
    resp = get_input(prompt=prompt, valid_responses=falls_in_category["attack"], case="title")
    return CardDeclared(request.player_id, idxes[0], resp)

def handle_target_request(api: DebugAPI, request: TargetRequest) -> TargetChosen:
    prompt = f"Which player would you like to target, Player {request.player_id}?\n"
    for i, player in enumerate(request.possible_targets):
        if player is not request.player_id:
            prompt += f"{i+1}. {player}\n"
    idx = single_index(prompt, len(request.possible_targets))
    return TargetChosen(request.player_id, request.possible_targets[idx])

def handle_challenge_request(api: DebugAPI, request: ChallengeRequest | ChallengeMultiRequest) -> ChallengeDecision:
    prompt = f"Would you like to challenge Player {request.attacker_id}'s claim of {request.claim}, Player {request.player_id}? (y/n)"
    resp = get_input(prompt=prompt, valid_responses={"y", "n"})
    return ChallengeDecision(request.player_id, resp == "y")

def handle_block_request(api: DebugAPI, request: BlockRequest | BlockTripleRequest) -> ChosenNotBlock | ChosenBlock | ChosenChallengeBlock:
    if isinstance(request, BlockTripleRequest) or request.is_base_claim:
        prompt = f"Would you like to block Player {request.attacker_id}'s {'triple' if isinstance(request, BlockTripleRequest) else 'claim of ' + request.claim}, Player {request.player_id}? (y/n)"
        resp = get_input(prompt=prompt, valid_responses={"y", "n"})
        if resp == "y":
            prompt = f"With which card would you like to block, Player {request.player_id}?\n"
            for i, card in enumerate(request.myhand):
                prompt += f"{i+1}. {card_tuple_str(card)}\n"
            idx = single_index(prompt, len(request.myhand))
            prompt = f"What would you like to declare this card as?\n"
            for ctype in falls_in_category["defense"]:
                prompt += f"- {ctype}\n"
            resp = get_input(prompt=prompt, valid_responses=falls_in_category["defense"], case="title")
            return ChosenBlock(request.player_id, request.myhand[idx], resp)
        return ChosenNotBlock(request.player_id)
    else:
        prompt = f"Challenge or block Player {request.attacker_id}'s claim of {request.claim}, Player {request.player_id}? (c/b/n)"
        resp = get_input(prompt=prompt, valid_responses={"c", "b", "n"})
        if resp == "c":
            return ChosenChallengeBlock(request.player_id)
        elif resp == "b":
            prompt = f"With which card would you like to block, Player {request.player_id}?\n"
            for i, card in enumerate(request.myhand):
                prompt += f"{i+1}. {card_tuple_str(card)}\n"
            idx = single_index(prompt, len(request.myhand))
            prompt = f"What would you like to declare this card as?\n"
            for ctype in falls_in_category["defense"]:
                prompt += f"- {ctype}\n"
            resp = get_input(prompt=prompt, valid_responses=falls_in_category["defense"], case="title")
            return ChosenBlock(request.player_id, request.myhand[idx], resp)
        else:
            return ChosenNotBlock(request.player_id)

def handle_relevant_card_request(api: DebugAPI, request: ChooseRelevantCard) -> RelevantCardChosen:
    prompt = f"Which card would you like to use for this effect, Player {request.player_id}?\n"
    for i, card in enumerate(request.source_hand):
        prompt += f"{i+1}. {card_tuple_str(card, not request.is_from_user)}\n"
    idx = single_index(prompt, len(request.source_hand))
    return RelevantCardChosen(request.player_id, request.source_hand[idx])


class DebugAPI(API):
    def __init__(self) -> None:
        self.request_handlers: dict[type[Request], Callable[[Self, Any], Response]] = {
            ActionRequest: handle_action_request,
            DeclareRequest: handle_declare_request,
            TargetRequest: handle_target_request,
            ChallengeRequest: handle_challenge_request,
            ChallengeMultiRequest: handle_challenge_request,
            BlockRequest: handle_block_request,
            BlockTripleRequest: handle_block_request,
            ChooseRelevantCard: handle_relevant_card_request,
        }

    def handle_input(self, input: Request) -> Response:
        for cls, handler in self.request_handlers.items():
            if isinstance(input, cls):
                return handler(self, input)
        raise NotImplementedError(f"Request of type \"{type(input).__name__}\" is not implemented.")

    def handle_event(self, event: EventEnvelope) -> None:
        pass


__all__ = [
    "DebugAPI",
]
