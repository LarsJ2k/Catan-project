from __future__ import annotations

from catan.controllers.simple_goal_bot_controller import SimpleGoalBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import (
    BuildCity,
    BuildRoad,
    BuildSettlement,
    DiscardResources,
    EndTurn,
    MoveRobber,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RespondToTradePass,
)
from catan.core.models.enums import GamePhase, PlayerTradePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, PlayerTradeState, TurnState
from catan.core.observer import DebugObservation


def _main_turn_state(seed: int = 5):
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3),
            board=build_classic_19_tile_board(seed=seed),
            seed=seed,
        )
    )
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    return state


def test_city_priority_over_other_actions() -> None:
    state = _main_turn_state(13)
    bot = SimpleGoalBotController(seed=1, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [
            BuildSettlement(player_id=1, node_id=0),
            BuildCity(player_id=1, node_id=1),
            EndTurn(player_id=1),
        ],
    )

    assert isinstance(chosen, BuildCity)


def test_settlement_priority_when_city_not_possible() -> None:
    state = _main_turn_state(21)
    bot = SimpleGoalBotController(seed=2, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [
            BuildRoad(player_id=1, edge_id=0),
            BuildSettlement(player_id=1, node_id=0),
            EndTurn(player_id=1),
        ],
    )

    assert isinstance(chosen, BuildSettlement)


def test_road_behavior_only_when_no_settlement_available() -> None:
    state = _main_turn_state(31)
    state.placed.settlements[0] = 1
    bot = SimpleGoalBotController(seed=3, enable_delay=False)
    progress_edge = next(
        edge.id
        for edge in state.board.edges
        if bot._road_progress_tuple(state, edge.id)[0] > 0
    )

    with_settlement = bot.choose_action(
        DebugObservation(state=state),
        [
            BuildSettlement(player_id=1, node_id=5),
            BuildRoad(player_id=1, edge_id=progress_edge),
            EndTurn(player_id=1),
        ],
    )
    without_settlement = bot.choose_action(
        DebugObservation(state=state),
        [
            BuildRoad(player_id=1, edge_id=progress_edge),
            EndTurn(player_id=1),
        ],
    )

    assert isinstance(with_settlement, BuildSettlement)
    assert isinstance(without_settlement, BuildRoad)


def test_trade_proposal_only_when_directly_enables_goal() -> None:
    state = _main_turn_state(41)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    state.players[2].resources[ResourceType.ORE] = 1
    state.players[3].resources[ResourceType.ORE] = 1
    bot = SimpleGoalBotController(seed=4, enable_delay=False)

    direct_trade = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])
    state.players[1].resources = {
        ResourceType.BRICK: 3,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    useless = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])

    assert isinstance(direct_trade, ProposePlayerTrade)
    assert isinstance(useless, EndTurn)


def test_trade_acceptance_only_for_city_or_settlement_enable() -> None:
    state = _main_turn_state(51)
    state.turn = TurnState(current_player=1, priority_player=1, step=TurnStep.PLAYER_TRADE)
    bot = SimpleGoalBotController(seed=5, enable_delay=False)
    legal = [RespondToTradeInterested(player_id=1), RespondToTradePass(player_id=1)]

    state.players[1].resources = {
        ResourceType.BRICK: 1,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    state.player_trade = PlayerTradeState(
        proposer_player_id=2,
        offered_resources=((ResourceType.GRAIN, 1),),
        requested_resources=((ResourceType.ORE, 1),),
        responder_order=(1,),
        current_responder_index=0,
        eligible_responders=(1,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    accept = bot.choose_action(DebugObservation(state=state), legal)

    state.player_trade = PlayerTradeState(
        proposer_player_id=2,
        offered_resources=((ResourceType.WOOL, 1),),
        requested_resources=((ResourceType.BRICK, 1),),
        responder_order=(1,),
        current_responder_index=0,
        eligible_responders=(1,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    reject = bot.choose_action(DebugObservation(state=state), legal)

    assert isinstance(accept, RespondToTradeInterested)
    assert isinstance(reject, RespondToTradePass)


def test_discard_prefers_highest_count_resource() -> None:
    state = _main_turn_state(61)
    state.turn = TurnState(current_player=1, priority_player=1, step=TurnStep.DISCARD)
    state.discard_requirements = {1: 2}
    state.players[1].resources = {
        ResourceType.BRICK: 3,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    bot = SimpleGoalBotController(seed=6, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [DiscardResources(player_id=1, resources=tuple())],
    )

    assert isinstance(chosen, DiscardResources)
    assert dict(chosen.resources) == {ResourceType.BRICK: 2}


def test_robber_avoids_own_tiles_and_targets_high_value_opponents() -> None:
    state = _main_turn_state(71)
    bot = SimpleGoalBotController(seed=7, enable_delay=False)

    own_tile = next(tile.id for tile in state.board.tiles if tile.number_token not in (6, 8))
    own_node = state.board.tile_to_nodes[own_tile][0]
    state.placed.settlements[own_node] = 1
    opponent_tile = next(
        tile.id
        for tile in state.board.tiles
        if tile.id != own_tile and tile.number_token in (6, 8)
    )
    for node in state.board.tile_to_nodes[opponent_tile][:2]:
        state.placed.settlements[node] = 2

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [
            MoveRobber(player_id=1, tile_id=own_tile),
            MoveRobber(player_id=1, tile_id=opponent_tile),
        ],
    )

    assert chosen == MoveRobber(player_id=1, tile_id=opponent_tile)


def test_no_looping_useless_trades_in_no_progress_scenario() -> None:
    state = _main_turn_state(81)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    bot = SimpleGoalBotController(seed=8, enable_delay=False)
    legal = [EndTurn(player_id=1)]

    for _ in range(5):
        chosen = bot.choose_action(DebugObservation(state=state), legal)
        assert isinstance(chosen, EndTurn)
