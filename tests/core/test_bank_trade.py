from __future__ import annotations

import pytest

from catan.core.engine import apply_action, get_legal_actions
from catan.core.models.action import BankTrade, EndTurn
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.enums import TerrainType
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState


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


def make_actions_state(resources: dict[ResourceType, int]) -> GameState:
    players = {
        1: PlayerState(player_id=1, resources={r: resources.get(r, 0) for r in ResourceType}),
        2: _player_with_zero_resources(2),
    }
    return GameState(
        board=make_test_board(),
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        rng_state=123,
    )


def _player_with_zero_resources(player_id: int) -> PlayerState:
    return PlayerState(player_id=player_id, resources={r: 0 for r in ResourceType})


def test_legal_bank_trades_generated_only_for_affordable_offer_resources() -> None:
    state = make_actions_state({ResourceType.BRICK: 4, ResourceType.GRAIN: 8})

    legal = get_legal_actions(state, 1)
    bank_trades = [action for action in legal if isinstance(action, BankTrade)]

    assert len(bank_trades) == 8  # 2 offer resources * 4 different request resources
    assert BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN) in bank_trades
    assert BankTrade(player_id=1, offer_resource=ResourceType.GRAIN, request_resource=ResourceType.BRICK) in bank_trades
    assert all(action.offer_resource != action.request_resource for action in bank_trades)


def test_insufficient_resources_prevents_bank_trade() -> None:
    state = make_actions_state({ResourceType.BRICK: 3, ResourceType.GRAIN: 2})
    illegal = BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN)

    assert illegal not in get_legal_actions(state, 1)
    with pytest.raises(ValueError, match="Illegal action"):
        apply_action(state, illegal)


def test_same_resource_bank_trade_is_invalid() -> None:
    state = make_actions_state({ResourceType.BRICK: 8})
    illegal = BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.BRICK)

    assert illegal not in get_legal_actions(state, 1)
    with pytest.raises(ValueError, match="Illegal action"):
        apply_action(state, illegal)


def test_bank_trade_updates_resources_immediately() -> None:
    state = make_actions_state({ResourceType.BRICK: 4, ResourceType.GRAIN: 0})

    after = apply_action(
        state,
        BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN),
    )

    assert after.players[1].resources[ResourceType.BRICK] == 0
    assert after.players[1].resources[ResourceType.GRAIN] == 1


def test_multiple_bank_trades_in_one_turn() -> None:
    state = make_actions_state({ResourceType.BRICK: 8, ResourceType.GRAIN: 0, ResourceType.ORE: 0})

    after_first = apply_action(
        state,
        BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN),
    )
    after_second = apply_action(
        after_first,
        BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.ORE),
    )

    assert after_second.turn is not None and after_second.turn.step == TurnStep.ACTIONS
    assert after_second.players[1].resources[ResourceType.BRICK] == 0
    assert after_second.players[1].resources[ResourceType.GRAIN] == 1
    assert after_second.players[1].resources[ResourceType.ORE] == 1


def test_determinism_with_bank_trades() -> None:
    initial_resources = {ResourceType.BRICK: 8, ResourceType.GRAIN: 0, ResourceType.ORE: 0}
    state_a = make_actions_state(initial_resources)
    state_b = make_actions_state(initial_resources)

    actions = [
        BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN),
        BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.ORE),
        EndTurn(player_id=1),
    ]

    for action in actions:
        state_a = apply_action(state_a, action)
        state_b = apply_action(state_b, action)

    assert state_a == state_b
