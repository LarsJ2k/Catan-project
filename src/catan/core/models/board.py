from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .enums import TerrainType

NodeId = int
EdgeId = int
TileId = int
PlayerId = int


@dataclass(frozen=True)
class Tile:
    id: TileId
    terrain: TerrainType
    number_token: Optional[int]


@dataclass(frozen=True)
class Edge:
    id: EdgeId
    node_a: NodeId
    node_b: NodeId


@dataclass(frozen=True)
class Board:
    nodes: tuple[NodeId, ...]
    edges: tuple[Edge, ...]
    tiles: tuple[Tile, ...]
    node_to_adjacent_tiles: dict[NodeId, tuple[TileId, ...]]
    node_to_adjacent_edges: dict[NodeId, tuple[EdgeId, ...]]
    edge_to_adjacent_nodes: dict[EdgeId, tuple[NodeId, NodeId]]
