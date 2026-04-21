from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .board import Board, EdgeId, NodeId, PlayerId
from .enums import GamePhase, ResourceType, TurnStep


@dataclass
class PlayerState:
    player_id: PlayerId
    resources: dict[ResourceType, int]
    roads_left: int = 15
    settlements_left: int = 5
    cities_left: int = 4
    victory_points: int = 0
    setup_settlements_placed: int = 0


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


@dataclass
class PlacedPieces:
    roads: dict[EdgeId, PlayerId] = field(default_factory=dict)
    settlements: dict[NodeId, PlayerId] = field(default_factory=dict)
    cities: dict[NodeId, PlayerId] = field(default_factory=dict)


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


@dataclass(frozen=True)
class InitialGameConfig:
    player_ids: tuple[PlayerId, ...]
    board: Board
    seed: int
