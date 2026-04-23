from __future__ import annotations

import copy
from typing import Any, Sequence

from catan.controllers.heuristic_v1_1_bot_controller import HeuristicV1_1BotController
from catan.controllers.heuristic_v2_position_evaluator import HeuristicV2PositionEvaluator
from catan.core.engine import apply_action
from catan.core.models.action import (
    Action,
    BuyDevelopmentCard,
    DiscardResources,
    ProposePlayerTrade,
    RollDice,
    StealResource,
)
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation


class HeuristicV2PositionalBotController(HeuristicV1_1BotController):
    """V2 positional heuristic that evaluates simulated resulting positions."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        delay_seconds: float = 1.2,
        enable_delay: bool = True,
        heuristic_params=None,
    ) -> None:
        super().__init__(seed=seed, delay_seconds=delay_seconds, enable_delay=enable_delay, heuristic_params=heuristic_params)
        self._evaluator = HeuristicV2PositionEvaluator()

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        candidates = [action for action in legal_actions if not isinstance(action, ProposePlayerTrade)]
        if not candidates:
            fallback = legal_actions[self._rng.randrange(len(legal_actions))]
            self._last_decision = {
                "kind": "heuristic_v2_positional",
                "chosen_action": fallback,
                "top_candidates": [{"action": fallback, "action_score": -5.0, "position_score": 0.0, "combined_score": -5.0}],
                "legal_action_count": len(legal_actions),
            }
            return fallback

        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None:
            chosen = super().choose_action(observation, candidates)
            if isinstance(self._last_decision, dict):
                self._last_decision["kind"] = "heuristic_v2_positional"
            return chosen
        discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
        if discard_placeholder is not None:
            chosen = self._choose_discard_action(state, discard_placeholder.player_id)
            self._last_decision = {
                "kind": "heuristic_v2_positional",
                "chosen_action": chosen,
                "top_candidates": [
                    {
                        "action": chosen,
                        "action_score": 25.0,
                        "normalized_action_score": 100.0,
                        "position_score": 0.0,
                        "combined_score": 25.0,
                        "summary": "discard policy",
                    }
                ],
                "legal_action_count": len(candidates),
            }
            return chosen

        candidate_count = max(1, int(self._params.candidate_count))
        action_scored = [(action, self._score_action(action, state)) for action in candidates]
        action_scored.sort(key=lambda item: item[1], reverse=True)
        shortlisted = action_scored[:candidate_count]
        normalized = self._normalize_action_scores(shortlisted)

        ranked_details: list[dict[str, Any]] = []
        best_total: float | None = None
        best_actions: list[Action] = []

        for action, action_score in shortlisted:
            position_score, summary = self._evaluate_after_action(state, action)
            combined = (
                self._params.action_score_weight * normalized[action]
                + self._params.state_score_weight * position_score
            )
            detail = {
                "action": action,
                "action_score": action_score,
                "normalized_action_score": normalized[action],
                "position_score": position_score,
                "combined_score": combined,
                "summary": summary,
            }
            ranked_details.append(detail)
            if best_total is None or combined > best_total:
                best_total = combined
                best_actions = [action]
            elif abs(combined - best_total) <= 1e-9:
                best_actions.append(action)

        chosen = best_actions[self._rng.randrange(len(best_actions))]
        ranked_details.sort(key=lambda item: item["combined_score"], reverse=True)
        self._last_decision = {
            "kind": "heuristic_v2_positional",
            "chosen_action": chosen,
            "top_candidates": ranked_details[:3],
            "legal_action_count": len(candidates),
        }
        return chosen

    def _normalize_action_scores(self, scored_actions: list[tuple[Action, float]]) -> dict[Action, float]:
        values = [score for _, score in scored_actions]
        low = min(values)
        high = max(values)
        if high - low < 1e-9:
            return {action: 50.0 for action, _ in scored_actions}
        return {action: ((score - low) / (high - low)) * 100.0 for action, score in scored_actions}

    def _evaluate_after_action(self, state: GameState, action: Action) -> tuple[float, str]:
        player_id = action.player_id
        if self._is_stochastic_action(action):
            current_eval = self._evaluator.evaluate(state, player_id, self._params)
            return current_eval.total_score - 2.0, "stochastic action: current-state estimate"

        try:
            simulated_state = apply_action(copy.deepcopy(state), action)
            evaluation = self._evaluator.evaluate(simulated_state, player_id, self._params)
            return evaluation.total_score, self._summarize_components(evaluation.components)
        except Exception:
            return -1_000_000.0, "simulation failed"

    def _is_stochastic_action(self, action: Action) -> bool:
        return isinstance(action, (RollDice, BuyDevelopmentCard, StealResource))

    def _summarize_components(self, components: dict[str, float]) -> str:
        top = sorted(components.items(), key=lambda item: abs(item[1]), reverse=True)[:2]
        return ", ".join(f"{name} {value:+.1f}" for name, value in top)
