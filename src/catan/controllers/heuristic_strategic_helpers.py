from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from catan.controllers.heuristic_v1_baseline_bot_controller import _CITY_COST, _DEV_COST, _SETTLEMENT_COST
from catan.core.models.action import Action, BankTrade, BuildCity, BuildRoad, BuildSettlement, BuyDevelopmentCard, EndTurn, ProposePlayerTrade
from catan.core.models.enums import ResourceType
from catan.core.models.state import GameState


class GamePhase(str, Enum):
    EARLY = "EARLY"
    MID = "MID"
    LATE = "LATE"


@dataclass(frozen=True)
class BottleneckProfile:
    ore_wheat_bottleneck: bool
    wood_brick_bottleneck: bool
    sheep_wheat_bottleneck: bool
    no_good_expansion_targets: bool
    strong_port_engine: bool
    road_overbuilt: bool


def classify_game_phase(state: GameState, player_id: int) -> GamePhase:
    p = state.players[player_id]
    vp = p.victory_points
    if vp >= 7:
        return GamePhase.LATE
    if vp >= 4:
        return GamePhase.MID
    return GamePhase.EARLY


def detect_bottlenecks(controller, state: GameState, player_id: int) -> BottleneckProfile:
    produced = controller._player_production_resources(state, player_id)
    ore = produced.get(ResourceType.ORE, 0.0)
    grain = produced.get(ResourceType.GRAIN, 0.0)
    wool = produced.get(ResourceType.WOOL, 0.0)
    lumber = produced.get(ResourceType.LUMBER, 0.0)
    brick = produced.get(ResourceType.BRICK, 0.0)
    targets = controller._roads_to_targets(state, player_id)
    p = state.players[player_id]
    roads_built = 15 - p.roads_left
    settlements_built = 5 - p.settlements_left
    return BottleneckProfile(
        ore_wheat_bottleneck=(ore + grain) < 5.5,
        wood_brick_bottleneck=(lumber + brick) < 5.0,
        sheep_wheat_bottleneck=(wool + grain) < 5.0,
        no_good_expansion_targets=not bool(targets),
        strong_port_engine=max(ore, grain, wool, lumber, brick) >= 4.0,
        road_overbuilt=roads_built > settlements_built * 2 + 1,
    )


def estimate_distances(controller, state: GameState, player_id: int) -> dict[str, int]:
    p = state.players[player_id]
    res = dict(p.resources)
    city = controller._missing_resources(res, _CITY_COST)
    dev = controller._missing_resources(res, _DEV_COST)
    settle_missing = controller._missing_resources(res, _SETTLEMENT_COST)
    targets = controller._roads_to_targets(state, player_id)
    if not targets:
        settlement = 9
        road_settle = 9
    else:
        nearest = min(targets.values())
        settlement = settle_missing + nearest
        road_settle = controller._missing_resources(res, {ResourceType.BRICK: 1, ResourceType.LUMBER: 1}) + nearest
    return {"city": city, "settlement": settlement, "dev": dev, "road_settlement": road_settle}


def forced_candidates(controller, state: GameState, actions: Sequence[Action], scored: list[tuple[Action, float]], top_n: int) -> list[Action]:
    scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
    result = [a for a, _ in scored_sorted[:top_n]]

    def add_best(kind):
        candidates = [(a, s) for a, s in scored_sorted if isinstance(a, kind)]
        if candidates:
            result.append(candidates[0][0])

    add_best(BuildCity)
    add_best(BuildSettlement)
    add_best(BuildRoad)
    add_best(BuyDevelopmentCard)
    add_best(BankTrade)
    add_best(ProposePlayerTrade)
    add_best(EndTurn)
    dedup = []
    seen = set()
    for a in result:
        if id(a) in seen:
            continue
        seen.add(id(a))
        dedup.append(a)
    return dedup
