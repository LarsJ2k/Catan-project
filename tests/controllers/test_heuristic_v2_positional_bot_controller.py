from __future__ import annotations

import copy

from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters
from catan.controllers.heuristic_v1_baseline_bot_controller import _TERRAIN_TO_RESOURCE
from catan.controllers.heuristic_v2_positional_bot_controller import HeuristicV2PositionalBotController
from catan.controllers.heuristic_v2_profiling import GLOBAL_V2_PROFILING_STATS
from catan.controllers.heuristic_v2_position_evaluator import HeuristicV2PositionEvaluator
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state
from catan.core.models.action import BankTrade, BuildCity, BuildRoad, BuildSettlement, DiscardResources, EndTurn, ProposePlayerTrade
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, TurnState
from catan.core.observer import DebugObservation
from catan.runners.game_setup import ControllerType


def _state(seed: int = 100) -> object:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(seed=seed), seed=seed))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    return state


def test_v2_only_selects_legal_actions_and_never_initiates_trade() -> None:
    bot = HeuristicV2PositionalBotController(seed=4, enable_delay=False)
    legal = [
        ProposePlayerTrade(
            player_id=1,
            offered_resources=((ResourceType.BRICK, 1),),
            requested_resources=((ResourceType.ORE, 1),),
        ),
        EndTurn(player_id=1),
    ]

    for _ in range(12):
        chosen = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert chosen in legal
        assert not isinstance(chosen, ProposePlayerTrade)


def test_v2_candidate_evaluation_does_not_mutate_real_state() -> None:
    state = _state(101)
    before = copy.deepcopy(state)
    bot = HeuristicV2PositionalBotController(seed=8, enable_delay=False)

    _ = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)],
    )

    assert state == before
    assert state.rng_state == before.rng_state


def test_v2_lightweight_clone_matches_deepcopy_for_apply_action() -> None:
    state = _state(107)
    state.phase = GamePhase.MAIN_TURN
    bot = HeuristicV2PositionalBotController(seed=8, enable_delay=False)
    action = EndTurn(player_id=1)

    lightweight = bot._clone_state_for_simulation(state)
    deep = copy.deepcopy(state)
    lightweight_after = apply_action(lightweight, action)
    deep_after = apply_action(deep, action)

    assert lightweight_after == deep_after
    assert state.placed.roads == {}


def test_v2_is_deterministic_for_same_seed_state_and_params() -> None:
    state = _state(102)
    params = HeuristicScoringParams.from_mapping(default_family_parameters(ControllerType.HEURISTIC_V2_POSITIONAL))
    bot_a = HeuristicV2PositionalBotController(seed=11, enable_delay=False, heuristic_params=params)
    bot_b = HeuristicV2PositionalBotController(seed=11, enable_delay=False, heuristic_params=params)
    legal = [BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]

    choice_a = bot_a.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    choice_b = bot_b.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert choice_a == choice_b


def test_v2_prefers_strong_settlement_over_weak_road() -> None:
    state = _state(103)
    bot = HeuristicV2PositionalBotController(seed=2, enable_delay=False)

    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildRoad(player_id=1, edge_id=0), BuildSettlement(player_id=1, node_id=0)],
    )
    assert isinstance(chosen, BuildSettlement)


def test_v2_prefers_city_over_dev_like_low_value_trade_action() -> None:
    state = _state(104)
    state.players[1].resources[ResourceType.WOOL] = 4
    bot = HeuristicV2PositionalBotController(seed=5, enable_delay=False)

    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[
            BuildCity(player_id=1, node_id=0),
            BankTrade(player_id=1, offer_resource=ResourceType.WOOL, request_resource=ResourceType.BRICK),
        ],
    )
    assert isinstance(chosen, BuildCity)


def test_v2_builds_valid_discard_action_from_placeholder() -> None:
    state = _state(106)
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=1, step=TurnStep.DISCARD)
    state.discard_requirements = {1: 3}
    state.players[1].resources = {
        ResourceType.BRICK: 2,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 1,
    }
    bot = HeuristicV2PositionalBotController(seed=5, enable_delay=False)

    action = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[DiscardResources(player_id=1, resources=tuple())],
    )

    assert isinstance(action, DiscardResources)
    assert sum(amount for _, amount in action.resources) == 3


def test_position_evaluator_rewards_vp_and_production_and_penalties() -> None:
    evaluator = HeuristicV2PositionEvaluator()
    params = HeuristicScoringParams.from_mapping(default_family_parameters(ControllerType.HEURISTIC_V2_POSITIONAL))

    base = _state(105)
    low = evaluator.evaluate(base, 1, params).total_score

    high_vp = copy.deepcopy(base)
    high_vp.players[1].victory_points = 4
    assert evaluator.evaluate(high_vp, 1, params).total_score > low

    high_prod = copy.deepcopy(base)
    high_prod.placed.settlements[0] = 1
    assert evaluator.evaluate(high_prod, 1, params).total_score > low

    blocked = copy.deepcopy(high_prod)
    blocked.robber_tile_id = blocked.board.node_to_adjacent_tiles[0][0]
    assert evaluator.evaluate(blocked, 1, params).total_score < evaluator.evaluate(high_prod, 1, params).total_score

    punitive_params = HeuristicScoringParams.from_mapping(default_family_parameters(ControllerType.HEURISTIC_V2_POSITIONAL))
    punitive_params = HeuristicScoringParams.from_mapping(
        {**punitive_params.as_dict(), "road_overbuild_penalty": 12.0, "road_potential_weight": 0.5}
    )
    overbuilt = copy.deepcopy(base)
    overbuilt.placed.settlements[0] = 1
    for edge_id in range(10):
        overbuilt.placed.roads[edge_id] = 1
    assert evaluator.evaluate(overbuilt, 1, punitive_params).total_score < evaluator.evaluate(high_prod, 1, punitive_params).total_score


def test_board_evaluation_cache_matches_uncached_node_calculations() -> None:
    state = _state(108)
    evaluator = HeuristicV2PositionEvaluator()
    cache = evaluator._get_board_cache(state.board)

    for node_id in state.board.nodes[:8]:
        assert cache.node_data[node_id].pip_score == evaluator._node_quality(state, node_id)
        resources = []
        for tile_id in state.board.node_to_adjacent_tiles[node_id]:
            tile = evaluator._tile_by_id(state, tile_id)
            resource = _TERRAIN_TO_RESOURCE.get(tile.terrain)
            if resource is not None:
                resources.append(resource)
        assert cache.node_data[node_id].resource_diversity == len(set(resources))


def test_expansion_cache_path_matches_uncached_expansion_score() -> None:
    state = _state(109)
    state.placed.settlements[0] = 1
    state.placed.roads[0] = 1
    evaluator = HeuristicV2PositionEvaluator()
    cached = evaluator._expansion_potential(state, 1, evaluator._get_board_cache(state.board))
    uncached = evaluator._expansion_potential_uncached(state, 1)
    assert cached == uncached


def test_v2_profiling_can_be_enabled_or_disabled() -> None:
    state = _state(150)
    legal = [BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]
    GLOBAL_V2_PROFILING_STATS.reset()

    disabled_bot = HeuristicV2PositionalBotController(seed=3, enable_delay=False, enable_v2_profiling=False)
    _ = disabled_bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert GLOBAL_V2_PROFILING_STATS.decision_count == 0

    enabled_bot = HeuristicV2PositionalBotController(seed=3, enable_delay=False, enable_v2_profiling=True)
    _ = enabled_bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert GLOBAL_V2_PROFILING_STATS.decision_count == 1

    summary = GLOBAL_V2_PROFILING_STATS.summary()
    assert summary["decisions"] == 1
    assert summary["avg_decision_ms"] >= 0.0
    assert "state_copy" in summary["avg_time_by_category_ms"]


def test_v2_profiling_does_not_change_selected_action() -> None:
    state = _state(151)
    legal = [BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]

    unprofiled = HeuristicV2PositionalBotController(seed=22, enable_delay=False, enable_v2_profiling=False)
    profiled = HeuristicV2PositionalBotController(seed=22, enable_delay=False, enable_v2_profiling=True)

    assert unprofiled.choose_action(DebugObservation(state=state), legal) == profiled.choose_action(
        DebugObservation(state=state), legal
    )
