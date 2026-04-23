from __future__ import annotations

import random
import time
from typing import Sequence

from catan.core.models.action import Action, ProposePlayerTrade
from catan.core.observer import Observation

DEFAULT_BOT_ACTION_DELAY_SECONDS = 0.6


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
        del observation
        candidates = [action for action in legal_actions if not isinstance(action, ProposePlayerTrade)]
        if not candidates:
            raise ValueError("RandomBotController received no selectable legal actions.")

        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        return candidates[self._rng.randrange(len(candidates))]
