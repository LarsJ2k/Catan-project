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
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation


class HeuristicV3LookaheadBotController(HeuristicV2PositionalBotController):
    """Limited-depth lookahead bot built on top of v2 positional heuristics."""

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if len(legal_actions) <= 1:
            return legal_actions[0]
        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None:
            chosen = super().choose_action(observation, legal_actions)
            if isinstance(self._last_decision, dict):
                self._last_decision["kind"] = "heuristic_v3_lookahead"
            return chosen

        candidates = self._prune_candidates(state, list(legal_actions)) or list(legal_actions)
        discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
        if discard_placeholder is not None:
            chosen = self._choose_discard_action(state, discard_placeholder.player_id)
            self._last_decision = {
                "kind": "heuristic_v3_lookahead",
                "chosen_action": chosen,
                "top_candidates": [{"action": chosen, "action_score": 25.0, "position_score": 0.0, "lookahead_score": 0.0, "combined_score": 25.0, "summary": "discard policy"}],
                "legal_action_count": len(legal_actions),
            }
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
            immediate, summary, _ = self._evaluate_after_action(state, action, current_eval.total_score)
            lookahead = self._future_option_score(state, action) if idx < max_lookahead else immediate
            combined = (
                self._params.v3_action_score_weight * normalized[action]
                + self._params.v3_immediate_state_weight * immediate
                + self._params.v3_lookahead_weight * lookahead
            )
            details.append({"action": action, "action_score": action_score, "position_score": immediate, "lookahead_score": lookahead, "combined_score": combined, "summary": summary})
            if best_score is None or combined > best_score:
                best_score, best_actions = combined, [action]
            elif abs(combined - best_score) <= 1e-9:
                best_actions.append(action)

        chosen = best_actions[self._rng.randrange(len(best_actions))]
        details.sort(key=lambda item: item["combined_score"], reverse=True)
        self._last_decision = {"kind": "heuristic_v3_lookahead", "chosen_action": chosen, "top_candidates": details[:3], "legal_action_count": len(legal_actions)}
        return chosen

    def _prune_candidates(self, state: GameState, actions: list[Action]) -> list[Action]:
        has_progress = any(isinstance(a, (BuildCity, BuildSettlement, BuyDevelopmentCard, BuildRoad)) for a in actions)
        pruned: list[Action] = []
        for action in actions:
            if isinstance(action, ProposePlayerTrade):
                continue
            if isinstance(action, BankTrade) and self._score_action(action, state) < self._params.trade_interest_threshold:
                continue
            if isinstance(action, BuildRoad):
                before = self._roads_to_targets(state, action.player_id)
                after = self._roads_to_targets(state, action.player_id, planned_edges={action.edge_id})
                if not any(after.get(node, 99) < before.get(node, 99) for node in after):
                    continue
            if isinstance(action, EndTurn) and has_progress and self._city_missing_count(state) > 1:
                continue
            pruned.append(action)
        return pruned

    def _future_option_score(self, state: GameState, action: Action) -> float:
        try:
            simulated = apply_action(self._clone_state_for_simulation(state), action)
        except Exception:
            return -1_000_000.0
        player = simulated.players[action.player_id]
        evaluation = self._evaluator.evaluate(simulated, action.player_id, self._params)
        base_production = evaluation.components.get("production", 0.0) / max(0.001, self._params.production_weight)
        score = self._params.v3_expected_income_weight * base_production
        city_missing = self._missing_resources(dict(player.resources), _CITY_COST)
        settle_missing = self._missing_resources(dict(player.resources), _SETTLEMENT_COST)
        dev_missing = self._missing_resources(dict(player.resources), _DEV_COST)
        score += self._params.v3_next_city_weight * (1.0 / (1 + city_missing))
        score += self._params.v3_next_settlement_weight * (1.0 / (1 + settle_missing))
        score += self._params.v3_next_dev_weight * (1.0 / (1 + dev_missing))
        if sum(player.resources.values()) > 7:
            score -= self._params.v3_discard_risk_penalty
        if player.roads_left <= 7 and len(simulated.placed.settlements) < 8:
            score -= self._params.v3_road_overbuild_penalty
        return score
