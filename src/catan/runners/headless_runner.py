from __future__ import annotations

from typing import Mapping

from catan.controllers.base import Controller
from catan.core.engine import apply_action, get_legal_actions, get_observation, is_terminal
from catan.core.models.state import GameState


class HeadlessRunner:
    def play_until_terminal(self, state: GameState, controllers: Mapping[int, Controller], max_steps: int = 10_000) -> GameState:
        steps = 0
        current = state
        while not is_terminal(current) and steps < max_steps:
            if current.turn is None:
                break
            player_id = current.turn.current_player
            controller = controllers[player_id]
            legal = get_legal_actions(current, player_id)
            observation = get_observation(current, player_id)
            if not legal:
                break
            action = controller.choose_action(observation, legal)
            current = apply_action(current, action)
            steps += 1
        return current
