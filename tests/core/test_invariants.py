from __future__ import annotations

from dataclasses import replace

from catan.core.engine import apply_action, create_initial_state
from catan.core.models.action import BuildCity, BuildRoad, BuildSettlement, EndTurn, PlaceSetupRoad, PlaceSetupSettlement, RollDice
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import InitialGameConfig


def make_board() -> Board:
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
        node_to_adjacent_tiles={0: (0,), 1: (0,), 2: (1,), 3: (1,), 4: (2,), 5: (2,), 6: (2,), 7: ()},
        node_to_adjacent_edges={0: (0, 7), 1: (0, 1), 2: (1, 2), 3: (2, 3), 4: (3, 4), 5: (4, 5), 6: (5, 6), 7: (6, 7)},
        edge_to_adjacent_nodes={i: (i, (i + 1) % 8) for i in range(8)},
    )


def setup_to_main_turn():
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=123))
    actions = [
        PlaceSetupSettlement(player_id=1, node_id=0),
        PlaceSetupRoad(player_id=1, edge_id=0),
        PlaceSetupSettlement(player_id=2, node_id=2),
        PlaceSetupRoad(player_id=2, edge_id=2),
        PlaceSetupSettlement(player_id=2, node_id=4),
        PlaceSetupRoad(player_id=2, edge_id=4),
        PlaceSetupSettlement(player_id=1, node_id=6),
        PlaceSetupRoad(player_id=1, edge_id=6),
    ]
    for action in actions:
        state = apply_action(state, action)
    return state


def test_node_never_both_settlement_and_city() -> None:
    state = setup_to_main_turn()
    p1 = state.players[1]
    p1 = replace(p1, resources={r: 10 for r in ResourceType})
    state = replace(state, players={**state.players, 1: p1, 2: replace(state.players[2], resources={r: 10 for r in ResourceType})})

    state = apply_action(state, RollDice(player_id=1))
    state = apply_action(state, BuildCity(player_id=1, node_id=6))

    overlap = set(state.placed.settlements.keys()) & set(state.placed.cities.keys())
    assert overlap == set()


def test_city_upgrade_replaces_settlement_occupancy() -> None:
    state = setup_to_main_turn()
    p1 = replace(state.players[1], resources={r: 10 for r in ResourceType})
    state = replace(state, players={**state.players, 1: p1})
    state = apply_action(state, RollDice(player_id=1))

    before = state.players[1].victory_points
    state = apply_action(state, BuildCity(player_id=1, node_id=0))

    assert 0 not in state.placed.settlements
    assert state.placed.cities[0] == 1
    assert state.players[1].victory_points == before + 1


def test_same_seed_and_actions_same_final_state() -> None:
    s1 = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=123))
    s2 = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=123))

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
        RollDice(player_id=2),
    ]

    for action in actions:
        s1 = apply_action(s1, action)
        s2 = apply_action(s2, action)

    assert s1 == s2
    assert s1.phase == GamePhase.MAIN_TURN
    assert s1.turn is not None and s1.turn.step == TurnStep.ACTIONS
