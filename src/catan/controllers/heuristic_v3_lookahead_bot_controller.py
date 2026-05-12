from __future__ import annotations

from time import sleep
from typing import Any, Sequence

from catan.controllers.heuristic_v1_baseline_bot_controller import _CITY_COST, _DEV_COST, _SETTLEMENT_COST
from catan.controllers.heuristic_strategic_helpers import classify_game_phase, detect_bottlenecks, estimate_distances, forced_candidates
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
from catan.core.models.enums import ResourceType, TurnStep
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation


class HeuristicV3LookaheadBotController(HeuristicV2PositionalBotController):
    """Limited-depth lookahead bot built on top of v2 positional heuristics."""

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if self._enable_delay and self._delay_seconds > 0:
            sleep(self._delay_seconds)
        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None and len(legal_actions) <= 1:
            only_action = legal_actions[0]
            self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": only_action, "top_candidates": [{"action": only_action, "action_score": 0.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 0.0, "summary": "forced action"}], "legal_action_count": len(legal_actions)}
            return only_action
        if state is None:
            chosen = super().choose_action(observation, legal_actions)
            if isinstance(self._last_decision, dict):
                self._last_decision["kind"] = "heuristic_v3_lookahead"
            return chosen

        candidates_pool = list(legal_actions)
        if state.turn is not None and state.turn.step == TurnStep.ACTIONS and state.player_trade is None:
            candidates_pool.extend(self._candidate_player_trades(state, legal_actions))
        candidates = self._prune_candidates(state, candidates_pool) or candidates_pool
        if len(candidates) <= 1:
            only_action = candidates[0]
            if isinstance(only_action, DiscardResources):
                only_action = self._choose_discard_action(state, only_action.player_id)
            top = {"action": only_action, "action_score": 0.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 0.0, "summary": "forced action"}
            if isinstance(only_action, ProposePlayerTrade):
                top["trade_debug"] = self._score_notes.get(id(only_action), "")
            self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": only_action, "top_candidates": [top], "legal_action_count": len(candidates_pool)}
            return only_action
        discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
        if discard_placeholder is not None:
            chosen = self._choose_discard_action(state, discard_placeholder.player_id)
            self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": chosen, "top_candidates": [{"action": chosen, "action_score": 25.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 25.0, "summary": "discard policy"}], "legal_action_count": len(legal_actions)}
            return chosen
        scored = [(a, self._score_action(a, state)) for a in candidates]
        shortlisted_actions = forced_candidates(self, state, candidates, scored, max(1, int(self._params.v3_candidate_count)))
        scored.sort(key=lambda item: item[1], reverse=True)
        shortlisted = [(a,s) for a,s in scored if a in shortlisted_actions]
        normalized = self._normalize_action_scores(shortlisted)

        current_player = state.turn.current_player if state.turn else shortlisted[0][0].player_id
        current_eval = self._evaluator.evaluate(state, current_player, self._params)
        phase = classify_game_phase(state, current_player)
        profile = detect_bottlenecks(self, state, current_player)
        distances = estimate_distances(self, state, current_player)

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
            strategic_bias = (12.0 / (1 + distances["city"])) + (10.0 / (1 + distances["settlement"]))
            if phase.value == "LATE":
                strategic_bias += 8.0 / (1 + distances["city"])
            if profile.road_overbuilt and isinstance(action, BuildRoad):
                lookahead -= 10.0
            combined = (
                self._params.v3_action_score_weight * normalized[action]
                + self._params.v3_immediate_state_weight * state_delta
                + self._params.v3_lookahead_weight * lookahead
                + (0.05 * state_after)
                + strategic_bias
            )
            details.append({"action": action, "action_score": action_score, "state_before": current_eval.total_score, "state_after": state_after, "state_delta": state_delta, "position_score": state_delta, "lookahead_score": lookahead, "strategic_goal_score": strategic_bias, "game_phase": phase.value, "bottlenecks": profile.__dict__, "turns_to_build": distances, "combined_score": combined, "summary": summary, "reason_flags": reason_flags})
            if isinstance(action, ProposePlayerTrade):
                details[-1]["trade_debug"] = self._score_notes.get(id(action), "")
            if best_score is None or combined > best_score:
                best_score, best_actions = combined, [action]
            elif abs(combined - best_score) <= 1e-9:
                best_actions.append(action)

        chosen = best_actions[self._rng.randrange(len(best_actions))]
        details.sort(key=lambda item: item["combined_score"], reverse=True)
        self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": chosen, "top_candidates": details[:3], "legal_action_count": len(candidates_pool)}
        return chosen

    def _prune_candidates(self, state: GameState, actions: list[Action]) -> list[Action]:
        pruned: list[Action] = []
        trade_candidates: list[tuple[ProposePlayerTrade, float]] = []
        road_candidates: list[tuple[BuildRoad, float, list[str]]] = []
        meaningful_progress_found = False
        for action in actions:
            if isinstance(action, ProposePlayerTrade):
                v2_score = self._score_player_trade_proposal(action, state)
                note = self._score_notes.get(id(action), "")
                if v2_score <= -999999.0:
                    continue
                lookahead_score, lookahead_flags = self._future_option_score(state, action)
                if not self._trade_has_next_action_potential(note, lookahead_score):
                    self._score_notes[id(action)] = (
                        f"{note}; v2_trade_score={v2_score:+.2f}; v3_lookahead_trade_score={lookahead_score:+.2f}; "
                        "rejected_reason=v3_no_next_action_potential"
                    )
                    continue
                self._score_notes[id(action)] = f"{note}; v2_trade_score={v2_score:+.2f}; v3_lookahead_trade_score={lookahead_score:+.2f}; v3_flags={lookahead_flags}"
                trade_candidates.append((action, v2_score + (0.3 * lookahead_score)))
                meaningful_progress_found = True
                continue
            if isinstance(action, BankTrade) and self._score_action(action, state) < self._params.trade_interest_threshold:
                continue
            if isinstance(action, BuildRoad):
                road_gain, road_flags = self._road_target_gain(state, action)
                if road_gain <= 0:
                    continue
                road_candidates.append((action, road_gain, road_flags))
                if "target_far_or_weak" not in road_flags:
                    pruned.append(action)
                    meaningful_progress_found = True
                continue
            if isinstance(action, (BuildSettlement, BuildCity)):

                meaningful_progress_found = True
            if isinstance(action, BuyDevelopmentCard):
                player = state.players[action.player_id]
                city_missing = self._missing_resources(dict(player.resources), _CITY_COST)
                if city_missing <= 1:
                    continue
            pruned.append(action)

        if road_candidates and not any(isinstance(a, BuildRoad) for a in pruned):
            best_road = max(road_candidates, key=lambda item: item[1])[0]
            pruned.append(best_road)

        trade_candidates.sort(key=lambda item: item[1], reverse=True)
        for action, _ in trade_candidates[:2]:
            pruned.append(action)
        if not meaningful_progress_found:
            return pruned
        return [a for a in pruned if not isinstance(a, EndTurn)] or pruned

    def _score_player_trade_proposal(self, action: ProposePlayerTrade, state: GameState | None) -> float:
        v2_score = super()._score_player_trade_proposal(action, state)
        if state is None:
            return v2_score
        note = self._score_notes.get(id(action), "")
        if v2_score <= -999999.0:
            self._score_notes[id(action)] = f"{note}; v2_trade_score={v2_score:+.2f}; v3_lookahead_trade_score=-1000000.00"
            return -1_000_000.0
        lookahead_score, flags = self._future_option_score(state, action)
        if not self._trade_has_next_action_potential(note, lookahead_score):
            self._score_notes[id(action)] = (
                f"{note}; v2_trade_score={v2_score:+.2f}; v3_lookahead_trade_score={lookahead_score:+.2f}; "
                "rejected_reason=v3_no_next_action_potential"
            )
            return -1_000_000.0
        priority_bonus = 0.0
        if "enables_city=True" in note:
            priority_bonus += 35.0
        if "enables_settlement=True" in note:
            priority_bonus += 28.0
        if "enables_dev=True" in note:
            priority_bonus += 10.0
        total = v2_score + (0.3 * lookahead_score) + priority_bonus
        self._score_notes[id(action)] = f"{note}; v2_trade_score={v2_score:+.2f}; v3_lookahead_trade_score={lookahead_score:+.2f}; v3_flags={flags}"
        return total

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
    def _trade_has_next_action_potential(self, note: str, lookahead_score: float) -> bool:
        enables_city = "enables_city=True" in note
        enables_settlement = "enables_settlement=True" in note
        enables_dev = "enables_dev=True" in note
        if enables_city or enables_settlement or enables_dev:
            return True
        state_delta = 0.0
        marker = "state_delta="
        if marker in note:
            try:
                raw = note.split(marker, 1)[1].split(";", 1)[0]
                state_delta = float(raw)
            except Exception:
                state_delta = 0.0
        return state_delta > 0.05 and lookahead_score > 0.0
