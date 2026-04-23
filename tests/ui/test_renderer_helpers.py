from __future__ import annotations

from dataclasses import replace

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import BuildRoad, BuildSettlement, EndTurn, MoveRobber, PlaceSetupRoad, RollDice, StealResource
from catan.core.models.enums import ResourceType
from catan.core.models.state import InitialGameConfig, PlacedPieces
from catan.ui.pygame_ui.renderer import PygameRenderer, extract_legal_targets, probability_dot_count


def test_extract_legal_targets_splits_nodes_edges_tiles_and_buttons() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=1))
    legal = [
        BuildSettlement(player_id=1, node_id=4),
        BuildRoad(player_id=1, edge_id=7),
        PlaceSetupRoad(player_id=1, edge_id=2),
        MoveRobber(player_id=1, tile_id=5),
        RollDice(player_id=1),
        EndTurn(player_id=1),
    ]
    nodes, edges, tiles, steal_nodes, can_roll, can_end = extract_legal_targets(state, legal)

    assert nodes == set()
    assert edges == {2}
    assert tiles == {5}
    assert steal_nodes == set()
    assert can_roll is True
    assert can_end is True


def test_extract_legal_targets_only_shows_selected_build_mode() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=1))
    legal = [BuildSettlement(player_id=1, node_id=4), BuildRoad(player_id=1, edge_id=7)]

    settlement_nodes, settlement_edges, *_ = extract_legal_targets(state, legal, build_mode="settlement")
    road_nodes, road_edges, *_ = extract_legal_targets(state, legal, build_mode="road")

    assert settlement_nodes == {4}
    assert settlement_edges == set()
    assert road_nodes == set()
    assert road_edges == {7}


def test_extract_legal_targets_includes_steal_nodes_for_current_robber_tile() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=1))
    tile = next(t for t in state.board.tiles if t.id != state.robber_tile_id)
    node = state.board.tile_to_nodes[tile.id][0]
    players = dict(state.players)
    players[2] = replace(players[2], resources={r: 1 for r in ResourceType})
    state = replace(state, robber_tile_id=tile.id, players=players, placed=PlacedPieces(settlements={node: 2}, roads={}, cities={}))

    _, _, _, steal_nodes, _, _ = extract_legal_targets(state, [StealResource(player_id=1, target_player_id=2)])
    assert steal_nodes == {node}


def test_probability_dot_count_mapping() -> None:
    assert probability_dot_count(2) == 1
    assert probability_dot_count(6) == 5
    assert probability_dot_count(7) == 0
    assert probability_dot_count(None) == 0


def test_scoreboard_vp_text_includes_largest_army_and_longest_road_bonus() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=1))
    state = replace(
        state,
        largest_army_holder=1,
        longest_road_holder=1,
        players={**state.players, 1: replace(state.players[1], victory_points=3)},
    )

    renderer = PygameRenderer.__new__(PygameRenderer)
    vp_text = renderer._scoreboard_vp_text(state, player_id=1)
    assert vp_text == "VP 7"
