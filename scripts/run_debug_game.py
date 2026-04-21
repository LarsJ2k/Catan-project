from __future__ import annotations

from catan.controllers.base import Controller
from catan.core.engine import create_initial_state
from catan.core.models.action import Action
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import TerrainType
from catan.core.models.state import InitialGameConfig
from catan.runners.debug_text_runner import DebugTextRunner


class FirstLegalController(Controller):
    def choose_action(self, observation, legal_actions):  # type: ignore[override]
        return legal_actions[0]


def make_demo_board() -> Board:
    edges = (
        Edge(id=0, node_a=0, node_b=1),
        Edge(id=1, node_a=1, node_b=2),
        Edge(id=2, node_a=2, node_b=3),
        Edge(id=3, node_a=3, node_b=4),
    )
    tiles = (
        Tile(id=0, terrain=TerrainType.FOREST, number_token=6),
        Tile(id=1, terrain=TerrainType.HILLS, number_token=8),
        Tile(id=2, terrain=TerrainType.FIELDS, number_token=5),
    )
    return Board(
        nodes=(0, 1, 2, 3, 4),
        edges=edges,
        tiles=tiles,
        node_to_adjacent_tiles={0: (0,), 1: (0,), 2: (1,), 3: (1, 2), 4: (2,)},
        node_to_adjacent_edges={0: (0,), 1: (0, 1), 2: (1, 2), 3: (2, 3), 4: (3,)},
        edge_to_adjacent_nodes={0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (3, 4)},
    )


def main() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_demo_board(), seed=42))
    controllers = {1: FirstLegalController(), 2: FirstLegalController()}
    DebugTextRunner().run(state, controllers, max_steps=40)


if __name__ == "__main__":
    main()
