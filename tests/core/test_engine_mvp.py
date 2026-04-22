from __future__ import annotations

from dataclasses import replace

from catan.core.engine import (
    apply_action,
    create_initial_state,
    get_legal_actions,
)
from catan.core.models.action import (
    BuildCity,
    BuildRoad,
    BuildSettlement,
    EndTurn,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    RollDice,
)
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, InitialGameConfig, PlacedPieces, PlayerState, SetupState, TurnState


def make_test_board() -> Board:
    edges = tuple(Edge(id=i, node_a=i, node_b=(i + 1) % 8) for i in range(8))
    tiles = (
        Tile(id=0, terrain=TerrainType.FOREST, number_token=6),
        Tile(id=1, terrain=TerrainType.HILLS, number_token=8),
        Tile(id=2, terrain=TerrainType.FIELDS, number_token=5),
    )
    return Board(
        nodes=tuple(range(8)),
        edges=edges,
        tiles=tiles,
        node_to_adjacent_tiles={
            0: (0,),
            1: (0,),
            2: (1,),
            3: (1,),
            4: (2,),
            5: (2,),
            6: (2,),
            7: (),
        },
        node_to_adjacent_edges={
            0: (0, 7),
            1: (0, 1),
            2: (1, 2),
            3: (2, 3),
            4: (3, 4),
            5: (4, 5),
            6: (5, 6),
            7: (6, 7),
        },
        edge_to_adjacent_nodes={i: (i, (i + 1) % 8) for i in range(8)},
    )


def make_initial_state() -> GameState:
    return create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2),
            board=make_test_board(),
            seed=123,
        )
    )


def with_full_resources(state: GameState, player_id: int, amount: int = 10) -> GameState:
    p = state.players[player_id]
    resources = {r: amount for r in ResourceType}
    return replace(state, players={**state.players, player_id: replace(p, resources=resources)})


def test_setup_legality_and_distance_rule() -> None:
    state = make_initial_state()
    legal = get_legal_actions(state, 1)
    assert PlaceSetupSettlement(player_id=1, node_id=0) in legal

    state = apply_action(state, PlaceSetupSettlement(player_id=1, node_id=1))
    legal_next = get_legal_actions(state, 2)
    assert legal_next == []

    legal_road = get_legal_actions(state, 1)
    assert all(isinstance(a, PlaceSetupRoad) for a in legal_road)
    assert {a.edge_id for a in legal_road} == {0, 1}

    state = apply_action(state, PlaceSetupRoad(player_id=1, edge_id=0))
    legal_settle_p2 = get_legal_actions(state, 2)
    node_ids = {a.node_id for a in legal_settle_p2 if isinstance(a, PlaceSetupSettlement)}
    assert 0 not in node_ids
    assert 2 not in node_ids


def test_setup_order_forward_reverse_and_main_turn_transition() -> None:
    state = make_initial_state()
    sequence = [
        PlaceSetupSettlement(player_id=1, node_id=0),
        PlaceSetupRoad(player_id=1, edge_id=0),
        PlaceSetupSettlement(player_id=2, node_id=2),
        PlaceSetupRoad(player_id=2, edge_id=2),
        PlaceSetupSettlement(player_id=2, node_id=4),
        PlaceSetupRoad(player_id=2, edge_id=4),
        PlaceSetupSettlement(player_id=1, node_id=6),
        PlaceSetupRoad(player_id=1, edge_id=6),
    ]
    for action in sequence:
        assert action in get_legal_actions(state, action.player_id)
        state = apply_action(state, action)

    assert state.phase == GamePhase.MAIN_TURN
    assert state.turn is not None
    assert state.turn.current_player == 1
    assert state.turn.step == TurnStep.ROLL


def test_build_legality_and_costs() -> None:
    base = make_initial_state()
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}, victory_points=1),
        2: PlayerState(player_id=2, resources={r: 0 for r in ResourceType}),
    }
    state = replace(
        base,
        phase=GamePhase.MAIN_TURN,
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        players=players,
        placed=PlacedPieces(roads={0: 1}, settlements={0: 1}, cities={}),
        setup=SetupState(order=[1, 2]),
    )

    assert BuildRoad(player_id=1, edge_id=1) not in get_legal_actions(state, 1)

    state = with_full_resources(state, 1)
    legal = get_legal_actions(state, 1)
    assert BuildRoad(player_id=1, edge_id=1) in legal

    after_road = apply_action(state, BuildRoad(player_id=1, edge_id=1))
    assert after_road.players[1].resources[ResourceType.BRICK] == 9
    assert after_road.players[1].roads_left == 14
    assert BuildSettlement(player_id=1, node_id=2) in get_legal_actions(after_road, 1)
    assert BuildCity(player_id=1, node_id=0) in get_legal_actions(after_road, 1)


def test_resource_distribution_and_city_upgrade_behavior() -> None:
    board = make_test_board()
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}, victory_points=1),
        2: PlayerState(player_id=2, resources={r: 0 for r in ResourceType}),
    }
    state = GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ROLL),
        placed=PlacedPieces(roads={0: 1}, settlements={0: 1}, cities={1: 2}),
        rng_state=1,  # total=6
    )

    rolled = apply_action(state, RollDice(player_id=1))
    assert rolled.players[1].resources[ResourceType.LUMBER] == 1
    assert rolled.players[2].resources[ResourceType.LUMBER] == 2

    rich = with_full_resources(replace(rolled, turn=replace(rolled.turn, step=TurnStep.ACTIONS)), 1)
    city_state = apply_action(rich, BuildCity(player_id=1, node_id=0))
    assert 0 not in city_state.placed.settlements
    assert city_state.placed.cities[0] == 1
    assert city_state.players[1].victory_points == 2


def test_setup_second_settlement_grants_starting_resources() -> None:
    state = make_initial_state()
    steps = [
        PlaceSetupSettlement(player_id=1, node_id=0),
        PlaceSetupRoad(player_id=1, edge_id=0),
        PlaceSetupSettlement(player_id=2, node_id=2),
        PlaceSetupRoad(player_id=2, edge_id=2),
        PlaceSetupSettlement(player_id=2, node_id=4),
        PlaceSetupRoad(player_id=2, edge_id=4),
        PlaceSetupSettlement(player_id=1, node_id=6),
    ]
    for action in steps:
        state = apply_action(state, action)

    assert state.players[1].resources[ResourceType.GRAIN] == 1


def test_determinism_same_seed_same_actions() -> None:
    state_a = make_initial_state()
    state_b = make_initial_state()

    actions = [
        PlaceSetupSettlement(player_id=1, node_id=0),
        PlaceSetupRoad(player_id=1, edge_id=0),
        PlaceSetupSettlement(player_id=2, node_id=2),
        PlaceSetupRoad(player_id=2, edge_id=2),
        PlaceSetupSettlement(player_id=2, node_id=4),
        PlaceSetupRoad(player_id=2, edge_id=4),
        PlaceSetupSettlement(player_id=1, node_id=6),
        PlaceSetupRoad(player_id=1, edge_id=6),
        RollDice(player_id=1),
        EndTurn(player_id=1),
    ]

    for action in actions:
        state_a = apply_action(state_a, action)
        state_b = apply_action(state_b, action)

    assert state_a == state_b
