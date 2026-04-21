from __future__ import annotations

import math
from dataclasses import dataclass

from catan.core.models.board import Board


@dataclass(frozen=True)
class BoardLayout:
    node_positions: dict[int, tuple[int, int]]
    edge_midpoints: dict[int, tuple[int, int]]


def build_circular_layout(board: Board, center: tuple[int, int], radius: int) -> BoardLayout:
    node_positions: dict[int, tuple[int, int]] = {}
    ordered_nodes = sorted(board.nodes)
    total = max(len(ordered_nodes), 1)

    for idx, node_id in enumerate(ordered_nodes):
        angle = (2 * math.pi * idx / total) - (math.pi / 2)
        x = int(center[0] + math.cos(angle) * radius)
        y = int(center[1] + math.sin(angle) * radius)
        node_positions[node_id] = (x, y)

    edge_midpoints: dict[int, tuple[int, int]] = {}
    for edge in board.edges:
        ax, ay = node_positions[edge.node_a]
        bx, by = node_positions[edge.node_b]
        edge_midpoints[edge.id] = ((ax + bx) // 2, (ay + by) // 2)

    return BoardLayout(node_positions=node_positions, edge_midpoints=edge_midpoints)
