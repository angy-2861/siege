from typing import Callable, overload

import random as r

from .core import Player, Phase, BlockStackItem
from .events import EventEnvelope, Request, ActionRequest, DeclareRequest, SkipAmtChanged, TargetRequest, ChallengeRequest, BlockRequest, ChooseRelevantCard, Response, ActionChosen, CardsDeclared, TargetChosen, ChallengeDecision, BlockDecision, RelevantCardChosen, Event, Eliminated, CardMoved, MovedToMe, MovedFromMe, TokenStolen, ActionPlayed, CardRevealed, UnusableNowCancelled, HandFullIgnored, Error
from .cards import Card, CardType, DeckType, category_of_type, decks, card_amts, ValidPileId, CardPos
from .behaviors import CardBehavior, AttackBehavior, card_behaviors
from ..api.base import Observer

__all__ = [
    "SiegeEngine"
]

class SiegeEngine:
    def __init__(self, players: list[Player], observers: list[Observer], deck_type: DeckType, seed: int | None = None):
        self.players: list[Player] = players
        self.observers: list[Observer] = observers
        self.eliminated: list[Player] = []
        self.deck_type: DeckType = deck_type
        self.deck: list[Card] = []
        self.discard: list[Card] = []

        self.current_player_index: int = 0
        self.phase: Phase = Phase.ACTION
        self.current_request: Request | None = None
        self.events: list[EventEnvelope] = []
        self.event_id_counter: int = 0

        self.phase_handlers: dict[Phase, Callable] = {
            Phase.ACTION: self._resolve_action_phase,
            Phase.DECLARE: self._resolve_declare_phase,
            Phase.TARGET: self._resolve_target_phase,
            Phase.CHALLENGE: self._challenge_loop_iteration,
            Phase.BLOCK: self._block_loop_iteration,
            Phase.RESOLUTION: self._resolve_resolution
        }
        self.response_handlers: dict[type[Response], Callable] = {
            ActionChosen: self._handle_action_response,
            CardsDeclared: self._handle_declare_response,
            TargetChosen: self._handle_target_response,
            ChallengeDecision: self._handle_challenge_response,
            BlockDecision: self._handle_block_response,
            RelevantCardChosen: self._handle_relevant_card_response,
        }

        # Pending action state
        self.declared_claim: CardType | None = None
        self.played_cards: list[Card] = []
        self.target_id: int | None = None

        # Challenge flow
        self.challenge_index: int | None = None

        # Block flow
        self.block_index: int | None = None
        self.block_target_id: int | None = None
        self.block_stack: list[BlockStackItem] = []
        self.base_blocks: dict[int, BlockStackItem | None] = {}
        self.block_passed: bool = False

        # Resolution state
        self.relevant_card: Card | None = None

        self.winner_id: int | None = None

        # Random seed
        self.seed = seed or r.randint(1, 999_999)
        self.rng = r.Random(self.seed)

        self.reset_game()

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_index]
    
    @current_player.setter
    def current_player(self, new_player: Player):
        if new_player not in self.players:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidPlayer", f"Player with id {new_player.id} is not in the game"),
                recipients=None,
                is_private=False
            ))
            raise ValueError(f"Player with id {new_player.id} is not in the game")
        self.current_player_index = self.players.index(new_player)

    def get_request(self) -> Request | None:
        return self.current_request

    def submit_response(self, response: Response) -> None:
        if self.current_request is None:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidResponse", "No active request"),
                recipients=None,
                is_private=False
            ))
            raise RuntimeError("No active request")

        if self.current_request.player_id != response.player_id:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidResponse", "Response from wrong player"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Response from wrong player")

        self._handle_response(response)
        self.current_request = None

        self._advance()

    def consume_events(self) -> list[EventEnvelope]:
        ev = self.events.copy()
        self.events.clear()
        return ev
    
    def _notify_observers(self, event: EventEnvelope):
        for obs in self.observers:
            obs.handle_event(event)

    @property
    def event_id(self) -> int:
        return self.event_id_counter
    
    def emit(self, events: list[EventEnvelope] | EventEnvelope):
        if not isinstance(events, list):
            events = [events]
        for event in events:
            self.events.append(event)
            self._notify_observers(event)
        self.event_id_counter += 1

    def _assert_declared_claim(self, response: CardsDeclared | None = None):
        dc = response.declared_type if response else self.declared_claim
        if dc is None:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidPhase", "No declared claim in declared claim assertion"),
                recipients=None,
                is_private=False
            ))
            raise RuntimeError("No declared claim in declared claim assertion")
        behavior = card_behaviors.get(dc)
        if not behavior or not isinstance(behavior, CardBehavior) or not behavior.is_claimable:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidDeclaredType", f"Declared type {dc} is not claimable"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Declared type is not claimable")
        return dc
    
    def _assert_declared_is_attack(self, response: CardsDeclared | None = None):
        dc = self._assert_declared_claim(response)
        behavior = card_behaviors.get(dc)
        if not behavior or not isinstance(behavior, AttackBehavior):
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidDeclaredType", f"Declared type {dc} does not have valid use functions for attack assertion"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Declared type does not have valid use functions for attack assertion")
        return dc, behavior
    
    def _assert_declared_has_targets(self, response: CardsDeclared | None = None):
        dc, behavior = self._assert_declared_is_attack(response)
        if not behavior.requires_target:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidDeclaredType", f"Declared type {dc} does not require a target"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Declared type does not require a target")
        return dc, behavior
    
    def _assert_current_target_valid(self):
        if self.target_id is None:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidPhase", "No target selected in target assertion"),
                recipients=None,
                is_private=False
            ))
            raise RuntimeError("No target selected in target assertion")
        if self.target_id not in [p.id for p in self.players]:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidTarget", f"Target id {self.target_id} is not a valid player"),
                recipients=None,
                is_private=False
            ))
            raise ValueError(f"Target id {self.target_id} is not a valid player")
        return self.get_player_from_id(self.target_id)
    
    def _assert(self, condition: bool, error_type: str, message: str) -> None:
        if not condition:
            self.emit(EventEnvelope(
                self.event_id,
                Error(error_type, message),
                recipients=None,
                is_private=False
            ))
            raise ValueError(message)

    def reset_game(self):
        self.players.extend(self.eliminated)
        self.eliminated.clear()
        self.discard.clear()
        c_ind = 0
        for ct in decks[self.deck_type]:
            for _ in range(card_amts[ct]):
                self.deck.append(Card(ct, ("deck", c_ind)))
                c_ind += 1
        self.reshuffle_deck()
        self.current_player_index = 0
        self.phase = Phase.ACTION
        self.current_request = None
        self.actor_id = None
        self.declared_claim = None
        self.played_cards = []
        self.target_id = None
        self.challenge_index = None
        self.block_target_id = None
        self.winner_id = None
        self._reset_block_state()
        for p in self.players:
            p.reset()

    def get_player_from_id(self, id: int):
        for player in self.players:
            if player.id == id:
                return player
        self.emit(EventEnvelope(
            self.event_id,
            Error("InvalidPlayerId", f"Player with id {id} does not exist"),
            recipients=None,
            is_private=False
        ))
        raise ValueError(f"Player with id {id} does not exist")
            
    def get_pile_from_id(self, pile_id: ValidPileId) -> list[Card]:
        if pile_id == "deck":
            return self.deck
        elif pile_id == "discard":
            return self.discard
        else:
            player = self.get_player_from_id(pile_id)
            return player.hand
    
    def move_card(self, card_from: CardPos, card_to: CardPos) -> Card | None:
        from_pile = self.get_pile_from_id(card_from[0])
        to_pile = self.get_pile_from_id(card_to[0])

        all_events: list[EventEnvelope] = []

        self._assert(
            -len(from_pile) <= card_from[1] < len(from_pile),
            "InvalidCardIndex",
            "Card index out of range"
        )

        if len(to_pile) >= 12 and isinstance(card_to[0], int):
            self.emit(EventEnvelope(
                self.event_id,
                Error("HandFull", f"Player with id {card_to[0]} has a full hand"),
                recipients=None,
                is_private=False
            ))
            return # Player hand limit is 12, if trying to move a card to a player's hand that already has 12 cards, ignore the move

        card = from_pile.pop(card_from[1])

        if card_to[1] == -1:
            to_pile.append(card)
        elif card_to[1] < 0:
            to_pile.insert(card_to[1] + 1, card)
        else:
            to_pile.insert(card_to[1], card)

        card.pos = card_to

        negative: set[int] = set()
        if isinstance(card_from[0], int):
            all_events.append(EventEnvelope(
                self.event_id,
                MovedFromMe(card.to_tuple(), card_to),
                recipients={card_from[0]},
                is_private=True
            ))
            negative.add(card_from[0])
        if isinstance(card_to[0], int):
            all_events.append(EventEnvelope(
                self.event_id,
                MovedToMe(card.to_tuple(), card_from),
                recipients={card_to[0]},
                is_private=True
            ))
            negative.add(card_to[0])
        all_events.append(EventEnvelope(
            self.event_id,
            CardMoved(card_from, card_to),
            recipients={p.id for p in self.players if p.id not in negative},
            is_private=False
        ))

        self.emit(all_events)
        
        self.check_for_deck_reshuffle()
        return card
    
    def steal_token(self, attacker: Player, target: Player):
        attacker.tokens += 1
        target.tokens -= 1
        self.emit(EventEnvelope(
            self.event_id,
            TokenStolen(attacker.id, target.id),
            recipients=None,
            is_private=False
        ))
        if target.tokens <= 0:
            self.eliminate(target)

    def reveal_card(self, pos: CardPos):
        pile = self.get_pile_from_id(pos[0])
        card = pile[pos[1]]
        card.revealed = True
        self.emit(EventEnvelope(
            self.event_id,
            CardRevealed(pos, card.to_tuple()),
            recipients=None,
            is_private=False
        ))
        return card
    
    def set_skip_amt(self, player: Player, new_amt: int):
        player.skip_amt = new_amt
        self.emit(EventEnvelope(
            self.event_id,
            SkipAmtChanged(player.id, new_amt),
            recipients=None,
            is_private=False
        ))

    def change_skip_amt(self, player: Player, delta: int):
        player.skip_amt += delta
        self.emit(EventEnvelope(
            self.event_id,
            SkipAmtChanged(player.id, player.skip_amt),
            recipients=None,
            is_private=False
        ))

    def eliminate(self, player: Player):
        self.players.remove(player)
        self.eliminated.append(player)
        self.emit(EventEnvelope(
            self.event_id,
            Eliminated(player.id),
            recipients=None,
            is_private=False
        ))

    def check_win_condition(self):
        if len(self.players) == 1:
            self.phase = Phase.GAME_OVER
            self.winner_id = self.players[0].id

    def check_for_deck_reshuffle(self):
        if len(self.deck) <= 0:
            self.reshuffle_deck()

    def reshuffle_deck(self):
        self.deck.extend(self.discard)
        self.discard.clear()
        r.shuffle(self.deck)

    def next_player_idx(self, player_idx: int):
        return (player_idx + 1) % len(self.players)
    
    def next_player(self):
        self.current_player_index = self.next_player_idx(self.current_player_index)
        return self.current_player
        
    def _resolve_action_phase(self):
        currents_id = self.current_player.id
        if self.current_player.skip_amt > 0:
            self.change_skip_amt(self.current_player, -1)
            self.current_player = self.next_player()
        self.current_request = ActionRequest(currents_id)

    def _resolve_declare_phase(self):
        currents_id = self.current_player.id
        self.current_request = DeclareRequest(currents_id, [c.to_tuple() for c in self.current_player.hand])
        
    def _resolve_target_phase(self):
        currents_id = self.current_player.id
        dc, behavior = self._assert_declared_is_attack()
        targets = behavior.get_targets(self)
        self.current_request = TargetRequest(currents_id, [p.id for p in targets])
    
    def _challenge_loop_iteration(self):
        if self.challenge_index is None:
            self.challenge_index = self.next_player_idx(self.current_player_index)
        else:
            self.challenge_index = self.next_player_idx(self.challenge_index)

        if self.challenge_index == self.current_player_index:
            # No one challenged, advance to block checks
            self.phase = Phase.BLOCK
            self._reset_block_state()
            self.challenge_index = None
        else:
            # Request challenge from current challenger
            challenger_id = self.players[self.challenge_index].id
            self.current_request = ChallengeRequest(challenger_id)
    
    def _get_target_list(self) -> list[Player]:
        # 1 card attacks: if requires_target is true, get targets from card_behaviors, otherwise return empty list
        # 2 card attacks: no targets, return empty list
        # 3 card attacks: all other players are targets, return list of all other player ids
        if len(self.played_cards) == 1:
            dc, behavior = self._assert_declared_is_attack()
            if behavior.requires_target:
                return behavior.get_targets(self)
            else:
                return []
        elif len(self.played_cards) == 2 or (len(self.played_cards) == 3 and len(self.players) == 2):
            return []
        else:
            return [p for p in self.players if p.id != self.current_player.id] 

    def _reset_block_state(self, resolution: bool = False):
        self.block_index = None
        self.block_target_id = None
        self.block_stack.clear()
        if not resolution:
            self.base_blocks.clear()
        self.block_passed = False

    def _continue_to_next_block_target(self):
        target_list = self._get_target_list()
        if not target_list:
            self.phase = Phase.RESOLUTION
        else:
            if self.block_index is None:
                self.block_index = 0
            else:
                self.block_index += 1
            if self.block_index >= len(target_list):
                self.phase = Phase.RESOLUTION
                self._reset_block_state(resolution=True)
            else:
                self.block_target_id = target_list[self.block_index].id
                currents_id = self.current_player.id
                dc = self._assert_declared_claim()
                self.current_request = BlockRequest(
                    player_id=self.block_target_id,
                    attacker_id=currents_id,
                    claim=dc
                )

    def _block_loop_iteration(self):
        self._assert_declared_claim()
        if self.block_passed:
            base = self._get_used_base_from_block_stack()
            attacker_id = self.block_target_id
            self._assert(attacker_id is not None, "InvalidPhase", "No current block target in block loop iteration")
            assert attacker_id is not None
            self.base_blocks[attacker_id] = base
            self.block_stack.clear()
            self.block_passed = False

            self._continue_to_next_block_target()
        else:
            if self.block_stack:
                last_block = self.block_stack[-1]
                block_target_id = last_block.target_id
                block_attacker_id = last_block.blocker_id
                block_claim = last_block.claim
                self.current_request = BlockRequest(block_target_id, block_attacker_id, block_claim)
            else:
                self._continue_to_next_block_target()

    def _clear_claim_and_advance(self):
        self.relevant_card = None
        self.declared_claim = None
        self.played_cards.clear()
        self.target_id = None
        self.next_player()
        self.phase = Phase.ACTION

    def _run_function_based_on_base_block(self, attacker, target, function):
        base = self.base_blocks.get(target.id)

        if base is None:
            function(attacker, target)
            return

        behavior = card_behaviors[base.claim]
        behavior.resolve_block(self, attacker, target, function)

    def _resolve_resolution(self):
        currents_id = self.current_player.id
        dc, behavior = self._assert_declared_is_attack()
        if not behavior.can_use(self):
            self.emit(EventEnvelope(
                self.event_id,
                UnusableNowCancelled(currents_id),
                recipients=None,
                is_private=False
            ))
            self._clear_claim_and_advance()
            return
        if len(self.played_cards) == 1:
            if not behavior.requires_relevant_card or self.relevant_card is not None:
                self._run_function_based_on_base_block(self.current_player, self._assert_current_target_valid(), lambda att, tgt: behavior.use(self, att, tgt))
                self._clear_claim_and_advance()
            else:
                if behavior.relevant_card_from_user:
                    source_player = self.current_player.id
                else:
                    target = self._assert_current_target_valid()
                    source_player = target.id
                self.current_request = ChooseRelevantCard(currents_id, source_player)
        elif len(self.played_cards) == 2:
            for _ in range(3):
                self.move_card(("deck", -1), (currents_id, -1))
            self._clear_claim_and_advance()
        elif len(self.played_cards) == 3:
            if len(self.players) == 2:
                for _ in range(5):
                    self.move_card(("deck", -1), (currents_id, -1))
                self._clear_claim_and_advance()
            else:
                # In a 3 card play with more than 2 players, all other players must give a token to the attacker, but there is no relevant card to choose, so we can just resolve the token stealing here and skip straight to the end of the action
                attacker = self.current_player
                for target in self.players:
                    if target.id != attacker.id:
                        self._run_function_based_on_base_block(attacker, target, self.steal_token)
                self._clear_claim_and_advance()

    def _advance(self):
        loop_guard = 0
        while self.current_request is None and self.phase != Phase.GAME_OVER:
            loop_guard += 1
            if loop_guard > 100:
                self.emit(EventEnvelope(
                    self.event_id,
                    Error("InfiniteLoop", "Infinite loop detected in game engine"),
                    recipients=None,
                    is_private=False
                ))
                raise RuntimeError("Infinite loop detected in game engine")
            self.phase_handlers[self.phase]()
            self.check_win_condition()

    def _get_used_base_from_block_stack(self):
        return self.block_stack[0] if len(self.block_stack) % 2 == 1 else None
        
    def _handle_block_response(self, response: BlockDecision):
        if response.challenge:
            self._resolve_block_challenge(response)
        elif response.block:
            self._add_block_to_stack(response)
        else:
            self.block_passed = True

    def _resolve_block_challenge(self, response: BlockDecision):
        if not self.block_stack:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidBlockChallenge", "No active block to challenge"),
                recipients=None,
                is_private=False
            ))
            raise RuntimeError("No active block to challenge")
        last_block = self.block_stack[-1]
        challenger = self.get_player_from_id(last_block.target_id)
        blocker = self.get_player_from_id(last_block.blocker_id)
        block_claim = last_block.claim
        last_card = self.reveal_card(last_block.pos)
        telling_truth = last_card.type == block_claim
        if telling_truth:
            for _ in range(card_behaviors[last_card.type].challenge_penalty(self)):
                self.steal_token(challenger, blocker)
        else:
            self.steal_token(blocker, challenger)
            self.block_stack.pop()
        self.block_passed = True

    def _add_block_to_stack(self, response: BlockDecision):
        currents_id = self.current_player.id
        if self.block_stack:
            last_block = self.block_stack[-1]
            if last_block.target_id != response.player_id:
                self.emit(EventEnvelope(
                    self.event_id,
                    Error("InvalidBlock", f"Player {response.player_id} cannot block, not the current target"),
                    recipients=None,
                    is_private=False
                ))
                raise ValueError("Player cannot block, not the current target")
        else:
            if response.player_id not in [p.id for p in self.players if p.id != currents_id]:
                self.emit(EventEnvelope(
                    self.event_id,
                    Error("InvalidBlock", f"Player {response.player_id} cannot block, not a valid target"),
                    recipients=None,
                    is_private=False
                ))
                raise ValueError("Player cannot block, not a valid target")
        if not response.card_pos:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidBlock", "No card position provided for block"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("No card position provided for block")
        self.move_card(response.card_pos, ("discard", -1))
        self.block_stack.append(BlockStackItem(response.player_id, currents_id, response.claim, ("discard", len(self.discard) - 1)))

    def _handle_action_response(self, response: ActionChosen):
        if response.action == "draw":
            self.move_card(("deck", -1), (self.current_player.id, -1))
            self.next_player()
        else:
            self.phase = Phase.DECLARE
            
    def _handle_declare_response(self, response: CardsDeclared):
        dc, behavior = self._assert_declared_is_attack(response)
        for idx in response.indices:
            self._assert(idx >= 0 and idx < len(self.current_player.hand), "InvalidCardIndex", f"Card index {idx} is out of bounds")
        self._assert(
            behavior.can_use(self),
            "InvalidAction",
            f"{dc} cannot be used right now"
        )
        self.declared_claim = dc
        self.played_cards = [self.current_player.hand[idx] for idx in response.indices]
        for idx in sorted(response.indices, reverse=True):
            self.move_card((self.current_player.id, idx), ("discard", -1))
        if len(self.played_cards) == 1 and behavior.requires_target:
            self.phase = Phase.TARGET
        else:
            self.emit(EventEnvelope(
                self.event_id,
                ActionPlayed(self.current_player.id, [c.to_tuple() for c in self.played_cards], dc, None),
                recipients={p.id for p in self.players if p.id != self.current_player.id},
                is_private=False
            ))
            self.phase = Phase.CHALLENGE

    def _handle_target_response(self, response: TargetChosen):
        dc, _ = self._assert_declared_is_attack()
        self._assert(response.target_id in [p.id for p in self.players], "InvalidTarget", f"Target id {response.target_id} is not a valid player")
        self.target_id = response.target_id
        self.emit(EventEnvelope(
            self.event_id,
            ActionPlayed(self.current_player.id, [c.to_tuple() for c in self.played_cards], dc, self.target_id),
            recipients={p.id for p in self.players if p.id != self.current_player.id},
            is_private=False
        ))
        self.phase = Phase.CHALLENGE

    def _handle_challenge_response(self, response: ChallengeDecision):
        self._assert(self.challenge_index is not None, "InvalidPhase", "No active challenge in challenge decision phase")
        assert self.challenge_index is not None
        challenger = self.players[self.challenge_index]
        if response.challenge:
            # Challenger has decided to challenge, resolve challenge
            dc, _ = self._assert_declared_is_attack()
            actual_types: list[CardType] = [c.type for c in self.played_cards]
            non_wild_types: list[CardType] = [t for t in actual_types if category_of_type[t] != "wild"] # all wild types can count as the declared type, so ignore them when determining the actual type(s) played
            mixed_type = dc if len(non_wild_types) == 0 else non_wild_types[0] if len(set(non_wild_types)) == 1 else None
            if (len(self.played_cards) == 1 and mixed_type == dc) or (len(self.played_cards) > 1 and mixed_type is not None): # if the player was truthful in their claim (either they played 1 card of the declared type, or they played multiple cards of the same type which [doubles and triples])
                # Player was telling the truth, challenger loses token, action proceeds as normal
                for _ in range(max(card_behaviors[ct].challenge_penalty(self) for ct in actual_types)):
                    self.steal_token(self.current_player, challenger)
                self.phase = Phase.BLOCK
                self._reset_block_state()
            else:
                # Player was lying, player loses token, action is cancelled
                self.steal_token(challenger, self.current_player)
                self.played_cards.clear()
                self.declared_claim = None
                self.target_id = None
                self.next_player()
                self.phase = Phase.ACTION

    def _handle_relevant_card_response(self, response: RelevantCardChosen):
        self._assert_declared_is_attack()
        if response.card_pos[0] != self.current_player.id and response.card_pos[0] != self.target_id:
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidRelevantCard", "Chosen relevant card does not belong to either the attacker or the target"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Chosen relevant card does not belong to either the attacker or the target")
        pile = self.get_pile_from_id(response.card_pos[0])
        if response.card_pos[1] < 0 or response.card_pos[1] >= len(pile):
            self.emit(EventEnvelope(
                self.event_id,
                Error("InvalidRelevantCard", "Chosen relevant card index is out of bounds"),
                recipients=None,
                is_private=False
            ))
            raise ValueError("Chosen relevant card index is out of bounds")
        self.relevant_card = pile[response.card_pos[1]]
        self._resolve_resolution()

    def _handle_response(self, response: Response):
        for cls, handler in self.response_handlers.items():
            if isinstance(response, cls):
                handler(response)
                return
        self.emit(EventEnvelope(
            self.event_id,
            Error("InvalidResponseType", f"{type(response)}"),
            recipients=None,
            is_private=False
        ))
        raise ValueError("Invalid response type")

    def start(self):
        self.reset_game()
        self._advance()
