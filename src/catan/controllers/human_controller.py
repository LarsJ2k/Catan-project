from __future__ import annotations

from collections import deque
from typing import Sequence

from catan.core.models.action import Action
from catan.core.observer import Observation


class NoActionAvailableYet(Exception):
    """Raised when no player input has been submitted yet."""


class HumanController:
    def __init__(self) -> None:
        self._queued_actions: deque[Action] = deque()

    def submit_action_intent(self, action: Action) -> None:
        self._queued_actions.append(action)

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        legal_set = set(legal_actions)
        while self._queued_actions:
            candidate = self._queued_actions.popleft()
            if candidate in legal_set:
                return candidate
        raise NoActionAvailableYet("Waiting for human player input.")
