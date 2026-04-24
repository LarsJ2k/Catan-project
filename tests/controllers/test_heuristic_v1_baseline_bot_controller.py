from __future__ import annotations

from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.controllers.heuristic_params import HeuristicScoringParams
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


def test_v1_trade_response_uses_conservative_plan_check() -> None:
    bot = HeuristicV1BaselineBotController(seed=4, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=44))
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    state.players[2].resources[ResourceType.BRICK] = 2
    state.players[2].resources[ResourceType.ORE] = 1
    state.players[2].resources[ResourceType.WOOL] = 1

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
    assert isinstance(bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal), RespondToTradePass)

    critical_state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=217))
    critical_state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    critical_state.players[1].victory_points = 3
    critical_state.players[2].resources = {
        ResourceType.BRICK: 1,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 1,
        ResourceType.ORE: 0,
    }
    critical_state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.WOOL, 1),),
        requested_resources=((ResourceType.GRAIN, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    assert isinstance(bot.choose_action(observation=DebugObservation(state=critical_state), legal_actions=legal), RespondToTradePass)


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


def test_v1_different_weight_profiles_can_pick_different_actions() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=103))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    legal = [BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]

    conservative = HeuristicV1BaselineBotController(
        seed=2,
        enable_delay=False,
        heuristic_params=HeuristicScoringParams(
            road_base_score=-20.0,
            end_turn_base_score=10.0,
            dead_road_penalty=30.0,
            dead_road_no_targets_penalty=30.0,
        ),
    )
    road_focus = HeuristicV1BaselineBotController(
        seed=2,
        enable_delay=False,
        heuristic_params=HeuristicScoringParams(
            road_base_score=40.0,
            end_turn_base_score=0.0,
            dead_road_penalty=0.0,
            dead_road_no_targets_penalty=0.0,
        ),
    )

    conservative_choice = conservative.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    road_focus_choice = road_focus.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert isinstance(conservative_choice, EndTurn)
    assert isinstance(road_focus_choice, BuildRoad)


def test_v1_rejects_useless_bank_trade_in_favor_of_end_turn() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=120))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 4,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    bot = HeuristicV1BaselineBotController(seed=1, enable_delay=False)
    legal = [EndTurn(player_id=1), BankTrade(player_id=1, offer_resource=ResourceType.WOOL, request_resource=ResourceType.BRICK, trade_rate=4)]

    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert isinstance(chosen, EndTurn)


def test_v1_accepts_bank_trade_that_enables_city() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=121))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 4,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    bot = HeuristicV1BaselineBotController(seed=1, enable_delay=False)
    trade = BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.ORE, trade_rate=4)
    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1), trade])
    assert chosen == trade


def test_v1_can_initiate_conservative_player_trade_that_enables_city() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=212))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {ResourceType.BRICK: 1, ResourceType.LUMBER: 0, ResourceType.WOOL: 0, ResourceType.GRAIN: 2, ResourceType.ORE: 2}
    state.players[2].resources[ResourceType.ORE] = 1
    bot = HeuristicV1BaselineBotController(seed=2, enable_delay=False)

    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    assert isinstance(chosen, ProposePlayerTrade)
    assert sum(amount for _, amount in chosen.offered_resources) in (1, 2)
    assert sum(amount for _, amount in chosen.requested_resources) == 1


def test_v1_player_trade_proposal_limit_defaults_to_one_and_resets_next_turn() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=213))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {ResourceType.BRICK: 1, ResourceType.LUMBER: 0, ResourceType.WOOL: 0, ResourceType.GRAIN: 2, ResourceType.ORE: 2}
    state.players[2].resources[ResourceType.ORE] = 1
    bot = HeuristicV1BaselineBotController(seed=3, enable_delay=False)

    first = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    second = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    assert isinstance(first, ProposePlayerTrade)
    assert isinstance(second, EndTurn)

    state.turn = TurnState(current_player=2, step=TurnStep.ACTIONS)
    _ = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=2)])
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    third = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    assert isinstance(third, ProposePlayerTrade)


def test_v1_player_trade_proposal_limit_can_be_two() -> None:
    params = HeuristicScoringParams(max_bot_trade_proposals_per_turn=2)
    bot = HeuristicV1BaselineBotController(seed=4, enable_delay=False, heuristic_params=params)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=214))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {ResourceType.BRICK: 2, ResourceType.LUMBER: 0, ResourceType.WOOL: 0, ResourceType.GRAIN: 2, ResourceType.ORE: 1}
    state.players[2].resources[ResourceType.ORE] = 1

    first = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    second = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    third = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[EndTurn(player_id=1)])
    assert isinstance(first, ProposePlayerTrade)
    assert isinstance(second, ProposePlayerTrade)
    assert isinstance(third, EndTurn)


def test_v1_trade_response_accepts_direct_enable_and_rejects_critical_giveaway() -> None:
    bot = HeuristicV1BaselineBotController(seed=5, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=215))
    state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    state.players[1].victory_points = 3
    state.players[2].resources = {ResourceType.BRICK: 0, ResourceType.LUMBER: 0, ResourceType.WOOL: 1, ResourceType.GRAIN: 2, ResourceType.ORE: 2}
    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.ORE, 1),),
        requested_resources=((ResourceType.WOOL, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    legal = [RespondToTradeInterested(player_id=2), RespondToTradePass(player_id=2)]
    assert isinstance(bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal), RespondToTradeInterested)

    critical_state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=217))
    critical_state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    critical_state.players[1].victory_points = 3
    critical_state.players[2].resources = {
        ResourceType.BRICK: 1,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 1,
        ResourceType.ORE: 0,
    }
    critical_state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.WOOL, 1),),
        requested_resources=((ResourceType.GRAIN, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    assert isinstance(bot.choose_action(observation=DebugObservation(state=critical_state), legal_actions=legal), RespondToTradePass)


def test_v1_trade_response_rejects_near_winning_leader() -> None:
    bot = HeuristicV1BaselineBotController(seed=6, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=216))
    state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    state.players[1].victory_points = 9
    state.players[2].resources = {ResourceType.BRICK: 0, ResourceType.LUMBER: 0, ResourceType.WOOL: 1, ResourceType.GRAIN: 2, ResourceType.ORE: 2}
    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.ORE, 1),),
        requested_resources=((ResourceType.WOOL, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    legal = [RespondToTradeInterested(player_id=2), RespondToTradePass(player_id=2)]
    assert isinstance(bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal), RespondToTradePass)
