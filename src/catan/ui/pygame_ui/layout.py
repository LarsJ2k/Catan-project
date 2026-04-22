from __future__ import annotations

import math
from dataclasses import dataclass

from catan.core.models.board import Board


@dataclass(frozen=True)
class BoardLayout:
    node_positions: dict[int, tuple[int, int]]
    edge_midpoints: dict[int, tuple[int, int]]
    tile_polygons: dict[int, tuple[tuple[int, int], ...]]
    tile_label_positions: dict[int, tuple[int, int]]


def build_circular_layout(board: Board, center: tuple[int, int], radius: int) -> BoardLayout:
    if board.node_positions and board.tile_to_nodes:
        return _build_from_board_geometry(board, center=center, radius=radius)

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

    return BoardLayout(node_positions=node_positions, edge_midpoints=edge_midpoints, tile_polygons={}, tile_label_positions={})


def _build_from_board_geometry(board: Board, center: tuple[int, int], radius: int) -> BoardLayout:
    min_x = min(x for x, _ in board.node_positions.values())
    max_x = max(x for x, _ in board.node_positions.values())
    min_y = min(y for _, y in board.node_positions.values())
    max_y = max(y for _, y in board.node_positions.values())

    width = max(max_x - min_x, 1e-6)
    height = max(max_y - min_y, 1e-6)
    scale = min((2 * radius) / width, (2 * radius) / height)

    def tx(x: float, y: float) -> tuple[int, int]:
        nx = int((x - (min_x + max_x) / 2) * scale + center[0])
        ny = int((y - (min_y + max_y) / 2) * scale + center[1])
        return nx, ny

    node_positions = {node_id: tx(x, y) for node_id, (x, y) in board.node_positions.items()}

    edge_midpoints: dict[int, tuple[int, int]] = {}
    for edge in board.edges:
        ax, ay = node_positions[edge.node_a]
        bx, by = node_positions[edge.node_b]
        edge_midpoints[edge.id] = ((ax + bx) // 2, (ay + by) // 2)

    tile_polygons: dict[int, tuple[tuple[int, int], ...]] = {}
    for tile_id, node_ids in board.tile_to_nodes.items():
        tile_polygons[tile_id] = tuple(node_positions[node_id] for node_id in node_ids)

    tile_label_positions = {
        tile_id: tx(cx, cy)
        for tile_id, (cx, cy) in board.tile_centers.items()
    }

    return BoardLayout(
        node_positions=node_positions,
        edge_midpoints=edge_midpoints,
        tile_polygons=tile_polygons,
        tile_label_positions=tile_label_positions,
    )
