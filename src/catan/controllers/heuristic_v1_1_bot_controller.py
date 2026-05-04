from __future__ import annotations

from typing import Sequence

from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters
from catan.controllers.heuristic_v1_baseline_bot_controller import (
    _CITY_COST,
    _DEV_COST,
    _SETTLEMENT_COST,
    HeuristicV1BaselineBotController,
)
from catan.core.models.action import Action, BuildCity, BuildRoad, BuildSettlement, BuyDevelopmentCard
from catan.core.models.enums import ResourceType
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation
from catan.runners.game_setup import ControllerType


class HeuristicV1_1BotController(HeuristicV1BaselineBotController):
    """Refined v1 heuristic: better savings discipline and stronger setup profile checks."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        delay_seconds: float = 1.2,
        enable_delay: bool = True,
        heuristic_params: HeuristicScoringParams | None = None,
    ) -> None:
        params = heuristic_params or HeuristicScoringParams.from_mapping(default_family_parameters(ControllerType.HEURISTIC_V1_1))
        super().__init__(seed=seed, delay_seconds=delay_seconds, enable_delay=enable_delay, heuristic_params=params)
        self._has_legal_settlement = False
        self._has_legal_city = False
        self._city_missing_resources = 99
        self._score_notes: dict[int, str] = {}

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        state = observation.state if isinstance(observation, DebugObservation) else None
        self._has_legal_settlement = any(isinstance(action, BuildSettlement) for action in legal_actions)
        self._has_legal_city = any(isinstance(action, BuildCity) for action in legal_actions)
        self._city_missing_resources = self._city_missing_count(state)
        self._score_notes: dict[int, str] = {}
        return super().choose_action(observation, legal_actions)

    def _record_decision(self, *, chosen_action: Action, scored_candidates: list[tuple[Action, float]], legal_action_count: int) -> None:
        super()._record_decision(
            chosen_action=chosen_action,
            scored_candidates=scored_candidates,
            legal_action_count=legal_action_count,
        )
        self._last_decision["kind"] = "heuristic_v1_1"
        reasons: list[str] = []
        if isinstance(chosen_action, BuildRoad) and self._has_legal_settlement:
            reasons.append("road penalized: legal settlement exists")
        if isinstance(chosen_action, BuyDevelopmentCard) and (self._has_legal_city or self._city_missing_resources <= 1):
            reasons.append("dev-card penalized: city is legal/near")
        note = self._score_notes.get(id(chosen_action))
        if note:
            reasons.append(note)
        if reasons:
            self._last_decision["reasons"] = reasons

    def _score_action(self, action: Action, state: GameState | None) -> float:
        score = super()._score_action(action, state)
        note_parts: list[str] = []
        if isinstance(action, BuildRoad):
            road_progress = 0.0
            if self._has_legal_settlement:
                score -= self._params.road_when_settlement_available_penalty
                note_parts.append("road penalty: settlement available")
            else:
                road_progress = self._score_road_progress(
                    state,
                    self._roads_to_targets(state, action.player_id) if state is not None else {},
                    self._roads_to_targets(state, action.player_id, planned_edges={action.edge_id}) if state is not None else {},
                )
                if road_progress > 0:
                    score += self._params.road_no_settlement_progress_bonus
                    note_parts.append("road bonus: no settlement available")
                    score += self._params.road_base_score * 0.35
                    note_parts.append("road bonus: proactive expansion")

            if state is not None:
                player_resources = state.players[action.player_id].resources
                should_preserve_settlement_pair = self._has_legal_settlement or road_progress <= 0
                if should_preserve_settlement_pair and (
                    player_resources.get(ResourceType.BRICK, 0) <= 1 or player_resources.get(ResourceType.LUMBER, 0) <= 1
                ):
                    score -= self._params.road_settlement_resource_lock_penalty
                    note_parts.append("road penalty: consumes brick/lumber needed for settlement")

        if isinstance(action, BuyDevelopmentCard):
            if self._has_legal_city:
                score -= self._params.dev_when_city_ready_penalty
                note_parts.append("dev penalty: legal city exists")
            elif self._city_missing_resources <= 1:
                score -= self._params.dev_when_city_near_penalty
                note_parts.append("dev penalty: near city")

        if note_parts:
            self._score_notes[id(action)] = "; ".join(note_parts)
        return score

    def _score_settlement_node(self, node_id, state: GameState | None, *, in_setup: bool):
        base = super()._score_settlement_node(node_id, state, in_setup=in_setup)
        if not in_setup or state is None:
            return base

        resources = self._node_resources(node_id, state)
        expansion_profile = {ResourceType.LUMBER, ResourceType.BRICK, ResourceType.GRAIN, ResourceType.WOOL}
        city_profile = {ResourceType.ORE, ResourceType.GRAIN, ResourceType.WOOL}
        expansion_bonus = self._profile_bonus(resources, expansion_profile, self._params.setup_expansion_profile_bonus)
        city_bonus = self._profile_bonus(resources, city_profile, self._params.setup_city_dev_profile_bonus)

        missing_penalty = (
            (len(expansion_profile - resources) + len(city_profile - resources))
            * self._params.setup_profile_missing_penalty
        )
        return base + expansion_bonus + city_bonus - missing_penalty

    def _evaluate_dev_purchase(self, state: GameState | None) -> float:
        score = super()._evaluate_dev_purchase(state)
        if self._has_legal_city:
            return score - self._params.dev_when_city_ready_penalty
        if self._city_missing_resources <= 1:
            return score - self._params.dev_when_city_near_penalty
        return score

    def _score_road(self, action: BuildRoad, state: GameState | None) -> float:
        score = super()._score_road(action, state)
        if state is None:
            return score
        if self._has_legal_settlement:
            return score - (self._params.road_when_settlement_available_penalty * 0.5)
        before_distances = self._roads_to_targets(state, action.player_id)
        after_distances = self._roads_to_targets(state, action.player_id, planned_edges={action.edge_id})
        if any(after < before_distances.get(node_id, 99) for node_id, after in after_distances.items()):
            score += self._params.road_no_settlement_progress_bonus * 2.0
        return score

    def _profile_bonus(self, resources: set[ResourceType], profile: set[ResourceType], full_bonus: float) -> float:
        present = len(resources & profile)
        if present == len(profile):
            return full_bonus
        return (present / max(1, len(profile))) * (full_bonus * 0.55)

    def _city_missing_count(self, state: GameState | None) -> int:
        if state is None or state.turn is None:
            return 99
        player = state.players[state.turn.current_player]
        return self._missing_resources(dict(player.resources), _CITY_COST)
