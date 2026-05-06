from __future__ import annotations

from typing import Any, Sequence

from catan.controllers.heuristic_v1_baseline_bot_controller import _CITY_COST, _DEV_COST, _SETTLEMENT_COST
from catan.controllers.heuristic_v2_positional_bot_controller import HeuristicV2PositionalBotController
from catan.core.engine import apply_action
from catan.core.models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    DiscardResources,
    EndTurn,
    ProposePlayerTrade,
)
from catan.core.models.enums import ResourceType
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation


class HeuristicV3LookaheadBotController(HeuristicV2PositionalBotController):
    """Limited-depth lookahead bot built on top of v2 positional heuristics."""

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        state = observation.state if isinstance(observation, DebugObservation) else None
        if len(legal_actions) <= 1:
            only_action = legal_actions[0]
            if state is not None and isinstance(only_action, DiscardResources):
                only_action = self._choose_discard_action(state, only_action.player_id)
            self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": only_action, "top_candidates": [{"action": only_action, "action_score": 0.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 0.0, "summary": "forced action"}], "legal_action_count": len(legal_actions)}
            return only_action
        if state is None:
            chosen = super().choose_action(observation, legal_actions)
            if isinstance(self._last_decision, dict):
                self._last_decision["kind"] = "heuristic_v3_lookahead"
            return chosen

        candidates = self._prune_candidates(state, list(legal_actions)) or list(legal_actions)
        discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
        if discard_placeholder is not None:
            chosen = self._choose_discard_action(state, discard_placeholder.player_id)
            self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": chosen, "top_candidates": [{"action": chosen, "action_score": 25.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 25.0, "summary": "discard policy"}], "legal_action_count": len(legal_actions)}
            return chosen
        scored = [(a, self._score_action(a, state)) for a in candidates]
        scored.sort(key=lambda item: item[1], reverse=True)
        shortlisted = scored[: max(1, int(self._params.v3_candidate_count))]
        normalized = self._normalize_action_scores(shortlisted)

        current_player = state.turn.current_player if state.turn else shortlisted[0][0].player_id
        current_eval = self._evaluator.evaluate(state, current_player, self._params)

        details: list[dict[str, Any]] = []
        best_score: float | None = None
        best_actions: list[Action] = []
        max_lookahead = max(1, int(self._params.v3_max_lookahead_candidates))
        for idx, (action, action_score) in enumerate(shortlisted):
            state_after, summary, _ = self._evaluate_after_action(state, action, current_eval.total_score)
            state_delta = state_after - current_eval.total_score
            lookahead, reason_flags = self._future_option_score(state, action)
            if idx >= max_lookahead:
                lookahead = state_delta
            combined = (
                self._params.v3_action_score_weight * normalized[action]
                + self._params.v3_immediate_state_weight * state_delta
                + self._params.v3_lookahead_weight * lookahead
                + (0.05 * state_after)
            )
            details.append({"action": action, "action_score": action_score, "state_before": current_eval.total_score, "state_after": state_after, "state_delta": state_delta, "position_score": state_delta, "lookahead_score": lookahead, "combined_score": combined, "summary": summary, "reason_flags": reason_flags})
            if best_score is None or combined > best_score:
                best_score, best_actions = combined, [action]
            elif abs(combined - best_score) <= 1e-9:
                best_actions.append(action)

        chosen = best_actions[self._rng.randrange(len(best_actions))]
        details.sort(key=lambda item: item["combined_score"], reverse=True)
        self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": chosen, "top_candidates": details[:3], "legal_action_count": len(legal_actions)}
        return chosen

    def _prune_candidates(self, state: GameState, actions: list[Action]) -> list[Action]:
        pruned: list[Action] = []
        trade_candidates: list[tuple[ProposePlayerTrade, float]] = []
        meaningful_progress_found = False
        for action in actions:
            if isinstance(action, ProposePlayerTrade):
                score = self._score_player_trade_proposal(action, state)
                if score < self._params.player_trade_proposal_threshold:
                    continue
                trade_candidates.append((action, score))
                meaningful_progress_found = True
                continue
            if isinstance(action, BankTrade) and self._score_action(action, state) < self._params.trade_interest_threshold:
                continue
            if isinstance(action, BuildRoad):
                road_gain, road_flags = self._road_target_gain(state, action)
                if road_gain <= 0:
                    continue
                if "target_far_or_weak" in road_flags:
                    continue
                meaningful_progress_found = True
            if isinstance(action, (BuildSettlement, BuildCity)):

                meaningful_progress_found = True
            if isinstance(action, BuyDevelopmentCard):
                player = state.players[action.player_id]
                city_missing = self._missing_resources(dict(player.resources), _CITY_COST)
                if city_missing <= 1:
                    continue
            pruned.append(action)

        trade_candidates.sort(key=lambda item: item[1], reverse=True)
        for action, _ in trade_candidates[:2]:
            pruned.append(action)
        if not meaningful_progress_found:
            return pruned
        return [a for a in pruned if not isinstance(a, EndTurn)] or pruned

    def _road_target_gain(self, state: GameState, action: BuildRoad) -> tuple[float, list[str]]:
        before = self._roads_to_targets(state, action.player_id)
        after = self._roads_to_targets(state, action.player_id, planned_edges={action.edge_id})
        best_gain = 0.0
        flags: list[str] = []
        for node_id, dist_after in after.items():
            dist_before = before.get(node_id, 99)
            if dist_after >= dist_before:
                continue
            quality = self._score_settlement_node(node_id, state, in_setup=False)
            gain = (dist_before - dist_after) * 6.0 + quality * 0.15 - dist_after * 2.0
            if gain > best_gain:
                best_gain = gain
                flags = [f"valid_target_distance:{dist_after}", f"target_quality:{quality:.1f}"]
                if dist_after > 2 and quality < 45:
                    flags.append("target_far_or_weak")
        return best_gain, flags

    def _future_option_score(self, state: GameState, action: Action) -> tuple[float, list[str]]:
        try:
            simulated = apply_action(self._clone_state_for_simulation(state), action)
        except Exception:
            return -1_000_000.0, ["simulation_failed"]
        player = simulated.players[action.player_id]
        evaluation = self._evaluator.evaluate(simulated, action.player_id, self._params)
        base_production = evaluation.components.get("production", 0.0) / max(0.001, self._params.production_weight)
        score = self._params.v3_expected_income_weight * base_production
        flags: list[str] = []

        city_missing = self._missing_resources(dict(player.resources), _CITY_COST)
        settle_missing = self._missing_resources(dict(player.resources), _SETTLEMENT_COST)
        dev_missing = self._missing_resources(dict(player.resources), _DEV_COST)
        score += self._params.v3_next_city_weight * (1.0 / (1 + city_missing))

        targets = self._roads_to_targets(simulated, action.player_id)
        if any(d == 0 for d in targets.values()) and settle_missing == 0:
            score += self._params.v3_next_settlement_weight
            flags.append("legal_settlement_now")
        elif targets:
            nearest = min(targets.values())
            best_target = min(targets, key=targets.get)
            quality = self._score_settlement_node(best_target, simulated, in_setup=False)
            if nearest <= 1:
                score += self._params.v3_next_settlement_weight * 0.65
            elif nearest <= 2:
                score += self._params.v3_next_settlement_weight * 0.30
            else:
                score += self._params.v3_next_settlement_weight * 0.05
            score += self._params.v3_next_road_target_weight * max(0.0, (quality / 60.0) - (nearest * 0.15))
            flags.extend([f"valid_target_distance:{nearest}", f"target_quality:{quality:.1f}"])
        else:
            score -= self._params.v3_no_expansion_penalty
            flags.append("no_expansion_penalty")

        if settle_missing > 0:
            score += self._params.v3_next_settlement_weight * (0.1 / (1 + settle_missing))

        dev_term = self._params.v3_next_dev_weight * (1.0 / (1 + dev_missing))
        if city_missing <= 1:
            dev_term -= self._params.v3_low_progress_penalty
            flags.append("dev_delays_city_penalty")
        if settle_missing <= 1 and targets:
            dev_term -= self._params.v3_low_progress_penalty * 0.7
            flags.append("dev_delays_settlement_penalty")
        score += dev_term

        produced = self._player_production_resources(simulated, action.player_id)
        flex = sum(1 for r in ResourceType if produced.get(r, 0) > 0)
        score += self._params.v3_hand_flexibility_weight * flex

        if sum(player.resources.values()) > 7:
            score -= self._params.v3_discard_risk_penalty
        own_roads_built = 15 - player.roads_left
        own_settlements_built = 5 - player.settlements_left
        road_overbuild = max(0, own_roads_built - (own_settlements_built * 2 + 1))
        if road_overbuild > 0:
            score -= road_overbuild * self._params.v3_road_overbuild_penalty
            flags.append("road_overbuild_penalty")

        if isinstance(action, (BankTrade, ProposePlayerTrade)) and city_missing > 2 and settle_missing > 2:
            score -= self._params.v3_trade_loop_penalty
            flags.append("trade_loop_penalty")
        if city_missing > 2 and settle_missing > 2 and dev_missing > 2:
            score -= self._params.v3_low_progress_penalty
            flags.append("low_progress_penalty")
        return score, flags
