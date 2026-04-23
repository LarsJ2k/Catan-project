from __future__ import annotations

from collections import deque
from typing import Sequence

from catan.core.models.action import Action, DiscardResources, ProposePlayerTrade
from catan.core.observer import Observation


class NoActionAvailableYet(Exception):
    """Raised when no player input has been submitted yet."""


class HumanController:
    def __init__(self) -> None:
        self._queued_actions: deque[Action] = deque()

    def submit_action_intent(self, action: Action) -> None:
        self._queued_actions.append(action)

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        while self._queued_actions:
            candidate = self._queued_actions.popleft()
            if self._matches_legal(candidate, legal_actions):
                return candidate
        raise NoActionAvailableYet("Waiting for human player input.")

    def _matches_legal(self, candidate: Action, legal_actions: Sequence[Action]) -> bool:
        if candidate in set(legal_actions):
            return True
        if isinstance(candidate, DiscardResources):
            return any(isinstance(action, DiscardResources) for action in legal_actions)
        if isinstance(candidate, ProposePlayerTrade):
            return True
        return False
