from __future__ import annotations

from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters
from catan.controllers.heuristic_v3_lookahead_bot_controller import HeuristicV3LookaheadBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state, get_legal_actions
from catan.core.models.action import BuildRoad, DiscardResources, EndTurn, ProposePlayerTrade
from catan.core.models.enums import ResourceType
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


def test_v3_builds_valid_discard_action_from_single_placeholder() -> None:
    state = _state()
    state.players[1].resources.clear()
    state.players[1].resources.update({resource: 2 for resource in ResourceType})
    state.discard_requirements = {1: 3}
    placeholder = DiscardResources(player_id=1, resources=())
    chosen = HeuristicV3LookaheadBotController(seed=1, enable_delay=False).choose_action(DebugObservation(state=state), [placeholder])
    assert isinstance(chosen, DiscardResources)
    assert sum(amount for _, amount in chosen.resources) == 3


def test_v3_road_overbuild_penalty_is_player_specific() -> None:
    state = _state()
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    state.players[1].roads_left = 6
    state.players[1].settlements_left = 5
    state.players[2].settlements_left = 2
    legal = tuple(get_legal_actions(state, 1))
    score, flags = bot._future_option_score(state, legal[0])
    assert "road_overbuild_penalty" in flags
    assert score < 0


def test_v3_prune_keeps_endturn_when_road_not_meaningful() -> None:
    state = _state()
    bot = HeuristicV3LookaheadBotController(seed=2, enable_delay=False)
    actions = [EndTurn(player_id=1), BuildRoad(player_id=1, edge_id=0)]
    pruned = bot._prune_candidates(state, actions)
    assert any(isinstance(a, EndTurn) for a in pruned)


def test_v3_player_trade_progress_gated_not_unconditionally_pruned() -> None:
    state = _state()
    bot = HeuristicV3LookaheadBotController(seed=2, enable_delay=False)
    state.players[1].resources[ResourceType.ORE] = 1
    state.players[1].resources[ResourceType.GRAIN] = 1
    state.players[1].resources[ResourceType.WOOL] = 1
    state.players[1].resources[ResourceType.LUMBER] = 1
    state.players[2].resources[ResourceType.ORE] = 2
    trade = ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.LUMBER, 1),), requested_resources=((ResourceType.ORE, 1),))
    pruned = bot._prune_candidates(state, [EndTurn(player_id=1), trade])
    assert any(isinstance(a, ProposePlayerTrade) for a in pruned)


def test_v3_debug_includes_state_delta_fields() -> None:
    state = _state()
    bot = HeuristicV3LookaheadBotController(seed=3, enable_delay=False)
    legal_actions = tuple(get_legal_actions(state, 1))
    bot.choose_action(DebugObservation(state=state), legal_actions)
    top = bot._last_decision["top_candidates"][0]
    assert "state_before" in top
    assert "state_after" in top
    assert "state_delta" in top


def test_v3_can_initiate_player_trade_that_enables_city() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.ORE: 2, ResourceType.GRAIN: 2, ResourceType.BRICK: 1, ResourceType.LUMBER: 0, ResourceType.WOOL: 0}
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    legal = [
        ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.BRICK, 1),), requested_resources=((ResourceType.ORE, 1),)),
        EndTurn(player_id=1),
    ]
    chosen = bot.choose_action(DebugObservation(state=state), legal)
    assert isinstance(chosen, ProposePlayerTrade)


def test_v3_can_initiate_player_trade_that_enables_settlement() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.BRICK: 0, ResourceType.LUMBER: 1, ResourceType.WOOL: 1, ResourceType.GRAIN: 1, ResourceType.ORE: 1}
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    legal = [
        ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.ORE, 1),), requested_resources=((ResourceType.BRICK, 1),)),
        EndTurn(player_id=1),
    ]
    chosen = bot.choose_action(DebugObservation(state=state), legal)
    assert isinstance(chosen, ProposePlayerTrade)


def test_v3_rejects_no_benefit_player_trade() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.BRICK: 1, ResourceType.LUMBER: 1, ResourceType.WOOL: 0, ResourceType.GRAIN: 0, ResourceType.ORE: 0}
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    legal = [
        ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.BRICK, 1),), requested_resources=((ResourceType.WOOL, 1),)),
        EndTurn(player_id=1),
    ]
    chosen = bot.choose_action(DebugObservation(state=state), legal)
    assert isinstance(chosen, EndTurn)


def test_v3_rejects_goal_critical_giveaway_trade() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.ORE: 3, ResourceType.GRAIN: 2, ResourceType.BRICK: 0, ResourceType.LUMBER: 0, ResourceType.WOOL: 0}
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    legal = [
        ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.ORE, 1),), requested_resources=((ResourceType.BRICK, 1),)),
        EndTurn(player_id=1),
    ]
    chosen = bot.choose_action(DebugObservation(state=state), legal)
    assert isinstance(chosen, EndTurn)


def test_v3_trade_debug_output_includes_scoring_fields() -> None:
    state = _state()
    state.players[1].resources = {ResourceType.ORE: 2, ResourceType.GRAIN: 2, ResourceType.BRICK: 1, ResourceType.LUMBER: 0, ResourceType.WOOL: 0}
    bot = HeuristicV3LookaheadBotController(seed=1, enable_delay=False)
    legal = [
        ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.BRICK, 1),), requested_resources=((ResourceType.ORE, 1),)),
        EndTurn(player_id=1),
    ]
    bot.choose_action(DebugObservation(state=state), legal)
    candidate = next(item for item in bot._last_decision["top_candidates"] if isinstance(item["action"], ProposePlayerTrade))
    trade_debug = candidate["trade_debug"]
    assert "v2_trade_score=" in trade_debug
    assert "v3_lookahead_trade_score=" in trade_debug
    assert "state_delta=" in trade_debug
    assert "enables_city=" in trade_debug
    assert "enables_settlement=" in trade_debug
    assert "enables_dev=" in trade_debug
