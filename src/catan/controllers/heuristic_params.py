from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from catan.core.models.enums import ResourceType
from catan.runners.game_setup import ControllerType


@dataclass(frozen=True)
class HeuristicScoringParams:
    brick_value: float = 1.0
    lumber_value: float = 1.0
    wool_value: float = 0.9
    grain_value: float = 1.1
    ore_value: float = 1.2
    immediate_win_score: float = 0.0
    roll_score: float = 10_000.0
    settlement_base_score: float = 200.0
    city_base_score: float = 180.0
    road_base_score: float = 20.0
    dev_buy_base_score: float = 105.0
    bank_trade_base_score: float = 35.0
    end_turn_base_score: float = 0.0
    pip_weight: float = 1.0
    diversity_weight: float = 2.5
    missing_resource_weight: float = 2.0
    port_weight: float = 1.0
    expansion_weight: float = 1.5
    wood_brick_bonus: float = 0.0
    ore_wheat_bonus: float = 0.0
    pair_synergy_weight: float = 0.0
    road_to_target_weight: float = 0.12
    dead_road_penalty: float = 14.0
    dead_road_no_targets_penalty: float = 22.0
    save_for_settlement_penalty: float = 18.0
    save_for_settlement_delta_penalty: float = 8.0
    save_for_settlement_mid_penalty: float = 5.0
    port_reach_weight: float = 0.15
    longest_road_weight: float = 1.5
    road_distance_penalty: float = 3.0
    road_improvement_weight: float = 14.0
    robber_leader_weight: float = 0.8
    robber_high_prod_weight: float = 1.0
    robber_scarce_resource_weight: float = 0.0
    robber_self_harm_penalty: float = 18.0
    robber_steal_value_weight: float = 8.0
    dev_buy_weight: float = 0.0
    knight_play_weight: float = 0.0
    bank_trade_direct_build_bonus: float = 10.0
    trade_interest_threshold: float = 0.0
    trade_scarcity_penalty: float = 0.5

    @classmethod
    def from_mapping(cls, raw: Mapping[str, float | int | str | bool]) -> HeuristicScoringParams:
        values = asdict(cls())
        for key, default_value in values.items():
            if key not in raw:
                continue
            values[key] = _coerce_like(default_value, raw[key])
        return cls(**values)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def resource_values(self) -> dict[ResourceType, float]:
        return {
            ResourceType.BRICK: self.brick_value,
            ResourceType.LUMBER: self.lumber_value,
            ResourceType.WOOL: self.wool_value,
            ResourceType.GRAIN: self.grain_value,
            ResourceType.ORE: self.ore_value,
        }


def default_family_parameters(controller_type: ControllerType) -> dict[str, float | int | str | bool]:
    if controller_type == ControllerType.HEURISTIC_BOT:
        return {"seed": "", "delay_seconds": 1.2, **HeuristicScoringParams().as_dict()}
    if controller_type == ControllerType.HEURISTIC_V1_BASELINE:
        params = HeuristicScoringParams(
            grain_value=1.2,
            ore_value=1.3,
            immediate_win_score=50_000.0,
            roll_score=20_000.0,
            settlement_base_score=280.0,
            city_base_score=260.0,
            road_base_score=18.0,
            dev_buy_base_score=110.0,
            bank_trade_base_score=26.0,
            end_turn_base_score=5.0,
            diversity_weight=3.0,
            missing_resource_weight=2.5,
            expansion_weight=1.6,
            wood_brick_bonus=4.5,
            ore_wheat_bonus=4.5,
            pair_synergy_weight=4.0,
            road_to_target_weight=0.13,
            dead_road_penalty=16.0,
            dead_road_no_targets_penalty=24.0,
            save_for_settlement_penalty=20.0,
            save_for_settlement_mid_penalty=6.0,
            port_reach_weight=0.16,
            robber_leader_weight=1.2,
            robber_high_prod_weight=1.0,
            robber_steal_value_weight=8.0,
            dev_buy_weight=2.0,
            knight_play_weight=8.0,
            bank_trade_direct_build_bonus=34.0,
            trade_scarcity_penalty=0.6,
        )
        return {"seed": "", "delay_seconds": 1.2, **params.as_dict()}
    return {"seed": "", "delay_seconds": 1.2}


def merge_with_family_defaults(
    controller_type: ControllerType,
    overrides: Mapping[str, float | int | str | bool],
) -> dict[str, float | int | str | bool]:
    merged = default_family_parameters(controller_type)
    for key, value in overrides.items():
        if key in merged:
            merged[key] = _coerce_like(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_like(default_value: float | int | str | bool, incoming: float | int | str | bool) -> float | int | str | bool:
    if isinstance(default_value, bool):
        if isinstance(incoming, str):
            return incoming.strip().lower() in {"1", "true", "yes", "on"}
        return bool(incoming)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        if isinstance(incoming, str):
            text = incoming.strip()
            return default_value if text == "" else int(text)
        return int(incoming)
    if isinstance(default_value, float):
        if isinstance(incoming, str):
            text = incoming.strip()
            return default_value if text == "" else float(text)
        return float(incoming)
    return str(incoming)
