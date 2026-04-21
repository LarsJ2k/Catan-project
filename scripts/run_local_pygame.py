from __future__ import annotations

import pygame

from catan.controllers.human_controller import HumanController
from catan.core.engine import create_initial_state
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import TerrainType
from catan.core.models.state import InitialGameConfig
from catan.ui.pygame_ui.app import PygameApp


def make_demo_board() -> Board:
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


def main() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_demo_board(), seed=123))
    controllers = {1: HumanController(), 2: HumanController()}
    PygameApp(pygame).run(state, controllers)


if __name__ == "__main__":
    main()
