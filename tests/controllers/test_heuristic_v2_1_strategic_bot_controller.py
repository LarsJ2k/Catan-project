from __future__ import annotations

from catan.controllers.heuristic_v2_1_strategic_bot_controller import HeuristicV2_1StrategicBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import EndTurn, ProposePlayerTrade
from catan.core.models.enums import ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, TurnState
from catan.core.observer import DebugObservation


def _state(seed: int = 44):
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(seed=seed), seed=seed))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    return state


def test_v2_1_generates_trade_candidates_from_actions_turn() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.BRICK: 1, ResourceType.LUMBER: 0, ResourceType.WOOL: 0, ResourceType.GRAIN: 2, ResourceType.ORE: 2}
    state.players[2].resources[ResourceType.ORE] = 1
    bot = HeuristicV2_1StrategicBotController(seed=1, enable_delay=False)
    chosen = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])
    assert isinstance(chosen, ProposePlayerTrade)
