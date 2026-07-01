from __future__ import annotations

from typing import TYPE_CHECKING

from .core import Player, Phase, BlockStackItem
from .cards import CardType, DeclorationType, Card, category_of_type
from .behaviors import CardBehavior, AttackBehavior, card_behaviors
from .events import *
from ._assertions import *
import colorama as clr

if TYPE_CHECKING:
    from .engine import SiegeEngine

__all__ = [
    "resolve_action_phase",
    "resolve_declare_phase",
    "resolve_target_phase",
    "resolve_challenge_phase",
    "resolve_block_phase",
    "resolve_resolution",
    "handle_action_response",
    "handle_declare_multi_response",
    "handle_declare_response",
    "handle_target_response",
    "handle_challenge_response",
    "handle_no_block_response",
    "handle_challenge_block_response",
    "handle_block_response",
    "handle_relevant_card_response",
]



def resolve_action_phase(engine: "SiegeEngine"):
    if engine.player_drawn:
        engine.move_card(("deck", -1), (engine.current_player.id, -1))
        engine.next_player()
    while len(engine.current_player.hand) == 0:
        engine.move_card(("deck", -1), (engine.current_player.id, -1))
        engine.next_player()
    while engine.current_player.skip_amt > 0:
        engine.change_skip_amt(engine.current_player, -1)
        engine.next_player()
    engine.current_request = ActionRequest(engine.current_player.id)

def resolve_declare_phase(engine: "SiegeEngine"):
    engine.current_request = DeclareRequest(engine.current_player.id, engine.pile_to_tuples(engine.current_player.hand))

def resolve_target_phase(engine: "SiegeEngine"):
    if (behavior := assert_usable(engine)) is None: return
    if not behavior.requires_target:
        engine.phase = Phase.CHALLENGE
        return
    targets = behavior.get_targets(engine)
    if len(engine.players) == 2 and len(targets) == 1:
        engine.target_id = targets[0].id
        engine.phase = Phase.CHALLENGE
        return
    if not targets:
        engine.emit(
            EventEnvelope(
                engine.event_id,
                ActionCancelled(engine.current_player.id),
                {engine.current_player.id},
                True
            )
        )
        engine.phase = Phase.DECLARE
        return
    engine.current_request = TargetRequest(engine.current_player.id, [plr.id for plr in targets])

def resolve_challenge_phase(engine: "SiegeEngine"):
    if not assert_usable_or_multi(engine): return
    assert engine.declared_claim is not None
    if engine.challenge_index is None:
        resolve_post_action(engine)
        engine.challenge_index = engine.next_player_idx(engine.current_player_index)
    if engine.challenged:
        if resolve_challenge_decision(engine):
            engine.phase = Phase.BLOCK
            engine._reset_challenge_state(blocking=True)
        else:
            cancel_action(engine)
        return
    engine.challenge_index = engine.next_player_idx(engine.challenge_index)
    if engine.challenge_index == engine.current_player_index:
        engine.phase = Phase.BLOCK
        engine._reset_challenge_state(blocking=True)
        return
    req_holder_id = engine.players[engine.challenge_index].id
    att_id = engine.current_player.id
    if engine.declared_claim is False:
        engine.current_request = ChallengeMultiRequest(req_holder_id, att_id, "triple" if len(engine.played_cards) == 3 else "double")
    else:
        engine.current_request = ChallengeRequest(req_holder_id, att_id, engine.declared_claim)

def resolve_post_action(engine: "SiegeEngine"):
    assert engine.declared_claim is not None
    engine.emit(
        EventEnvelope(
            engine.event_id,
            ActionPlayed(
                engine.current_player.id,
                engine.pile_to_tuples(engine.played_cards),
                engine.declared_claim,
                engine.target_id
            ),
            None,
            False
        )
    )

def resolve_challenge_decision(engine: "SiegeEngine", block_item: BlockStackItem | None = None):
    """
    Resolves the decision to challenge another player on any action (base claim or block item), calculating if the claim was truthful and awarding/taking tokens.

    Args:
        engine: The engine to resolve this challenge on.
        block_item: The block item that this challenge is for, or `None` to resolve the current base claim. If this is set to `None`, `engine.challenge_index` (the index of the challenging player) must be set and the claimer will be set to the current player.

    Returns:
        bool | None: Whether or not the claim was truthful, or `None` if this function caused the current action to be cancelled.
    """
    if not assert_usable_or_multi(engine): return
    assert engine.declared_claim is not None
    played: list[CardType] = [block_item.card[0]] if block_item is not None else [card.type for card in engine.played_cards]
    expected_type: DeclorationType = block_item.claim if block_item is not None else engine.declared_claim
    # This function is called from the target calling out the blocker, so the claimer is the blocker and the challenger is the target
    claimer: Player = engine.get_player_from_id(block_item.blocker_id) if block_item is not None else engine.current_player
    if block_item is None:
        assert engine.challenge_index is not None
        challenger = engine.players[engine.challenge_index]
        engine.already_challenged = challenger
    else:
        challenger = engine.get_player_from_id(block_item.target_id)
    is_truthtelling = True
    if expected_type is False:
        for i in played:
            i_behavior = card_behaviors[i]
            for j in played:
                if i is j: continue
                j_behavior = card_behaviors[j]
                is_truthtelling &= i_behavior.is_truthtelling_multi(engine, j_behavior) or j_behavior.is_truthtelling_multi(engine, i_behavior)
    else:
        for p in played:
            p_behavior = card_behaviors[p]
            is_truthtelling &= p_behavior.is_truthtelling(engine, expected_type)
    if is_truthtelling:
        engine.steal_token(claimer, challenger)
    else:
        engine.steal_token(challenger, claimer)
    return is_truthtelling


def resolve_block_phase(engine: "SiegeEngine"):
    if len(engine.played_cards) == 3:
        resolve_block_round_robin(engine)
    elif len(engine.played_cards) == 2:
        engine.phase = Phase.RESOLUTION
    elif len(engine.played_cards) == 1:
        if (behavior := assert_usable(engine)) is None: return
        if behavior.requires_target:
            assert engine.target_id is not None
            if engine.already_challenged is not None and engine.target_id == engine.already_challenged:
                engine.phase = Phase.RESOLUTION
                engine._reset_block_state(resolution=True)
                return
            if resolve_block_targeted(
                engine,
                engine.get_player_from_id(
                    engine.target_id
                )
            ):
                engine.phase = Phase.RESOLUTION
                engine._reset_block_state(resolution=True)
        else: resolve_block_round_robin(engine)
    else:
        cancel_action(engine)
        return
    
def resolve_block_round_robin(engine: "SiegeEngine"):
    if engine.block_index is None:
        engine.block_index = engine.next_player_idx(engine.current_player_index)
    if engine.block_index == engine.current_player_index:
        engine.phase = Phase.RESOLUTION
        engine._reset_block_state(resolution=True)
        return
    if engine.already_challenged is not None and engine.players[engine.block_index] == engine.already_challenged or resolve_block_targeted(engine, engine.players[engine.block_index]):
        engine.block_index = engine.next_player_idx(engine.block_index)

def resolve_block_targeted(engine: "SiegeEngine", target: Player) -> bool | None:
    """
    Resolves one iteration of the block loop. (decision made off block or asking for decision to block base claim)

    Args:
        engine: The engine to resolve this challenge on.

    Returns:
        bool | None: Whether or not the block stack has ended (player decided to not block or player failed challenge), or `None` if this function caused the current action to be cancelled.
    """
    if not assert_usable_or_multi(engine): return
    assert engine.declared_claim is not None
    if not engine.block_stack:
        engine.block_index = engine.players.index(target)
        engine.current_request = BlockRequest(
            target.id,
            engine.current_player.id,
            True,
            engine.declared_claim,
            engine.pile_to_tuples(target.hand)
        ) if engine.declared_claim is not False else BlockTripleRequest(
            target.id,
            engine.current_player.id,
            engine.pile_to_tuples(target.hand)
        )
        return False
    if engine.challenged and len(engine.block_stack) == 0:
        engine.challenged = False
        print(
            f"{clr.Fore.YELLOW}{clr.Style.BRIGHT}[WARNING]{clr.Style.NORMAL}: " +
            "Engine detected API challenging base claim with a `ChosenChallengeBlock` response. " +
            "`ChallengeDecision` should be used instead. " +
            "The response will be ignored." +
            clr.Style.RESET_ALL
        )
    if engine.challenged and engine.blocked:
        print(
            f"{clr.Fore.YELLOW}{clr.Style.BRIGHT}[WARNING]{clr.Style.NORMAL}:" +
            "Engine detected both `challenged` and `blocked` flags being set at once. `challenged` will be prefered." +
            clr.Style.RESET_ALL
        )
    if engine.challenged:
        engine.challenged = False
        if not resolve_challenge_decision(engine, engine.block_stack[-1]): # if the block was a lie...
            engine.block_stack.pop() # it is ignored
        stack_finished(engine, target) # challenging always ends the block stack, whether the challenge was successful or not
        return True
    elif engine.blocked:
        engine.blocked = False
        last_blocker = engine.block_stack[-1].blocker_id
        last_blocked = engine.block_stack[-1].target_id
        last_claim = engine.block_stack[-1].claim
        engine.current_request = BlockRequest(
            last_blocked,
            last_blocker,
            False,
            last_claim,
            engine.pile_to_tuples(engine.get_pile_from_id(last_blocker))
        )
        return False
    else:
        stack_finished(engine, target)
        return True

def stack_finished(engine: "SiegeEngine", stack_target: Player):
    engine.base_blocks[stack_target.id] = (
        engine.block_stack[0]
        if len(engine.block_stack) % 2 == 1 else
        None
    )
    engine.block_stack.clear()


def resolve_resolution(engine: "SiegeEngine"):
    if len(engine.played_cards) == 3:
        resolve_triple_resolution(engine)
    elif len(engine.played_cards) == 2:
        for _ in range(3):
            engine.move_card(("deck", -1), (engine.current_player.id, -1))
    elif len(engine.played_cards) == 1:
        if (behavior := assert_usable(engine)) is None: return
        if behavior.requires_relevant_card and engine.relevant_card is None:
            resolve_relevant_card_needed(engine, behavior)
            return
        if engine.target_id is None:
            cancel_action(engine)
            return
        behavior.use(engine, engine.current_player, engine.get_player_from_id(engine.target_id))
    else:
        cancel_action(engine)
        return
    engine.next_player()
    engine._reset_challenge_state()
    engine._reset_block_state()
    engine.phase = Phase.ACTION

def resolve_triple_resolution(engine: "SiegeEngine"):
    if len(engine.players) == 2:
        for _ in range(5):
            engine.move_card(("deck", -1), (engine.current_player.id, -1))
    else:
        for player in engine.players:
            if player is engine.current_player: continue
            base_block = engine.base_blocks.get(player.id)
            if base_block is None:
                engine.steal_token(engine.current_player, player)
            else:
                behavior = card_behaviors[base_block.claim]
                behavior.resolve_block(engine, engine.current_player, player, engine.steal_token)

def resolve_relevant_card_needed(engine: "SiegeEngine", behavior: AttackBehavior):
    def relevant_card_request(attacker: Player, target: Player) -> None:
        target_hand = attacker.hand if behavior.relevant_card_from_user else target.hand
        if target_hand or not (usable_cards := behavior.get_usable_relevant_cards(engine, target_hand)):
            cancel_action(engine)
            return
        engine.current_request = ChooseRelevantCard(
            engine.current_player.id,
            engine.pile_to_tuples(usable_cards),
            behavior.relevant_card_from_user
        )
    if engine.target_id is None:
        cancel_action(engine)
        return
    behavior.resolve_block(engine, engine.current_player, engine.get_player_from_id(engine.target_id), relevant_card_request)



def handle_action_response(engine: "SiegeEngine", response: ActionChosen):
    if response.action == "draw":
        engine.player_drawn = True
    else:
        engine.phase = Phase.DECLARE

def handle_declare_multi_response(engine: "SiegeEngine", response: CardsDeclared):
    engine.declared_claim = False
    engine.played_cards = [engine.current_player.hand[idx] for idx in response.indices]
    engine.phase = Phase.BLOCK

def handle_declare_response(engine: "SiegeEngine", response: CardDeclared):
    if assert_usable(engine, response) is None: return
    engine.declared_claim = response.declared_type
    engine.played_cards = [engine.current_player.hand[response.index]]
    engine.phase = Phase.TARGET

def handle_target_response(engine: "SiegeEngine", response: TargetChosen):
    if assert_usable(engine) is None: return
    engine.target_id = response.target_id
    engine.phase = Phase.BLOCK

def handle_challenge_response(engine: "SiegeEngine", response: ChallengeDecision):
    engine.challenged = response.challenge

def handle_no_block_response(engine: "SiegeEngine", response: ChosenNotBlock):
    engine.blocked = False
    engine.challenged = False

def handle_challenge_block_response(engine: "SiegeEngine", response: ChosenChallengeBlock):
    engine.blocked = False
    engine.challenged = True

def handle_block_response(engine: "SiegeEngine", response: ChosenBlock):
    engine.blocked = True
    engine.challenged = False
    engine.block_stack.append(
        BlockStackItem(
            response.player_id,
            engine.players[engine.block_index].id if (
                engine.block_index is not None and
                response.player_id == engine.current_player.id
            ) else engine.current_player.id,
            response.claim,
            response.card
        )
    )

def handle_relevant_card_response(engine: "SiegeEngine", response: RelevantCardChosen):
    engine.relevant_card = Card.from_tuple(response.card)
