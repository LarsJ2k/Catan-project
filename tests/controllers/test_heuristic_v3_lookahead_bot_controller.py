from __future__ import annotations

from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters
from catan.controllers.heuristic_v3_lookahead_bot_controller import HeuristicV3LookaheadBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state, get_legal_actions
from catan.core.models.action import EndTurn
from catan.core.models.state import InitialGameConfig
from catan.core.observer import DebugObservation
from catan.runners.game_setup import ControllerType


def _state():
    return create_initial_state(InitialGameConfig(board=build_classic_19_tile_board(), player_ids=(1, 2, 3, 4), seed=7))


def test_v3_selects_legal_action_and_is_deterministic() -> None:
    state = _state()
    legal_actions = tuple(get_legal_actions(state, 1))
    params = HeuristicScoringParams.from_mapping(default_family_parameters(ControllerType.HEURISTIC_V3_LOOKAHEAD))
    first = HeuristicV3LookaheadBotController(seed=11, enable_delay=False, heuristic_params=params).choose_action(DebugObservation(state=state), legal_actions)
    second = HeuristicV3LookaheadBotController(seed=11, enable_delay=False, heuristic_params=params).choose_action(DebugObservation(state=state), legal_actions)
    assert first in legal_actions
    assert first == second


def test_v3_keeps_end_turn_when_only_safe_option() -> None:
    state = _state()
    action = HeuristicV3LookaheadBotController(seed=3, enable_delay=False).choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])
    assert isinstance(action, EndTurn)
