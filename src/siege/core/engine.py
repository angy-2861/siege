from __future__ import annotations

from typing import Any, Callable, Self

import random as r

from .core import Player, Phase, BlockStackItem
from .events import *
from .cards import Card, CardTuple, CardType, DeclorationType, DeckType, category_of_type, decks, card_amts, ValidPileId, CardPos
from .behaviors import CardBehavior, AttackBehavior, card_behaviors
from ._handlers import *
from ._errors import fail
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
        self.sudden_siege: bool = False

        self.current_player_index: int = 0
        self.phase: Phase = Phase.ACTION
        self.current_request: Request | None = None
        self.events: list[EventEnvelope] = []
        self.event_id_counter: int = 0

        self.phase_handlers: dict[
            Phase,
            Callable[[Self], None]
        ] = {
            Phase.ACTION: resolve_action_phase,
            Phase.DECLARE: resolve_declare_phase,
            Phase.TARGET: resolve_target_phase,
            Phase.CHALLENGE: resolve_challenge_phase,
            Phase.BLOCK: resolve_block_phase,
            Phase.RESOLUTION: resolve_resolution
        }
        self.response_handlers: dict[
            type[Response],
            Callable[[Self, Any], None],
        ] = {
            ActionChosen: handle_action_response,
            CardsDeclared: handle_declare_multi_response,
            CardDeclared: handle_declare_response,
            TargetChosen: handle_target_response,
            ChallengeDecision: handle_challenge_response,
            ChosenNotBlock: handle_no_block_response,
            ChosenChallengeBlock: handle_challenge_block_response,
            ChosenBlock: handle_block_response,
            RelevantCardChosen: handle_relevant_card_response,
        }

        # Draw state
        self.player_drawn: bool = False

        # Pending action state
        self.declared_claim: DeclorationType | None = None
        self.played_cards: list[Card] = []
        self.target_id: int | None = None

        # Challenge flow
        self.challenge_index: int | None = None
        self.already_challenged: Player | None = None
        self.challenged: bool = False

        # Block flow
        self.block_index: int | None = None
        self.block_stack: list[BlockStackItem] = []
        self.base_blocks: dict[int, BlockStackItem | None] = {}
        self.blocked: bool = False

        # Resolution state
        self.relevant_card: Card | None = None

        self.winner_id: int | None = None

        # Random seed
        self.seed = seed or r.randint(1, 999_999)
        self.rng = r.Random(self.seed)

        self.reset_game()

    @property
    def current_player(self) -> Player:
        """
        The player that is currently taking their turn.
        """
        return self.players[self.current_player_index]
    
    @current_player.setter
    def current_player(self, new_player: Player):
        if new_player not in self.players:
            fail(
                self,
                "InvalidPlayer",
                f"Player with id {new_player.id} is not in the game"
            )
        self.current_player_index = self.players.index(new_player)

    def submit_response(self, response: Response) -> None:
        """
        Handles the submitted response and advances the game.

        Args:
            response: The submitted response.

        Raises:
            RuntimeError: if no response is needed right now.
            ValueError: if the response is not from the correct player.
        """
        if self.current_request is None:
            fail(
                self,
                "InvalidResponse", "No active request",
                python_error_type=RuntimeError,
            )

        if self.current_request.player_id != response.player_id:
            fail(
                self,
                "InvalidResponse",
                "Response from wrong player",
            )

        self._handle_response(response)
        self.current_request = None

        self._advance()

    def consume_events(self) -> list[EventEnvelope]:
        """
        Consumes all events and returns them.

        Returns:
            list[EventEnvelope]: The consumed events.
        """
        ev = self.events.copy()
        self.events.clear()
        return ev
    
    def _notify_observers(self, event: EventEnvelope):
        """
        Notifies the watching observers of the provided event.

        Args:
            event: The event to notify the observers of.
        """
        for obs in self.observers:
            obs.handle_event(event)

    @property
    def event_id(self) -> int:
        """
        The current event ID of the game.
        """
        return self.event_id_counter
    
    def emit(self, events: list[EventEnvelope] | EventEnvelope) -> None:
        """
        Emits all provided events, caching them for consumption and sending them to observers.

        Args:
            events: The event(s) to be emitted.
        """
        if not isinstance(events, list):
            events = [events]
        for event in events:
            self.events.append(event)
            self._notify_observers(event)
        self.event_id_counter += 1

    def _reset_challenge_state(self, blocking: bool = False) -> None:
        """
        Resets the current challenge state
        """
        self.challenge_index = None
        if not blocking:
            self.already_challenged = None
        self.challenged = False

    def _reset_block_state(self, resolution: bool = False) -> None:
        """
        Resets the current block state.

        Args:
            resolution: Whether or not this function is being called from the resolution phase.
        """
        self.block_index = None
        self.block_stack.clear()
        if not resolution:
            self.base_blocks.clear()
        self.blocked = False

    def reset_game(self) -> None:
        """
        Resets the game.
        """
        self.players.extend(self.eliminated)
        self.eliminated.clear()
        self.discard.clear()
        c_ind = 0
        for ct in decks[self.deck_type]:
            for _ in range(card_amts[ct]):
                self.deck.append(Card(ct, ("deck", c_ind)))
                c_ind += 1
        self.reshuffle_deck()
        self.sudden_siege = False
        self.current_player_index = 0
        self.phase = Phase.ACTION
        self.current_request = None
        self.declared_claim = None
        self.played_cards = []
        self.target_id = None
        self.winner_id = None
        self._reset_challenge_state()
        self._reset_block_state()
        for p in self.players:
            p.reset()
        for _ in range(2):
            for plr in self.players:
                self.move_card(("deck", -1), (plr.id, -1))
        print([[str(c) for c in plr.hand] for plr in self.players])

    def pile_to_tuples(self, pile: list[Card]) -> list[CardTuple]:
        """
        Given a pile, returns it with all inside cards encoded to CardTuples.

        Args:
            pile: The pile to encode.

        Returns:
            list[CardTuple]: The encoded pile.
        """
        return [card.to_tuple() for card in pile]

    def get_player_from_id(self, id: int) -> Player:
        """
        Given a player ID, returns the matching player.

        Args:
            id: The returned player's ID

        Returns:
            Player: The player with the given ID.

        Raises:
            ValueError: if no players in the game have the ID.
        """
        for player in self.players:
            if player.id == id:
                return player
        fail(
            self,
            "InvalidPlayerId", f"Player with id {id} does not exist",
        )

    def get_pile_from_id(self, pile_id: ValidPileId) -> list[Card]:
        """
        From a pile ID, returns the list of cards that represents that pile.

        Args:
            pile_id: the ID of the pile to be returned.

        Returns:
            list[Card]: The list of cards that represents that pile.
        """
        if pile_id == "deck":
            return self.deck
        elif pile_id == "discard":
            return self.discard
        else:
            player = self.get_player_from_id(pile_id)
            return player.hand
    
    def move_card(self, card_from: CardPos, card_to: CardPos) -> Card | None:
        """
        Moves a card.

        Args:
            card_from: The current position of the card.
            card_to: The target position of the card.

        Returns:
            Card | None: The moved card, unless it was not moved.
        """
        from_pile = self.get_pile_from_id(card_from[0])
        to_pile = self.get_pile_from_id(card_to[0])

        all_events: list[EventEnvelope] = []

        if not -len(from_pile) <= card_from[1] < len(from_pile):
            fail(
                self,
                "InvalidCardIndex",
                "Card index out of range"
            )

        if len(to_pile) >= 12 and isinstance(card_to[0], int):
            self.emit(EventEnvelope(
                self.event_id,
                HandFullIgnored(card_to[0]),
                recipients=None,
                is_private=False
            ))
            return # Player hand limit is 12, if trying to move a card to a player's hand that already has 12 cards, ignore the move

        card = from_pile.pop(card_from[1])
        for c in from_pile:
            if c.pos[1] > card.pos[1]:
                c.pos = (card_from[0], c.pos[1] - 1)

        if card_to[1] == -1:
            card.pos = (card_to[0], len(to_pile))
            to_pile.append(card)
        elif card_to[1] < 0:
            card.pos = (card_to[0], card_to[1] + len(to_pile) + 1)
            to_pile.insert(card_to[1] + 1, card)
        else:
            card.pos = card_to
            to_pile.insert(card_to[1], card)

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
    
    def steal_token(self, attacker: Player, target: Player) -> None:
        """
        Makes a player steal a token from another.

        Args:
            attacker: The player stealing the token.
            target: The player that the token is being stolen from.
        """
        steal_mul = 2 if self.sudden_siege and target.tokens >= 2 else 1
        attacker.tokens += steal_mul
        target.tokens -= steal_mul
        self.emit(EventEnvelope(
            self.event_id,
            TokenStolen(attacker.id, target.id),
            recipients=None,
            is_private=False
        ))
        if target.tokens <= 0:
            self.eliminate(target)

    def reveal_card(self, pos: CardPos) -> Card:
        """
        Reveals a card.

        Args:
            pos: The position of the card to reveal.

        Returns:
            Card: The revealed card.
        """
        pile = self.get_pile_from_id(pos[0])
        card = pile[pos[1]]
        card.revealed = True
        self.emit(EventEnvelope(
            self.event_id,
            CardRevealed(card.to_tuple()),
            recipients=None,
            is_private=False
        ))
        return card
    
    def set_skip_amt(self, player: Player, new_amt: int) -> None:
        """
        Sets the skip amount of the provided player to the provided amount.

        Args:
            player: The player to set the skip amount of.
            new_amt: The number of skips to set it to.
        """
        player.skip_amt = new_amt
        self.emit(EventEnvelope(
            self.event_id,
            SkipAmtChanged(player.id, new_amt),
            recipients=None,
            is_private=False
        ))

    def change_skip_amt(self, player: Player, delta: int) -> None:
        """
        Changes the skip amount of the provided player by the provided delta.

        Args:
            player: The player to change the skip amount of.
            delta: The number of skips to change it by.
        """
        player.skip_amt += delta
        self.emit(EventEnvelope(
            self.event_id,
            SkipAmtChanged(player.id, player.skip_amt),
            recipients=None,
            is_private=False
        ))

    def eliminate(self, player: Player) -> None:
        """
        Eliminates a player.
        """
        self.players.remove(player)
        self.eliminated.append(player)
        self.emit(EventEnvelope(
            self.event_id,
            Eliminated(player.id),
            recipients=None,
            is_private=False
        ))

    def check_win_condition(self) -> None:
        """
        Checks for win condition and Sudden Siege condition.
        
        If there is 1 player left, the game is over and the winner is the last remaining player.
        If there are 2 players left and the game did not start with 2 players, the game has entered Sudden Siege.
        """
        if len(self.players) == 1:
            self.phase = Phase.GAME_OVER
            self.winner_id = self.players[0].id
        elif len(self.players) == 2 and self.eliminated and not self.sudden_siege:
            self.sudden_siege = True
            self.emit(
                EventEnvelope(
                    self.event_id,
                    SuddenSiege(),
                    None,
                    False
                )
            )

    def check_for_deck_reshuffle(self) -> None:
        """
        Reshuffles the deck if it is empty.
        """
        if len(self.deck) == 0:
            self.reshuffle_deck()

    def reshuffle_deck(self) -> None:
        """
        Reshuffles the deck.
        """
        self.deck.extend(self.discard)
        self.discard.clear()
        self.rng.shuffle(self.deck)
        for i, card in enumerate(self.deck):
            card.pos = ("deck", i)
        self.emit(
            EventEnvelope(
                self.event_id,
                DeckReshuffled(
                    [card.to_tuple() for card in self.deck]
                ),
                None,
                False
            )
        )

    def next_player_idx(self, player_idx: int) -> int:
        """
        Returns the player index that goes after the provided player index.

        Args:
            player_idx: The index of the player that will be taken the next player of.

        Returns:
            int: The index of the player after the provided one.
        """
        return (player_idx + 1) % len(self.players)
    
    def next_player(self) -> Player:
        """
        Advances to the next player and returns them.
        
        Returns:
            Player: The new current player that has been advanced to.
        """
        self.current_player_index = self.next_player_idx(self.current_player_index)
        return self.current_player

    def _advance(self) -> None:
        """
        Advances the game state based on the current phase of the game.

        Raises:
            RuntimeError: if the advance goes on for 100 function calls without setting a request or ending the game.
        """
        loop_guard = 0
        while self.current_request is None and self.phase != Phase.GAME_OVER:
            loop_guard += 1
            if loop_guard > 100:
                fail(
                    self,
                    "InfiniteLoop",
                    "Infinite loop detected in game engine",
                    python_error_type=RuntimeError
                )
            self.phase_handlers[self.phase](self)
            self.check_win_condition()

    def _handle_response(self, response: Response) -> None:
        """
        Attempts to propagate the game state given a response

        Args:
            response: The response to propagate the game state with.

        Raises:
            NotImplementedError: if the response is not of an implemented type.
        """
        for cls, handler in self.response_handlers.items():
            if isinstance(response, cls):
                handler(self, response)
                return
        fail(
            self,
            "InvalidResponseType",
            f"Invalid response type: {type(response)}",
            python_error_type=NotImplementedError
        )

    def start(self) -> None:
        """
        Starts the game.ed
        """
        self.reset_game()
        self._advance()
