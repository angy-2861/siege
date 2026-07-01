from .core import SiegeEngine, Player, EventEnvelope
from .api import DebugAPI

def handle_consumed_events(consumed_events: list[EventEnvelope], players: list[Player]):
    for event in consumed_events:
        for plr in players:
            if event.recipients is None or plr.id in event.recipients:
                plr.api.handle_event(event)

def main():
    plr1 = Player(DebugAPI())
    plr2 = Player(DebugAPI())
    players = [plr1, plr2]
    eng = SiegeEngine(players, [], "Normal", 8)
    handle_consumed_events(eng.consume_events(), players)
    eng.start()
    while eng.current_request != None:
        match eng.current_request.player_id:
            case plr1.id: given_response = plr1.api.handle_input(eng.current_request)
            case plr2.id: given_response = plr2.api.handle_input(eng.current_request)
            case _ as x: raise ValueError(f"Current request's respondent ID is invalid: {x}.")
        print(f"Given response: {given_response!r}")
        handle_consumed_events(eng.consume_events(), players)
        eng.submit_response(given_response)

if __name__ == '__main__':
    main()