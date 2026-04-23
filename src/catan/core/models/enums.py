from __future__ import annotations

from enum import Enum, auto


class ResourceType(Enum):
    BRICK = auto()
    LUMBER = auto()
    WOOL = auto()
    GRAIN = auto()
    ORE = auto()


class TerrainType(Enum):
    HILLS = auto()
    FOREST = auto()
    PASTURE = auto()
    FIELDS = auto()
    MOUNTAINS = auto()
    DESERT = auto()


class GamePhase(Enum):
    SETUP_FORWARD = auto()
    SETUP_REVERSE = auto()
    MAIN_TURN = auto()
    GAME_OVER = auto()


class TurnStep(Enum):
    ROLL = auto()
    DISCARD = auto()
    ROBBER_MOVE = auto()
    ROBBER_STEAL = auto()
    ACTIONS = auto()
    PLAYER_TRADE = auto()


class PlayerTradePhase(Enum):
    RESPONSES = auto()
    PARTNER_SELECTION = auto()


class DevelopmentCardType(Enum):
    KNIGHT = auto()
    VICTORY_POINT = auto()
    ROAD_BUILDING = auto()
    YEAR_OF_PLENTY = auto()
    MONOPOLY = auto()
