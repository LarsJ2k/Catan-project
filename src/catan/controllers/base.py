from __future__ import annotations

from typing import Protocol, Sequence

from catan.core.models.action import Action
from catan.core.observer import Observation


class Controller(Protocol):
    def choose_action(
        self,
        observation: Observation,
        legal_actions: Sequence[Action],
    ) -> Action:
        ...
