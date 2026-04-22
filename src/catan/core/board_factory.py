from __future__ import annotations

import math

from .models.board import Board, Edge, Tile
from .models.enums import TerrainType


def build_classic_19_tile_board() -> Board:
    """Build a deterministic classic 19-hex Catan board graph (3-4-5-4-3)."""
    axial_coords = _radius_two_axial_coords()

    # Fixed deterministic MVP layout (can randomize later without changing graph generation).
    terrain_sequence = [
        TerrainType.FOREST,
        TerrainType.HILLS,
        TerrainType.PASTURE,
        TerrainType.FIELDS,
        TerrainType.MOUNTAINS,
        TerrainType.FOREST,
        TerrainType.HILLS,
        TerrainType.PASTURE,
        TerrainType.FIELDS,
        TerrainType.MOUNTAINS,
        TerrainType.FOREST,
        TerrainType.HILLS,
        TerrainType.PASTURE,
        TerrainType.FIELDS,
        TerrainType.MOUNTAINS,
        TerrainType.FOREST,
        TerrainType.HILLS,
        TerrainType.PASTURE,
        TerrainType.DESERT,
    ]
    number_sequence = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11, None]

    node_key_to_id: dict[tuple[int, int], int] = {}
    node_positions: dict[int, tuple[float, float]] = {}
    tile_to_nodes: dict[int, tuple[int, ...]] = {}
    node_to_adjacent_tiles: dict[int, set[int]] = {}

    edge_key_to_id: dict[tuple[int, int], int] = {}
    edges: list[Edge] = []
    node_to_adjacent_edges: dict[int, set[int]] = {}

    tiles: list[Tile] = []
    tile_centers: dict[int, tuple[float, float]] = {}

    for tile_id, (q, r) in enumerate(axial_coords):
        terrain = terrain_sequence[tile_id]
        token = number_sequence[tile_id] if terrain != TerrainType.DESERT else None
        tile = Tile(id=tile_id, terrain=terrain, number_token=token, axial=(q, r))
        tiles.append(tile)

        cx, cy = _axial_to_cartesian(q, r)
        tile_centers[tile_id] = (cx, cy)

        corner_ids: list[int] = []
        corner_positions = _hex_corners(cx, cy)
        for corner in corner_positions:
            key = (round(corner[0] * 1000), round(corner[1] * 1000))
            if key not in node_key_to_id:
                node_id = len(node_key_to_id)
                node_key_to_id[key] = node_id
                node_positions[node_id] = corner
            node_id = node_key_to_id[key]
            corner_ids.append(node_id)
            node_to_adjacent_tiles.setdefault(node_id, set()).add(tile_id)

        tile_to_nodes[tile_id] = tuple(corner_ids)

        for i in range(6):
            a = corner_ids[i]
            b = corner_ids[(i + 1) % 6]
            edge_key = tuple(sorted((a, b)))
            if edge_key not in edge_key_to_id:
                edge_id = len(edge_key_to_id)
                edge_key_to_id[edge_key] = edge_id
                edges.append(Edge(id=edge_id, node_a=edge_key[0], node_b=edge_key[1]))
            edge_id = edge_key_to_id[edge_key]
            node_to_adjacent_edges.setdefault(a, set()).add(edge_id)
            node_to_adjacent_edges.setdefault(b, set()).add(edge_id)

    edge_to_adjacent_nodes = {edge.id: (edge.node_a, edge.node_b) for edge in edges}

    return Board(
        nodes=tuple(sorted(node_key_to_id.values())),
        edges=tuple(edges),
        tiles=tuple(tiles),
        node_to_adjacent_tiles={k: tuple(sorted(v)) for k, v in node_to_adjacent_tiles.items()},
        node_to_adjacent_edges={k: tuple(sorted(v)) for k, v in node_to_adjacent_edges.items()},
        edge_to_adjacent_nodes=edge_to_adjacent_nodes,
        tile_to_nodes=tile_to_nodes,
        node_positions=node_positions,
        tile_centers=tile_centers,
    )


def _radius_two_axial_coords() -> list[tuple[int, int]]:
    coords: list[tuple[int, int]] = []
    radius = 2
    for r in range(-radius, radius + 1):
        q_min = max(-radius, -r - radius)
        q_max = min(radius, -r + radius)
        for q in range(q_min, q_max + 1):
            coords.append((q, r))
    return coords


def _axial_to_cartesian(q: int, r: int) -> tuple[float, float]:
    x = math.sqrt(3) * (q + r / 2)
    y = 1.5 * r
    return x, y


def _hex_corners(cx: float, cy: float, size: float = 1.0) -> list[tuple[float, float]]:
    corners: list[tuple[float, float]] = []
    for i in range(6):
        angle_rad = math.radians(60 * i - 30)
        x = cx + size * math.cos(angle_rad)
        y = cy + size * math.sin(angle_rad)
        corners.append((x, y))
    return corners
