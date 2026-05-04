from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from catan.core.models.enums import ResourceType
from catan.runners.game_setup import ControllerType

_GLOBAL_GAME_PARAMETER_KEYS = frozenset({"seed", "delay_seconds"})


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
    bank_trade_progress_threshold: float = 1.0
    bank_trade_no_progress_penalty: float = -60.0
    bank_trade_chain_penalty: float = -18.0
    bank_trade_enable_road_requires_target: bool = True
    bank_trade_enable_dev_bonus: float = 14.0
    bank_trade_enable_city_bonus: float = 32.0
    bank_trade_enable_settlement_bonus: float = 30.0
    trade_interest_threshold: float = 0.0
    trade_scarcity_penalty: float = 0.5
    max_bot_trade_proposals_per_turn: int = 1
    player_trade_enable_settlement_bonus: float = 24.0
    player_trade_enable_city_bonus: float = 30.0
    player_trade_enable_dev_bonus: float = 18.0
    player_trade_scarce_resource_bonus: float = 10.0
    player_trade_critical_giveaway_penalty: float = 16.0
    player_trade_leader_penalty: float = 18.0
    player_trade_accept_threshold: float = 8.0
    player_trade_proposal_threshold: float = 10.0
    setup_expansion_profile_bonus: float = 0.0
    setup_city_dev_profile_bonus: float = 0.0
    setup_profile_missing_penalty: float = 0.0
    road_when_settlement_available_penalty: float = 0.0
    road_settlement_resource_lock_penalty: float = 0.0
    road_no_settlement_progress_bonus: float = 0.0
    dev_when_city_ready_penalty: float = 0.0
    dev_when_city_near_penalty: float = 0.0
    candidate_count: int = 8
    action_score_weight: float = 0.25
    state_score_weight: float = 0.75
    vp_weight: float = 100.0
    production_weight: float = 8.0
    resource_balance_weight: float = 10.0
    expansion_potential_weight: float = 6.0
    city_potential_weight: float = 5.0
    dev_potential_weight: float = 4.0
    road_potential_weight: float = 2.5
    port_value_weight: float = 3.0
    hand_resource_weight: float = 1.0
    robber_block_penalty: float = 12.0
    large_hand_penalty: float = 2.0
    road_overbuild_penalty: float = 4.0
    no_expansion_penalty: float = 20.0

    v3_candidate_count: int = 6
    v3_max_lookahead_candidates: int = 4
    v3_enable_rollout_lite: bool = False
    v3_rollout_count: int = 0
    v3_rollout_depth: int = 0
    v3_action_score_weight: float = 0.15
    v3_immediate_state_weight: float = 0.55
    v3_lookahead_weight: float = 0.30
    v3_next_city_weight: float = 30.0
    v3_next_settlement_weight: float = 28.0
    v3_next_dev_weight: float = 10.0
    v3_next_road_target_weight: float = 12.0
    v3_expected_income_weight: float = 6.0
    v3_hand_flexibility_weight: float = 3.0
    v3_discard_risk_penalty: float = 8.0
    v3_road_overbuild_penalty: float = 8.0
    v3_no_expansion_penalty: float = 25.0
    v3_trade_loop_penalty: float = 30.0
    v3_low_progress_penalty: float = 15.0
    v3_robber_leader_block_weight: float = 4.0
    v3_robber_production_block_weight: float = 3.0
    v3_robber_self_block_penalty: float = 25.0

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
        return {**HeuristicScoringParams().as_dict()}
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
        return {**params.as_dict()}
    if controller_type == ControllerType.HEURISTIC_V1_FIXED:
        return default_family_parameters(ControllerType.HEURISTIC_V1_BASELINE)
    if controller_type == ControllerType.HEURISTIC_V1_1:
        params = HeuristicScoringParams(
            grain_value=1.2,
            ore_value=1.3,
            immediate_win_score=50_000.0,
            roll_score=20_000.0,
            settlement_base_score=292.0,
            city_base_score=278.0,
            road_base_score=14.0,
            dev_buy_base_score=98.0,
            bank_trade_base_score=26.0,
            end_turn_base_score=5.0,
            pip_weight=0.92,
            diversity_weight=3.6,
            missing_resource_weight=3.0,
            expansion_weight=1.8,
            wood_brick_bonus=6.0,
            ore_wheat_bonus=6.0,
            pair_synergy_weight=5.0,
            road_to_target_weight=0.11,
            dead_road_penalty=18.0,
            dead_road_no_targets_penalty=28.0,
            save_for_settlement_penalty=24.0,
            save_for_settlement_delta_penalty=10.0,
            save_for_settlement_mid_penalty=7.5,
            port_reach_weight=0.2,
            longest_road_weight=1.0,
            dev_buy_weight=1.5,
            knight_play_weight=8.0,
            bank_trade_direct_build_bonus=34.0,
            trade_scarcity_penalty=0.6,
            setup_expansion_profile_bonus=13.0,
            setup_city_dev_profile_bonus=10.0,
            setup_profile_missing_penalty=3.5,
            road_when_settlement_available_penalty=24.0,
            road_settlement_resource_lock_penalty=14.0,
            road_no_settlement_progress_bonus=12.0,
            dev_when_city_ready_penalty=26.0,
            dev_when_city_near_penalty=12.0,
        )
        return {**params.as_dict()}
    if controller_type == ControllerType.HEURISTIC_V2_POSITIONAL:
        return {**HeuristicScoringParams().as_dict()}
    if controller_type == ControllerType.HEURISTIC_V3_LOOKAHEAD:
        return {**HeuristicScoringParams().as_dict()}
    return {}


def merge_with_family_defaults(
    controller_type: ControllerType,
    overrides: Mapping[str, float | int | str | bool],
) -> dict[str, float | int | str | bool]:
    merged = default_family_parameters(controller_type)
    for key, value in overrides.items():
        if key in _GLOBAL_GAME_PARAMETER_KEYS:
            continue
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
