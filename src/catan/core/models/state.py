from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .board import Board, EdgeId, NodeId, PlayerId, TileId
from .enums import DevelopmentCardType, GamePhase, PlayerTradePhase, ResourceType, TurnStep


@dataclass
class PlayerState:
    player_id: PlayerId
    resources: dict[ResourceType, int]
    roads_left: int = 15
    settlements_left: int = 5
    cities_left: int = 4
    victory_points: int = 0
    setup_settlements_placed: int = 0
    dev_cards: dict[DevelopmentCardType, int] = field(default_factory=lambda: {card_type: 0 for card_type in DevelopmentCardType})
    new_dev_cards: dict[DevelopmentCardType, int] = field(default_factory=lambda: {card_type: 0 for card_type in DevelopmentCardType})
    knights_played: int = 0
    longest_road_length: int = 0


@dataclass
class SetupState:
    pending_settlement_player: Optional[PlayerId] = None
    pending_road_player: Optional[PlayerId] = None
    pending_road_origin_node: Optional[NodeId] = None
    order: list[PlayerId] = field(default_factory=list)
    index: int = 0


@dataclass
class TurnState:
    current_player: PlayerId
    step: TurnStep = TurnStep.ROLL
    last_roll: Optional[tuple[int, int]] = None
    priority_player: Optional[PlayerId] = None
    dev_card_played_this_turn: bool = False


@dataclass
class PlacedPieces:
    roads: dict[EdgeId, PlayerId] = field(default_factory=dict)
    settlements: dict[NodeId, PlayerId] = field(default_factory=dict)
    cities: dict[NodeId, PlayerId] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerTradeState:
    proposer_player_id: PlayerId
    offered_resources: tuple[tuple[ResourceType, int], ...]
    requested_resources: tuple[tuple[ResourceType, int], ...]
    responder_order: tuple[PlayerId, ...]
    current_responder_index: int
    eligible_responders: tuple[PlayerId, ...]
    interested_responders: tuple[PlayerId, ...]
    phase: PlayerTradePhase


@dataclass(frozen=True)
class DevCardFlowState:
    card_type: DevelopmentCardType
    roads_remaining: int = 0
    roads_placed: int = 0


@dataclass
class GameState:
    board: Board
    players: dict[PlayerId, PlayerState]
    phase: GamePhase
    setup: SetupState
    turn: Optional[TurnState]
    placed: PlacedPieces
    winner: Optional[PlayerId] = None
    rng_state: int = 0
    robber_tile_id: Optional[TileId] = None
    discard_requirements: dict[PlayerId, int] = field(default_factory=dict)
    player_trade: PlayerTradeState | None = None
    dev_deck: tuple[DevelopmentCardType, ...] = ()
    largest_army_holder: PlayerId | None = None
    longest_road_holder: PlayerId | None = None
    robber_source: str | None = None
    dev_card_flow: DevCardFlowState | None = None


@dataclass(frozen=True)
class InitialGameConfig:
    player_ids: tuple[PlayerId, ...]
    board: Board
    seed: int
