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
class BankTrade(ActionBase):
    offer_resource: ResourceType
    request_resource: ResourceType
    trade_rate: int = 4
    via_port_resource: ResourceType | None = None


@dataclass(frozen=True)
class ProposePlayerTrade(ActionBase):
    offered_resources: tuple[tuple[ResourceType, int], ...]
    requested_resources: tuple[tuple[ResourceType, int], ...]


@dataclass(frozen=True)
class RespondToTradeInterested(ActionBase):
    pass


@dataclass(frozen=True)
class RespondToTradePass(ActionBase):
    pass


@dataclass(frozen=True)
class ChooseTradePartner(ActionBase):
    partner_player_id: PlayerId


@dataclass(frozen=True)
class RejectTradeResponses(ActionBase):
    pass


@dataclass(frozen=True)
class EndTurn(ActionBase):
    pass


@dataclass(frozen=True)
class BuyDevelopmentCard(ActionBase):
    pass


@dataclass(frozen=True)
class PlayKnightCard(ActionBase):
    pass


@dataclass(frozen=True)
class PlayRoadBuildingCard(ActionBase):
    pass


@dataclass(frozen=True)
class FinishRoadBuildingCard(ActionBase):
    pass


@dataclass(frozen=True)
class PlayYearOfPlentyCard(ActionBase):
    pass


@dataclass(frozen=True)
class ChooseYearOfPlentyResources(ActionBase):
    first_resource: ResourceType
    second_resource: ResourceType


@dataclass(frozen=True)
class PlayMonopolyCard(ActionBase):
    pass


@dataclass(frozen=True)
class ChooseMonopolyResource(ActionBase):
    resource: ResourceType


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
    | BankTrade
    | ProposePlayerTrade
    | RespondToTradeInterested
    | RespondToTradePass
    | ChooseTradePartner
    | RejectTradeResponses
    | BuyDevelopmentCard
    | PlayKnightCard
    | PlayRoadBuildingCard
    | FinishRoadBuildingCard
    | PlayYearOfPlentyCard
    | ChooseYearOfPlentyResources
    | PlayMonopolyCard
    | ChooseMonopolyResource
    | EndTurn
)
