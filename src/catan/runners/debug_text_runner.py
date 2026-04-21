from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from catan.controllers.base import Controller
from catan.core.engine import apply_action, get_legal_actions, is_terminal
from catan.core.models.state import GameState


class DebugTextRunner:
    """Minimal headless runner that prints turn/action summaries."""

    def run(self, state: GameState, controllers: Mapping[int, Controller], max_steps: int = 200) -> GameState:
        current = state
        for step in range(max_steps):
            if is_terminal(current):
                print(f"game_over winner={current.winner} step={step}")
                return current

            actor = current.setup.pending_settlement_player or current.setup.pending_road_player
            if current.turn is not None:
                actor = current.turn.current_player

            if actor is None:
                print("no_active_player; stopping")
                return current

            legal = get_legal_actions(current, actor)
            if not legal:
                print(f"no_legal_actions player={actor}; stopping")
                return current

            action = controllers[actor].choose_action(replace(current), legal)
            print(f"step={step} player={actor} action={action}")
            current = apply_action(current, action)

        print("max_steps_reached")
        return current
