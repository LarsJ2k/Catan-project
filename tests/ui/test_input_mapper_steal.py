from __future__ import annotations

from dataclasses import replace

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.models.action import StealResource
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState
from catan.ui.pygame_ui.input_mapper import PygameInputMapper
from catan.ui.pygame_ui.layout import BoardLayout


class DummyRect:
    def collidepoint(self, _pos) -> bool:
        return False


class DummyEvent:
    type = 1
    button = 1

    def __init__(self, pos: tuple[int, int]):
        self.pos = pos


class DummyPygame:
    KEYDOWN = 2
    MOUSEBUTTONDOWN = 1


def _state_for_steal() -> tuple[GameState, int, int]:
    board = build_classic_19_tile_board()
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}),
        2: PlayerState(player_id=2, resources={r: 1 for r in ResourceType}),
        3: PlayerState(player_id=3, resources={r: 1 for r in ResourceType}),
    }
    state = GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3]),
        turn=TurnState(current_player=1, step=TurnStep.ROBBER_STEAL, priority_player=1),
        placed=PlacedPieces(),
        rng_state=1,
        robber_tile_id=0,
    )
    tile_nodes = state.board.tile_to_nodes[0]
    node_a, node_b = tile_nodes[0], tile_nodes[1]
    state = replace(state, placed=PlacedPieces(settlements={node_a: 2, node_b: 3}, roads={}, cities={}))
    return state, node_a, node_b


def _layout_with_nodes(node_a: int, node_b: int) -> BoardLayout:
    return BoardLayout(
        node_positions={node_a: (10, 10), node_b: (100, 100)},
        edge_midpoints={},
        tile_polygons={},
        tile_label_positions={},
    )


def test_clicking_valid_victim_node_maps_to_steal_action() -> None:
    state, node_a, node_b = _state_for_steal()
    mapper = PygameInputMapper(DummyPygame())
    legal = [StealResource(player_id=1, target_player_id=2), StealResource(player_id=1, target_player_id=3)]

    result = mapper.map_event(DummyEvent((10, 10)), legal, _layout_with_nodes(node_a, node_b), DummyRect(), DummyRect(), state)
    assert result.action == StealResource(player_id=1, target_player_id=2)


def test_clicking_invalid_piece_does_nothing_for_steal() -> None:
    state, node_a, node_b = _state_for_steal()
    mapper = PygameInputMapper(DummyPygame())
    legal = [StealResource(player_id=1, target_player_id=2)]

    result = mapper.map_event(DummyEvent((100, 100)), legal, _layout_with_nodes(node_a, node_b), DummyRect(), DummyRect(), state)
    assert result.action is None
