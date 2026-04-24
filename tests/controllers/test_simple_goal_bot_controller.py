from __future__ import annotations

from catan.controllers.simple_goal_bot_controller import SimpleGoalBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import (
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    DiscardResources,
    EndTurn,
    MoveRobber,
    PlayRoadBuildingCard,
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


def test_settlement_priority_over_city_when_location_exists() -> None:
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

    assert isinstance(chosen, BuildSettlement)


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


def test_city_is_chosen_when_settlement_location_exists_but_only_city_is_buildable() -> None:
    state = _main_turn_state(22)
    bot = SimpleGoalBotController(seed=22, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [
            BuildCity(player_id=1, node_id=1),
            EndTurn(player_id=1),
        ],
    )

    assert isinstance(chosen, BuildCity)


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


def test_saves_for_settlement_when_location_exists_without_resources() -> None:
    state = _main_turn_state(32)
    bot = SimpleGoalBotController(seed=32, enable_delay=False)
    state.players[1].resources = {resource: 0 for resource in ResourceType}
    state.placed.settlements[0] = 1

    path: tuple[int, int] | None = None
    for first_edge in state.board.node_to_adjacent_edges[0]:
        first_a, first_b = state.board.edge_to_adjacent_nodes[first_edge]
        first_neighbor = first_b if first_a == 0 else first_a
        for second_edge in state.board.node_to_adjacent_edges[first_neighbor]:
            if second_edge == first_edge:
                continue
            state.placed.roads = {first_edge: 1, second_edge: 1}
            if bot._has_immediate_settlement_location(state, [EndTurn(player_id=1)]):
                path = (first_edge, second_edge)
                break
        if path is not None:
            break
    assert path is not None

    progress_edge = next(edge.id for edge in state.board.edges if bot._road_progress_tuple(state, edge.id)[0] > 0)
    chosen = bot.choose_action(
        DebugObservation(state=state),
        [BuildRoad(player_id=1, edge_id=progress_edge), EndTurn(player_id=1)],
    )
    assert isinstance(chosen, EndTurn)


def test_skips_road_building_and_non_settlement_trade_when_immediate_settlement_exists() -> None:
    state = _main_turn_state(33)
    bot = SimpleGoalBotController(seed=33, enable_delay=False)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 4,
    }
    state.placed.settlements[0] = 1

    path: tuple[int, int] | None = None
    for first_edge in state.board.node_to_adjacent_edges[0]:
        first_a, first_b = state.board.edge_to_adjacent_nodes[first_edge]
        first_neighbor = first_b if first_a == 0 else first_a
        for second_edge in state.board.node_to_adjacent_edges[first_neighbor]:
            if second_edge == first_edge:
                continue
            state.placed.roads = {first_edge: 1, second_edge: 1}
            if bot._has_immediate_settlement_location(state, [EndTurn(player_id=1)]):
                path = (first_edge, second_edge)
                break
        if path is not None:
            break
    assert path is not None

    progress_edge = next(edge.id for edge in state.board.edges if bot._road_progress_tuple(state, edge.id)[0] > 0)
    trade_for_road = BankTrade(
        player_id=1,
        offer_resource=ResourceType.ORE,
        request_resource=ResourceType.BRICK,
        trade_rate=4,
        via_port_resource=None,
    )
    chosen = bot.choose_action(
        DebugObservation(state=state),
        [
            PlayRoadBuildingCard(player_id=1),
            BuildRoad(player_id=1, edge_id=progress_edge),
            trade_for_road,
            EndTurn(player_id=1),
        ],
    )

    assert isinstance(chosen, EndTurn)


def test_trade_proposal_only_when_directly_enables_goal() -> None:
    state = _main_turn_state(41)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 1,
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


def test_trade_prefers_safe_2_for_1_before_1_for_1() -> None:
    state = _main_turn_state(42)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 3,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    state.players[2].resources[ResourceType.ORE] = 1
    bot = SimpleGoalBotController(seed=40, enable_delay=False)

    chosen = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])

    assert chosen == ProposePlayerTrade(
        player_id=1,
        offered_resources=((ResourceType.WOOL, 2),),
        requested_resources=((ResourceType.ORE, 1),),
    )


def test_trade_does_not_offer_goal_critical_resources() -> None:
    state = _main_turn_state(43)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 2,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    state.players[2].resources[ResourceType.ORE] = 1
    bot = SimpleGoalBotController(seed=41, enable_delay=False)

    chosen = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])

    assert isinstance(chosen, ProposePlayerTrade)
    assert chosen.offered_resources == ((ResourceType.WOOL, 2),)


def test_trade_falls_back_to_1_for_1_when_no_safe_2_for_1() -> None:
    state = _main_turn_state(44)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 2,
    }
    state.players[2].resources[ResourceType.ORE] = 1
    bot = SimpleGoalBotController(seed=42, enable_delay=False)

    chosen = bot.choose_action(DebugObservation(state=state), [EndTurn(player_id=1)])

    assert chosen == ProposePlayerTrade(
        player_id=1,
        offered_resources=((ResourceType.WOOL, 1),),
        requested_resources=((ResourceType.ORE, 1),),
    )


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


def test_dev_buy_allowed_when_still_one_away_after_purchase() -> None:
    state = _main_turn_state(52)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 2,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 1,
    }
    bot = SimpleGoalBotController(seed=12, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [BuyDevelopmentCard(player_id=1), EndTurn(player_id=1)],
    )

    assert isinstance(chosen, BuyDevelopmentCard)


def test_dev_buy_blocked_when_purchase_breaks_one_away_state() -> None:
    state = _main_turn_state(53)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 1,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 1,
    }
    bot = SimpleGoalBotController(seed=13, enable_delay=False)

    chosen = bot.choose_action(
        DebugObservation(state=state),
        [BuyDevelopmentCard(player_id=1), EndTurn(player_id=1)],
    )

    assert isinstance(chosen, EndTurn)


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


def test_road_target_discovery_excludes_currently_buildable_nodes() -> None:
    state = _main_turn_state(82)
    state.placed.settlements[0] = 1
    bot = SimpleGoalBotController(seed=9, enable_delay=False)
    legal = [BuildSettlement(player_id=1, node_id=5), BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]

    targets = bot._valid_future_settlement_targets(state, legal)

    assert all(node_id != 5 for node_id, _ in targets)


def test_road_path_selection_reduces_distance_to_selected_target() -> None:
    state = _main_turn_state(83)
    state.placed.settlements[0] = 1
    bot = SimpleGoalBotController(seed=10, enable_delay=False)
    legal = [BuildRoad(player_id=1, edge_id=edge.id) for edge in state.board.edges]
    target = bot._select_future_settlement_target(state, legal)
    assert target is not None
    target_node, _ = target
    before = bot._distance_to_target_with_planned_roads(state, target_node, set())

    choice = bot.choose_action(DebugObservation(state=state), legal + [EndTurn(player_id=1)])

    assert isinstance(choice, BuildRoad)
    after = bot._distance_to_target_with_planned_roads(state, target_node, {choice.edge_id})
    assert before is not None and after is not None
    assert after < before


def test_road_target_tiebreak_is_deterministic_from_seed() -> None:
    state = _main_turn_state(84)
    state.placed.settlements[0] = 1
    legal = [BuildRoad(player_id=1, edge_id=edge.id) for edge in state.board.edges] + [EndTurn(player_id=1)]
    bot_a = SimpleGoalBotController(seed=123, enable_delay=False)
    bot_b = SimpleGoalBotController(seed=123, enable_delay=False)

    choice_a = bot_a.choose_action(DebugObservation(state=state), legal)
    choice_b = bot_b.choose_action(DebugObservation(state=state), legal)

    assert choice_a == choice_b


def test_road_building_card_only_played_when_valid_target_exists() -> None:
    state = _main_turn_state(85)
    state.placed.settlements[0] = 1
    bot = SimpleGoalBotController(seed=11, enable_delay=False)
    legal = [PlayRoadBuildingCard(player_id=1), BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)]

    chosen = bot.choose_action(DebugObservation(state=state), legal)
    assert isinstance(chosen, PlayRoadBuildingCard)

    blocked = _main_turn_state(86)
    blocked.placed.settlements[0] = 1
    for node_id in blocked.board.nodes:
        if node_id in blocked.placed.settlements:
            continue
        blocked.placed.settlements[node_id] = 2
    chosen_blocked = bot.choose_action(
        DebugObservation(state=blocked),
        [PlayRoadBuildingCard(player_id=1), BuildRoad(player_id=1, edge_id=0), EndTurn(player_id=1)],
    )
    assert isinstance(chosen_blocked, EndTurn)
