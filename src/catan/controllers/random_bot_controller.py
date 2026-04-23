from __future__ import annotations

import random
import time
from typing import Any, Sequence

from catan.core.models.action import Action, DiscardResources, ProposePlayerTrade
from catan.core.models.enums import ResourceType
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation

DEFAULT_BOT_ACTION_DELAY_SECONDS = 1.2


class RandomBotController:
    """Simple bot that chooses uniformly at random from legal actions."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        delay_seconds: float = DEFAULT_BOT_ACTION_DELAY_SECONDS,
        enable_delay: bool = True,
    ) -> None:
        self._rng = random.Random(seed)
        self._delay_seconds = delay_seconds
        self._enable_delay = enable_delay

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        state = observation.state if isinstance(observation, DebugObservation) else None
        candidates = [action for action in legal_actions if not isinstance(action, ProposePlayerTrade)]
        if not candidates:
            raise ValueError("RandomBotController received no selectable legal actions.")

        if state is not None:
            discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
            if discard_placeholder is not None:
                chosen = self._choose_discard_action(state, discard_placeholder.player_id)
                self._record_decision(chosen_action=chosen, legal_action_count=len(candidates))
                return chosen

        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        chosen = candidates[self._rng.randrange(len(candidates))]
        self._record_decision(chosen_action=chosen, legal_action_count=len(candidates))
        return chosen

    def set_delay_seconds(self, delay_seconds: float) -> None:
        self._delay_seconds = max(0.0, delay_seconds)

    def get_last_decision(self) -> dict[str, Any] | None:
        return getattr(self, "_last_decision", None)

    def _record_decision(self, *, chosen_action: Action, legal_action_count: int) -> None:
        self._last_decision = {
            "kind": "random",
            "chosen_action": chosen_action,
            "legal_action_count": legal_action_count,
            "message": f"Random choice from {legal_action_count} legal actions",
        }

    def _choose_discard_action(self, state: GameState, player_id: int) -> DiscardResources:
        required = state.discard_requirements.get(player_id, 0)
        hand = dict(state.players[player_id].resources)
        discards: dict[ResourceType, int] = {resource: 0 for resource in ResourceType}
        available_resources = [resource for resource, amount in hand.items() if amount > 0]
        for _ in range(required):
            pick = available_resources[self._rng.randrange(len(available_resources))]
            discards[pick] += 1
            hand[pick] -= 1
            if hand[pick] <= 0:
                available_resources = [resource for resource in available_resources if hand[resource] > 0]
        return DiscardResources(
            player_id=player_id,
            resources=tuple((resource, amount) for resource, amount in discards.items() if amount > 0),
        )
