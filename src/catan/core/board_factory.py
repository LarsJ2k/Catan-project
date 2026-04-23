from __future__ import annotations

import math
from typing import TypeVar

from .models.board import Board, Edge, Port, Tile
from .models.enums import ResourceType, TerrainType
from .rng import next_u32

T = TypeVar("T")


def build_classic_19_tile_board(seed: int | None = None) -> Board:
    """Build a deterministic classic 19-hex Catan board graph (3-4-5-4-3)."""
    axial_coords = _radius_two_axial_coords()

    terrain_sequence, number_sequence = _resolve_tile_layout(seed)

    node_key_to_id: dict[tuple[int, int], int] = {}
    node_positions: dict[int, tuple[float, float]] = {}
    tile_to_nodes: dict[int, tuple[int, ...]] = {}
    node_to_adjacent_tiles: dict[int, set[int]] = {}

    edge_key_to_id: dict[tuple[int, int], int] = {}
    edges: list[Edge] = []
    node_to_adjacent_edges: dict[int, set[int]] = {}
    edge_to_adjacent_tiles: dict[int, set[int]] = {}

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
            edge_to_adjacent_tiles.setdefault(edge_id, set()).add(tile_id)

    edge_to_adjacent_nodes = {edge.id: (edge.node_a, edge.node_b) for edge in edges}
    ports, node_to_ports = _build_ports(edge_to_adjacent_tiles, edge_to_adjacent_nodes, node_positions, seed=seed)

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
        ports=ports,
        node_to_ports=node_to_ports,
    )


def _resolve_tile_layout(seed: int | None) -> tuple[list[TerrainType], list[int | None]]:
    # Fixed deterministic MVP layout.
    deterministic_terrain = [
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
    deterministic_numbers = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11, None]
    if seed is None:
        return deterministic_terrain, deterministic_numbers

    terrain_pool = [t for t in deterministic_terrain if t != TerrainType.DESERT]
    number_pool = [token for token in deterministic_numbers if token is not None]
    terrain_pool = _shuffle_with_seed(terrain_pool, seed)
    number_pool = _shuffle_with_seed(number_pool, seed ^ 0x9E3779B9)

    terrain_sequence: list[TerrainType] = []
    number_sequence: list[int | None] = []
    terrain_index = 0
    number_index = 0
    desert_index = _rand_below(seed ^ 0xA5A5A5A5, 19)

    for tile_idx in range(19):
        if tile_idx == desert_index:
            terrain_sequence.append(TerrainType.DESERT)
            number_sequence.append(None)
        else:
            terrain_sequence.append(terrain_pool[terrain_index])
            number_sequence.append(number_pool[number_index])
            terrain_index += 1
            number_index += 1
    return terrain_sequence, number_sequence


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


def _build_ports(
    edge_to_adjacent_tiles: dict[int, set[int]],
    edge_to_adjacent_nodes: dict[int, tuple[int, int]],
    node_positions: dict[int, tuple[float, float]],
    *,
    seed: int | None,
) -> tuple[tuple[Port, ...], dict[int, tuple[int, ...]]]:
    coastal_edges = [edge_id for edge_id, tiles in edge_to_adjacent_tiles.items() if len(tiles) == 1]
    sorted_coastal = sorted(
        coastal_edges,
        key=lambda edge_id: _edge_midpoint_angle(edge_to_adjacent_nodes[edge_id], node_positions),
    )
    step = len(sorted_coastal) / 9
    selected_edges: list[int] = []
    used: set[int] = set()
    for idx in range(9):
        edge_index = int(round(idx * step)) % len(sorted_coastal)
        while sorted_coastal[edge_index] in used:
            edge_index = (edge_index + 1) % len(sorted_coastal)
        selected_edges.append(sorted_coastal[edge_index])
        used.add(sorted_coastal[edge_index])

    port_resources: list[ResourceType | None] = [
        None,
        ResourceType.BRICK,
        None,
        ResourceType.LUMBER,
        None,
        ResourceType.GRAIN,
        None,
        ResourceType.ORE,
        ResourceType.WOOL,
    ]
    if seed is not None:
        port_resources = _shuffle_with_seed(port_resources, seed ^ 0xB4B82E39)
    ports: list[Port] = []
    node_to_port_ids: dict[int, list[int]] = {}
    for port_id, (edge_id, trade_resource) in enumerate(zip(selected_edges, port_resources, strict=True)):
        node_ids = edge_to_adjacent_nodes[edge_id]
        ports.append(Port(id=port_id, edge_id=edge_id, node_ids=node_ids, trade_resource=trade_resource))
        for node_id in node_ids:
            node_to_port_ids.setdefault(node_id, []).append(port_id)
    return tuple(ports), {node_id: tuple(sorted(port_ids)) for node_id, port_ids in node_to_port_ids.items()}


def _edge_midpoint_angle(edge_nodes: tuple[int, int], node_positions: dict[int, tuple[float, float]]) -> float:
    ax, ay = node_positions[edge_nodes[0]]
    bx, by = node_positions[edge_nodes[1]]
    mx = (ax + bx) / 2
    my = (ay + by) / 2
    return math.atan2(my, mx)


def _shuffle_with_seed(values: list[T], seed: int) -> list[T]:
    shuffled = list(values)
    rng_state = seed
    for idx in range(len(shuffled) - 1, 0, -1):
        rng_value, rng_state = next_u32(rng_state)
        swap_idx = rng_value % (idx + 1)
        shuffled[idx], shuffled[swap_idx] = shuffled[swap_idx], shuffled[idx]
    return shuffled


def _rand_below(seed: int, modulo: int) -> int:
    value, _ = next_u32(seed)
    return value % modulo
