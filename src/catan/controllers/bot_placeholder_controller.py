from __future__ import annotations

from typing import Sequence

from catan.core.models.action import Action
from catan.core.observer import Observation


class BotPlaceholderController:
    """Simple placeholder bot that picks the first legal action."""

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        del observation
        if not legal_actions:
            raise ValueError("BotPlaceholderController received no legal actions.")
        return legal_actions[0]
