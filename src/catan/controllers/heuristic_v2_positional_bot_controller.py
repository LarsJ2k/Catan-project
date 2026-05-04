from __future__ import annotations

from time import perf_counter, sleep
from typing import Any, Sequence

from catan.controllers.heuristic_v1_1_bot_controller import HeuristicV1_1BotController
from catan.controllers.heuristic_v2_position_evaluator import HeuristicV2PositionEvaluator
from catan.controllers.heuristic_v2_profiling import GLOBAL_V2_PROFILING_STATS, V2DecisionProfile
from catan.core.engine import apply_action
from catan.core.models.action import (
    Action,
    BankTrade,
    BuyDevelopmentCard,
    DiscardResources,
    ProposePlayerTrade,
    RollDice,
    StealResource,
)
from catan.core.models.state import GameState
from catan.core.models.state import PlacedPieces, PlayerState, SetupState, TurnState
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
        enable_v2_profiling: bool = False,
    ) -> None:
        super().__init__(seed=seed, delay_seconds=delay_seconds, enable_delay=enable_delay, heuristic_params=heuristic_params)
        self._evaluator = HeuristicV2PositionEvaluator()
        self._enable_v2_profiling = enable_v2_profiling

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if self._enable_delay and self._delay_seconds > 0:
            sleep(self._delay_seconds)
        profile = V2DecisionProfile()
        decision_start = perf_counter()
        prep_start = perf_counter()
        filter_start = perf_counter()
        candidates = list(legal_actions)
        profile.filter_forbidden_time_s = perf_counter() - filter_start
        if not candidates:
            fallback = legal_actions[self._rng.randrange(len(legal_actions))]
            self._last_decision = {
                "kind": "heuristic_v2_positional",
                "chosen_action": fallback,
                "top_candidates": [{"action": fallback, "action_score": -5.0, "position_score": 0.0, "combined_score": -5.0}],
                "legal_action_count": len(legal_actions),
            }
            profile.legal_action_count = len(legal_actions)
            profile.trivial_or_forced = True
            self._record_profile(profile, decision_start)
            return fallback

        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None:
            chosen = super().choose_action(observation, candidates)
            if isinstance(self._last_decision, dict):
                self._last_decision["kind"] = "heuristic_v2_positional"
            profile.legal_action_count = len(candidates)
            self._record_profile(profile, decision_start)
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
            profile.legal_action_count = len(candidates)
            profile.trivial_or_forced = True
            self._record_profile(profile, decision_start)
            return chosen

        score_start = perf_counter()
        candidate_count = max(1, int(self._params.candidate_count))
        action_scored = [(action, self._score_action(action, state)) for action in candidates]
        profile.action_scoring_time_s = perf_counter() - score_start

        topn_start = perf_counter()
        action_scored.sort(key=lambda item: item[1], reverse=True)
        shortlisted = action_scored[:candidate_count]
        normalized = self._normalize_action_scores(shortlisted)
        profile.topn_selection_time_s = perf_counter() - topn_start
        profile.legal_prep_time_s = perf_counter() - prep_start
        profile.legal_action_count = len(candidates)
        profile.candidates_considered = len(shortlisted)

        ranked_details: list[dict[str, Any]] = []
        best_total: float | None = None
        best_actions: list[Action] = []
        evaluation_player = state.turn.current_player if state.turn is not None else shortlisted[0][0].player_id
        current_eval = self._evaluator.evaluate(state, evaluation_player, self._params)
        current_position_score = current_eval.total_score

        for action, action_score in shortlisted:
            position_score, summary, candidate_profile = self._evaluate_after_action(state, action, current_position_score)
            profile.candidate_simulation_time_s += candidate_profile.candidate_simulation_time_s
            profile.state_copy_time_s += candidate_profile.state_copy_time_s
            profile.apply_action_time_s += candidate_profile.apply_action_time_s
            profile.position_eval_time_s += candidate_profile.position_eval_time_s
            profile.explanation_time_s += candidate_profile.explanation_time_s
            for name, value in candidate_profile.evaluator_component_time_s.items():
                profile.evaluator_component_time_s[name] = profile.evaluator_component_time_s.get(name, 0.0) + value
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
            if isinstance(action, BankTrade):
                note = self._score_notes.get(id(action))
                if note:
                    detail["summary"] = f"{summary} | {note}" if summary else note
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
        self._record_profile(profile, decision_start)
        return chosen

    def _normalize_action_scores(self, scored_actions: list[tuple[Action, float]]) -> dict[Action, float]:
        values = [score for _, score in scored_actions]
        low = min(values)
        high = max(values)
        if high - low < 1e-9:
            return {action: 50.0 for action, _ in scored_actions}
        return {action: ((score - low) / (high - low)) * 100.0 for action, score in scored_actions}

    def _evaluate_after_action(self, state: GameState, action: Action, current_position_score: float) -> tuple[float, str, V2DecisionProfile]:
        profile = V2DecisionProfile()
        candidate_start = perf_counter()
        player_id = action.player_id
        if self._is_stochastic_action(action):
            eval_start = perf_counter()
            current_eval = self._evaluator.evaluate(state, player_id, self._params)
            profile.position_eval_time_s = perf_counter() - eval_start
            profile.evaluator_component_time_s = dict(current_eval.timings)
            profile.candidate_simulation_time_s = perf_counter() - candidate_start
            return current_eval.total_score - 2.0, "stochastic action: current-state estimate", profile

        try:
            copy_start = perf_counter()
            simulated_state = self._clone_state_for_simulation(state)
            profile.state_copy_time_s = perf_counter() - copy_start

            apply_start = perf_counter()
            simulated_state = apply_action(simulated_state, action)
            profile.apply_action_time_s = perf_counter() - apply_start

            eval_start = perf_counter()
            evaluation = self._evaluator.evaluate(simulated_state, player_id, self._params)
            profile.position_eval_time_s = perf_counter() - eval_start
            profile.evaluator_component_time_s = dict(evaluation.timings)

            summary_start = perf_counter()
            summary = self._summarize_components(evaluation.components)
            profile.explanation_time_s = perf_counter() - summary_start

            profile.candidate_simulation_time_s = perf_counter() - candidate_start
            if isinstance(action, BankTrade):
                delta = evaluation.total_score - current_position_score
                if delta <= self._params.bank_trade_progress_threshold:
                    profile.candidate_simulation_time_s = perf_counter() - candidate_start
                    return (
                        evaluation.total_score + self._params.bank_trade_no_progress_penalty,
                        f"delta {delta:+.2f} below threshold",
                        profile,
                    )
                summary = f"delta {delta:+.2f}; {summary}" if summary else f"delta {delta:+.2f}"
            profile.candidate_simulation_time_s = perf_counter() - candidate_start
            return evaluation.total_score, summary, profile
        except Exception:
            profile.candidate_simulation_time_s = perf_counter() - candidate_start
            return -1_000_000.0, "simulation failed", profile

    def _clone_state_for_simulation(self, state: GameState) -> GameState:
        return GameState(
            board=state.board,
            players={
                player_id: PlayerState(
                    player_id=player.player_id,
                    resources=dict(player.resources),
                    roads_left=player.roads_left,
                    settlements_left=player.settlements_left,
                    cities_left=player.cities_left,
                    victory_points=player.victory_points,
                    setup_settlements_placed=player.setup_settlements_placed,
                    dev_cards=dict(player.dev_cards),
                    new_dev_cards=dict(player.new_dev_cards),
                    knights_played=player.knights_played,
                    longest_road_length=player.longest_road_length,
                    dev_cards_bought=player.dev_cards_bought,
                    dev_cards_played=player.dev_cards_played,
                    bank_trades_count=player.bank_trades_count,
                    player_trades_proposed=player.player_trades_proposed,
                    player_trades_completed=player.player_trades_completed,
                )
                for player_id, player in state.players.items()
            },
            phase=state.phase,
            setup=SetupState(
                pending_settlement_player=state.setup.pending_settlement_player,
                pending_road_player=state.setup.pending_road_player,
                pending_road_origin_node=state.setup.pending_road_origin_node,
                order=list(state.setup.order),
                index=state.setup.index,
            ),
            turn=(
                None
                if state.turn is None
                else TurnState(
                    current_player=state.turn.current_player,
                    step=state.turn.step,
                    last_roll=state.turn.last_roll,
                    priority_player=state.turn.priority_player,
                    dev_card_played_this_turn=state.turn.dev_card_played_this_turn,
                )
            ),
            placed=PlacedPieces(
                roads=dict(state.placed.roads),
                settlements=dict(state.placed.settlements),
                cities=dict(state.placed.cities),
            ),
            winner=state.winner,
            rng_state=state.rng_state,
            robber_tile_id=state.robber_tile_id,
            discard_requirements=dict(state.discard_requirements),
            player_trade=state.player_trade,
            dev_deck=state.dev_deck,
            largest_army_holder=state.largest_army_holder,
            longest_road_holder=state.longest_road_holder,
            robber_source=state.robber_source,
            dev_card_flow=state.dev_card_flow,
        )

    def _record_profile(self, profile: V2DecisionProfile, decision_start: float) -> None:
        if not self._enable_v2_profiling:
            return
        profile.decision_time_s = perf_counter() - decision_start
        GLOBAL_V2_PROFILING_STATS.record(profile)

    def _is_stochastic_action(self, action: Action) -> bool:
        return isinstance(action, (RollDice, BuyDevelopmentCard, StealResource))

    def _summarize_components(self, components: dict[str, float]) -> str:
        top = sorted(components.items(), key=lambda item: abs(item[1]), reverse=True)[:2]
        return ", ".join(f"{name} {value:+.1f}" for name, value in top)
