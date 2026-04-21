from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from .models.board import PlayerId
from .models.state import GameState


@dataclass(frozen=True)
class PublicPlayerView:
    player_id: PlayerId
    victory_points: int
    resource_count: int


@dataclass(frozen=True)
class PlayerObservation:
    requesting_player_id: PlayerId
    current_player_id: Optional[PlayerId]
    phase: str
    own_resources: Mapping[str, int]
    players_public: tuple[PublicPlayerView, ...]


@dataclass(frozen=True)
class DebugObservation:
    state: GameState


Observation = PlayerObservation | DebugObservation
