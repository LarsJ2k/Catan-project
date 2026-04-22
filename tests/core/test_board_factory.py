from __future__ import annotations

from dataclasses import replace

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import BuildRoad, EndTurn, PlaceSetupRoad, PlaceSetupSettlement, RollDice
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, PlacedPieces, SetupState, TurnState
from catan.core.rng import roll_two_d6


def _seed_for_total(total: int) -> int:
    for seed in range(1, 2_000_000):
        dice, _ = roll_two_d6(seed)
        if sum(dice) == total:
            return seed
    raise AssertionError("No seed found for desired total")


def test_classic_board_graph_consistency() -> None:
    board = build_classic_19_tile_board()

    assert len(board.tiles) == 19
    assert len(board.nodes) == 54
    assert len(board.edges) == 72

    for tile_id, nodes in board.tile_to_nodes.items():
        assert len(nodes) == 6
        for node_id in nodes:
            assert tile_id in board.node_to_adjacent_tiles[node_id]


def test_adjacent_tiles_share_nodes_and_edges() -> None:
    board = build_classic_19_tile_board()
    shared_node_pairs = 0
    shared_edge_pairs = 0

    tile_nodes = board.tile_to_nodes
    edge_to_nodes = {edge.id: {edge.node_a, edge.node_b} for edge in board.edges}

    for a in range(len(board.tiles)):
        for b in range(a + 1, len(board.tiles)):
            nodes_a = set(tile_nodes[a])
            nodes_b = set(tile_nodes[b])
            shared_nodes = nodes_a & nodes_b
            if len(shared_nodes) == 2:
                shared_node_pairs += 1
                has_shared_edge = any(edge_nodes == shared_nodes for edge_nodes in edge_to_nodes.values())
                assert has_shared_edge
                shared_edge_pairs += 1

    assert shared_node_pairs > 0
    assert shared_edge_pairs > 0


def test_resource_payout_uses_correct_adjacent_tiles() -> None:
    board = build_classic_19_tile_board()
    non_desert = next(tile for tile in board.tiles if tile.number_token is not None)
    target_node = board.tile_to_nodes[non_desert.id][0]

    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=board, seed=1))
    players = {
        1: replace(state.players[1], resources={r: 0 for r in ResourceType}, victory_points=1),
        2: replace(state.players[2], resources={r: 0 for r in ResourceType}),
    }
    state = replace(
        state,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ROLL),
        placed=PlacedPieces(roads={}, settlements={target_node: 1}, cities={}),
        rng_state=_seed_for_total(non_desert.number_token),
    )

    after = apply_action(state, RollDice(player_id=1))
    gained = sum(after.players[1].resources.values())
    assert gained == 1


def test_setup_and_main_turn_legality_on_classic_board() -> None:
    board = build_classic_19_tile_board()
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=123))

    # Setup has many legal nodes.
    legal_setup = get_legal_actions(state, 1)
    settlements = [a for a in legal_setup if isinstance(a, PlaceSetupSettlement)]
    assert len(settlements) > 10

    # Drive setup with first legal actions until main turn.
    guard = 200
    while state.phase != GamePhase.MAIN_TURN and guard > 0:
        guard -= 1
        actor = state.setup.pending_settlement_player or state.setup.pending_road_player
        assert actor is not None
        legal = get_legal_actions(state, actor)
        assert legal
        state = apply_action(state, legal[0])

    assert state.phase == GamePhase.MAIN_TURN
    current = state.turn.current_player
    legal_main = get_legal_actions(state, current)
    assert any(isinstance(a, RollDice) for a in legal_main)

    # Roll then ensure there are actions available (at least EndTurn).
    state = apply_action(state, next(a for a in legal_main if isinstance(a, RollDice)))
    legal_after_roll = get_legal_actions(state, current)
    assert any(isinstance(a, EndTurn) for a in legal_after_roll)

    # Ensure expansion graph can offer road options once resources are provided.
    rich_player = replace(state.players[current], resources={r: 10 for r in ResourceType})
    state = replace(state, players={**state.players, current: rich_player})
    legal_rich = get_legal_actions(state, current)
    assert any(isinstance(a, BuildRoad) for a in legal_rich)
