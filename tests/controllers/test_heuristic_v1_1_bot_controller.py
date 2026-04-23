from __future__ import annotations

from catan.controllers.heuristic_v1_1_bot_controller import HeuristicV1_1BotController
from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import BuildCity, BuildRoad, BuildSettlement, BuyDevelopmentCard, EndTurn, PlaceSetupSettlement, ProposePlayerTrade
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, TurnState
from catan.core.observer import DebugObservation
from catan.runners.game_setup import ControllerType


def _new_state(seed: int = 101):
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(seed=seed), seed=seed))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    return state


def test_v1_1_penalizes_road_when_settlement_is_legal() -> None:
    state = _new_state(13)
    bot = HeuristicV1_1BotController(seed=1, enable_delay=False)

    choice = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildRoad(player_id=1, edge_id=0), BuildSettlement(player_id=1, node_id=0)],
    )

    assert isinstance(choice, BuildSettlement)


def test_v1_1_allows_meaningful_road_when_no_settlement_action_exists() -> None:
    state = _new_state(31)
    state.placed.settlements[0] = 1
    tuned = dict(default_family_parameters(ControllerType.HEURISTIC_V1_1))
    tuned["road_base_score"] = 38.0
    tuned["road_no_settlement_progress_bonus"] = 36.0
    bot = HeuristicV1_1BotController(seed=2, enable_delay=False, heuristic_params=HeuristicScoringParams.from_mapping(tuned))
    road_chosen = False
    for edge_id in range(25):
        choice = bot.choose_action(
            observation=DebugObservation(state=state),
            legal_actions=[BuildRoad(player_id=1, edge_id=edge_id), EndTurn(player_id=1)],
        )
        if isinstance(choice, BuildRoad):
            road_chosen = True
            break

    assert road_chosen is True


def test_v1_1_prefers_city_over_dev_buy_in_strong_city_situation() -> None:
    state = _new_state(41)
    bot = HeuristicV1_1BotController(seed=2, enable_delay=False)

    choice = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildCity(player_id=1, node_id=0), BuyDevelopmentCard(player_id=1)],
    )

    assert isinstance(choice, BuildCity)


def test_v1_1_dev_buy_reduced_when_near_city_vs_v1_baseline() -> None:
    state = _new_state(52)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    legal = [BuyDevelopmentCard(player_id=1), EndTurn(player_id=1)]

    v1_baseline = HeuristicV1BaselineBotController(seed=4, enable_delay=False)
    v1_1 = HeuristicV1_1BotController(seed=4, enable_delay=False)

    assert isinstance(v1_baseline.choose_action(DebugObservation(state=state), legal), BuyDevelopmentCard)
    v1_1_choice = v1_1.choose_action(DebugObservation(state=state), legal)
    if isinstance(v1_1_choice, BuyDevelopmentCard):
        reasons = v1_1.get_last_decision().get("reasons", [])  # type: ignore[union-attr]
        assert any("dev-card penalized" in reason or "dev penalty" in reason for reason in reasons)


def test_v1_1_setup_rewards_functional_profiles() -> None:
    state = _new_state(67)
    state.phase = GamePhase.SETUP_FORWARD
    bot = HeuristicV1_1BotController(seed=7, enable_delay=False)

    scores = [(node, bot._score_settlement_node(node, state, in_setup=True)) for node in state.board.nodes]
    top_node = max(scores, key=lambda item: item[1])[0]
    bottom_node = min(scores, key=lambda item: item[1])[0]

    choice = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[
            PlaceSetupSettlement(player_id=1, node_id=bottom_node),
            PlaceSetupSettlement(player_id=1, node_id=top_node),
        ],
    )

    assert choice == PlaceSetupSettlement(player_id=1, node_id=top_node)


def test_v1_1_only_selects_legal_actions_and_never_proposes_trade() -> None:
    bot = HeuristicV1_1BotController(seed=9, enable_delay=False)
    legal = [
        ProposePlayerTrade(
            player_id=1,
            offered_resources=((ResourceType.BRICK, 1),),
            requested_resources=((ResourceType.ORE, 1),),
        ),
        EndTurn(player_id=1),
    ]

    for _ in range(10):
        chosen = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert chosen in legal
        assert not isinstance(chosen, ProposePlayerTrade)
