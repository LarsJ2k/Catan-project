from __future__ import annotations

from dataclasses import replace

from .observer import DebugObservation, Observation, PlayerObservation, PublicPlayerView
from .rng import roll_two_d6
from .models.action import Action, EndTurn, RollDice
from .models.board import PlayerId
from .models.enums import GamePhase, ResourceType, TurnStep
from .models.state import GameState


def get_legal_actions(state: GameState, player_id: PlayerId) -> list[Action]:
    if state.phase == GamePhase.GAME_OVER:
        return []

    if state.phase in (GamePhase.SETUP_FORWARD, GamePhase.SETUP_REVERSE):
        # MVP implementation will fill concrete setup placement legal moves next.
        return []

    if state.turn is None or state.turn.current_player != player_id:
        return []

    if state.turn.step == TurnStep.ROLL:
        return [RollDice(player_id=player_id)]

    return [EndTurn(player_id=player_id)]


def apply_action(state: GameState, action: Action) -> GameState:
    legal_actions = get_legal_actions(state, action.player_id)
    if action not in legal_actions:
        raise ValueError(f"Illegal action: {action}")

    if isinstance(action, RollDice):
        assert state.turn is not None
        rolled, next_rng = roll_two_d6(state.rng_state)
        next_turn = replace(state.turn, step=TurnStep.ACTIONS, last_roll=rolled)
        # Resource distribution happens here in upcoming milestone.
        return replace(state, turn=next_turn, rng_state=next_rng)

    if isinstance(action, EndTurn):
        assert state.turn is not None
        order = list(state.players.keys())
        idx = order.index(state.turn.current_player)
        next_player = order[(idx + 1) % len(order)]
        next_turn = replace(state.turn, current_player=next_player, step=TurnStep.ROLL, last_roll=None)
        return replace(state, turn=next_turn)

    raise ValueError(f"Unhandled action type: {type(action).__name__}")


def is_terminal(state: GameState) -> bool:
    return state.phase == GamePhase.GAME_OVER or state.winner is not None


def get_observation(state: GameState, player_id: PlayerId, *, debug: bool = False) -> Observation:
    if debug:
        return DebugObservation(state=state)

    own = state.players[player_id]
    own_resources = {resource.name: count for resource, count in own.resources.items()}

    players_public = tuple(
        PublicPlayerView(
            player_id=pid,
            victory_points=pstate.victory_points,
            resource_count=sum(pstate.resources.values()),
        )
        for pid, pstate in state.players.items()
    )

    return PlayerObservation(
        requesting_player_id=player_id,
        current_player_id=state.turn.current_player if state.turn else None,
        phase=state.phase.name,
        own_resources=own_resources,
        players_public=players_public,
    )
