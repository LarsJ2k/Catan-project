from __future__ import annotations

from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import (
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    EndTurn,
    MoveRobber,
    PlaceSetupSettlement,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RespondToTradePass,
)
from catan.core.models.enums import GamePhase, PlayerTradePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, PlayerTradeState, TurnState
from catan.core.observer import DebugObservation


def test_v1_bot_always_selects_legal_action() -> None:
    bot = HeuristicV1BaselineBotController(seed=7, enable_delay=False)
    legal = [EndTurn(player_id=1), BuildRoad(player_id=1, edge_id=2)]

    for _ in range(30):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert action in legal


def test_v1_bot_never_initiates_player_trade() -> None:
    bot = HeuristicV1BaselineBotController(seed=3, enable_delay=False)
    legal = [
        ProposePlayerTrade(
            player_id=1,
            offered_resources=((ResourceType.BRICK, 1),),
            requested_resources=((ResourceType.ORE, 1),),
        ),
        EndTurn(player_id=1),
    ]

    for _ in range(20):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert not isinstance(action, ProposePlayerTrade)


def test_v1_prefers_strong_settlement_over_road() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=22))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    bot = HeuristicV1BaselineBotController(seed=2, enable_delay=False)

    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildRoad(player_id=1, edge_id=0), BuildSettlement(player_id=1, node_id=0)],
    )

    assert isinstance(chosen, BuildSettlement)


def test_v1_prefers_strong_city_over_road() -> None:
    bot = HeuristicV1BaselineBotController(seed=4, enable_delay=False)
    legal = [BuildRoad(player_id=1, edge_id=6), BuildCity(player_id=1, node_id=3)]

    chosen = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]

    assert isinstance(chosen, BuildCity)


def test_v1_end_turn_beats_dead_road() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=31))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.placed.settlements[0] = 2
    state.placed.settlements[1] = 2
    state.placed.settlements[11] = 2
    state.placed.settlements[12] = 2
    bot = HeuristicV1BaselineBotController(seed=2, enable_delay=False)

    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)],
    )

    assert isinstance(chosen, EndTurn)


def test_v1_setup_prefers_scored_opening_spot_over_weak_spot() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=44))
    state.phase = GamePhase.SETUP_FORWARD
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    bot = HeuristicV1BaselineBotController(seed=12, enable_delay=False)

    scored = [
        (node_id, bot._score_settlement_node(node_id, state, in_setup=True))
        for node_id in state.board.nodes
    ]
    strong_node = max(scored, key=lambda item: item[1])[0]
    weak_node = min(scored, key=lambda item: item[1])[0]

    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[PlaceSetupSettlement(player_id=1, node_id=weak_node), PlaceSetupSettlement(player_id=1, node_id=strong_node)],
    )

    assert chosen == PlaceSetupSettlement(player_id=1, node_id=strong_node)


def test_v1_robber_avoids_self_harm_when_clear_choice_exists() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=51))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.placed.settlements[0] = 1
    state.placed.settlements[15] = 2
    bot = HeuristicV1BaselineBotController(seed=4, enable_delay=False)

    self_tile = state.board.node_to_adjacent_tiles[0][0]
    target_tile = state.board.node_to_adjacent_tiles[15][0]
    legal = [MoveRobber(player_id=1, tile_id=self_tile), MoveRobber(player_id=1, tile_id=target_tile)]

    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert chosen == MoveRobber(player_id=1, tile_id=target_tile)


def test_v1_trade_response_uses_simple_value_check() -> None:
    bot = HeuristicV1BaselineBotController(seed=4, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=44))
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    state.players[2].resources[ResourceType.BRICK] = 2
    state.players[2].resources[ResourceType.ORE] = 1

    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.ORE, 1),),
        requested_resources=((ResourceType.BRICK, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    legal = [RespondToTradeInterested(player_id=2), RespondToTradePass(player_id=2)]
    assert isinstance(bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal), RespondToTradeInterested)

    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.BRICK, 1),),
        requested_resources=((ResourceType.ORE, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    assert isinstance(bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal), RespondToTradePass)


def test_v1_prefers_dev_purchase_when_no_strong_build_exists() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=63))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 1,
        ResourceType.ORE: 1,
    }
    bot = HeuristicV1BaselineBotController(seed=1, enable_delay=False)

    choice = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[BuyDevelopmentCard(player_id=1), EndTurn(player_id=1), BankTrade(player_id=1, offer_resource=ResourceType.WOOL, request_resource=ResourceType.BRICK)],
    )

    assert isinstance(choice, BuyDevelopmentCard)
