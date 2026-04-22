from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import ResourceType
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
    axial: tuple[int, int] | None = None


@dataclass(frozen=True)
class Edge:
    id: EdgeId
    node_a: NodeId
    node_b: NodeId


@dataclass(frozen=True)
class Port:
    id: int
    edge_id: EdgeId
    node_ids: tuple[NodeId, NodeId]
    trade_resource: ResourceType | None

    @property
    def trade_rate(self) -> int:
        return 3 if self.trade_resource is None else 2


@dataclass(frozen=True)
class Board:
    nodes: tuple[NodeId, ...]
    edges: tuple[Edge, ...]
    tiles: tuple[Tile, ...]
    node_to_adjacent_tiles: dict[NodeId, tuple[TileId, ...]]
    node_to_adjacent_edges: dict[NodeId, tuple[EdgeId, ...]]
    edge_to_adjacent_nodes: dict[EdgeId, tuple[NodeId, NodeId]]
    tile_to_nodes: dict[TileId, tuple[NodeId, ...]] = field(default_factory=dict)
    node_positions: dict[NodeId, tuple[float, float]] = field(default_factory=dict)
    tile_centers: dict[TileId, tuple[float, float]] = field(default_factory=dict)
    ports: tuple[Port, ...] = field(default_factory=tuple)
    node_to_ports: dict[NodeId, tuple[int, ...]] = field(default_factory=dict)

    def node_neighbors(self, node_id: NodeId) -> tuple[NodeId, ...]:
        neighbors: list[NodeId] = []
        for edge_id in self.node_to_adjacent_edges.get(node_id, ()): 
            a, b = self.edge_to_adjacent_nodes[edge_id]
            neighbors.append(b if a == node_id else a)
        return tuple(neighbors)
