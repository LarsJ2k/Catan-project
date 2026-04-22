from __future__ import annotations

from dataclasses import dataclass

from .board import EdgeId, NodeId, PlayerId, TileId
from .enums import ResourceType


@dataclass(frozen=True)
class ActionBase:
    player_id: PlayerId


@dataclass(frozen=True)
class PlaceSetupSettlement(ActionBase):
    node_id: NodeId


@dataclass(frozen=True)
class PlaceSetupRoad(ActionBase):
    edge_id: EdgeId


@dataclass(frozen=True)
class RollDice(ActionBase):
    pass


@dataclass(frozen=True)
class DiscardResources(ActionBase):
    resources: tuple[tuple[ResourceType, int], ...]


@dataclass(frozen=True)
class MoveRobber(ActionBase):
    tile_id: TileId


@dataclass(frozen=True)
class StealResource(ActionBase):
    target_player_id: PlayerId


@dataclass(frozen=True)
class SkipSteal(ActionBase):
    pass


@dataclass(frozen=True)
class BuildRoad(ActionBase):
    edge_id: EdgeId


@dataclass(frozen=True)
class BuildSettlement(ActionBase):
    node_id: NodeId


@dataclass(frozen=True)
class BuildCity(ActionBase):
    node_id: NodeId


@dataclass(frozen=True)
class EndTurn(ActionBase):
    pass


Action = (
    PlaceSetupSettlement
    | PlaceSetupRoad
    | RollDice
    | DiscardResources
    | MoveRobber
    | StealResource
    | SkipSteal
    | BuildRoad
    | BuildSettlement
    | BuildCity
    | EndTurn
)
