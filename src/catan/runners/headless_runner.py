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
            if current.turn is None and current.phase.name.startswith("SETUP") is False:
                break
            player_id = self._active_player(current)
            if player_id is None:
                break
            controller = controllers[player_id]
            legal = get_legal_actions(current, player_id)
            observation = get_observation(current, player_id)
            if not legal:
                break
            action = controller.choose_action(observation, legal)
            current = apply_action(current, action)
            steps += 1
        return current

    def _active_player(self, state: GameState) -> int | None:
        if state.turn is not None and state.turn.priority_player is not None:
            return state.turn.priority_player
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player
