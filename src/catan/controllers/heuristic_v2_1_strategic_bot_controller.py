from __future__ import annotations

from typing import Any, Sequence

from catan.controllers.heuristic_strategic_helpers import classify_game_phase, detect_bottlenecks, estimate_distances, forced_candidates
from catan.controllers.heuristic_v2_positional_bot_controller import HeuristicV2PositionalBotController
from catan.core.models.action import Action
from catan.core.observer import DebugObservation, Observation


class HeuristicV2_1StrategicBotController(HeuristicV2PositionalBotController):
    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None:
            return super().choose_action(observation, legal_actions)
        scored = [(a, self._score_action_for_v2_shortlist(a, state, legal_actions)) for a in legal_actions]
        candidates = forced_candidates(self, state, legal_actions, scored, max(1, int(self._params.candidate_count)))
        normalized = self._normalize_action_scores([(a, s) for a, s in scored if a in candidates])
        eval_player = state.turn.current_player if state.turn else candidates[0].player_id
        current_eval = self._evaluator.evaluate(state, eval_player, self._params)
        phase = classify_game_phase(state, eval_player)
        profile = detect_bottlenecks(self, state, eval_player)
        distances = estimate_distances(self, state, eval_player)
        details: list[dict[str, Any]] = []
        best = None
        best_actions: list[Action] = []
        for action in candidates:
            action_score = next(s for a, s in scored if a == action)
            position_score, summary, _ = self._evaluate_after_action(state, action, current_eval.total_score)
            strategic = (20.0 / (1 + distances["city"])) + (16.0 / (1 + distances["settlement"])) + (8.0 / (1 + distances["dev"]))
            if phase.value == "EARLY":
                strategic += 8.0 / (1 + distances["settlement"])
            elif phase.value == "LATE":
                strategic += 10.0 / (1 + distances["city"])
            penalty = 0.0
            if profile.no_good_expansion_targets and action.__class__.__name__ == "BuildRoad":
                penalty += 20.0
            if profile.road_overbuilt and action.__class__.__name__ == "BuildRoad":
                penalty += 12.0
            combined = 0.3 * normalized[action] + 0.6 * position_score + strategic - penalty
            details.append({"action": action, "action_score": action_score, "position_delta": position_score - current_eval.total_score, "strategic_goal_score": strategic, "game_phase": phase.value, "bottlenecks": profile.__dict__, "turns_to_build": distances, "useless_action_penalty": penalty, "combined_score": combined, "summary": summary})
            if best is None or combined > best:
                best = combined
                best_actions = [action]
            elif abs(combined - best) < 1e-9:
                best_actions.append(action)
        chosen = best_actions[self._rng.randrange(len(best_actions))]
        details.sort(key=lambda d: d["combined_score"], reverse=True)
        self._last_decision = {"kind": "heuristic_v2_1_strategic", "chosen_action": chosen, "top_candidates": details[:3], "legal_action_count": len(legal_actions)}
        return chosen
