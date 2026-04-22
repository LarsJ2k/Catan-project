from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from catan.controllers.base import Controller
from catan.core.engine import apply_action, get_legal_actions, is_terminal
from catan.core.models.enums import GamePhase
from catan.core.models.state import GameState


class DebugTextRunner:
    """Headless runner with detailed trace output for debugging game flow."""

    def run(self, state: GameState, controllers: Mapping[int, Controller], max_steps: int = 200) -> GameState:
        current = state
        for step in range(max_steps):
            if is_terminal(current):
                print(self._terminal_line(current, step))
                return current

            actor = self._active_player(current)
            if actor is None:
                print("no_active_player; stopping")
                return current

            legal = get_legal_actions(current, actor)
            if not legal:
                print(f"no_legal_actions player={actor}; stopping")
                return current

            print(self._pre_action_summary(step, current, actor, legal))
            action = controllers[actor].choose_action(replace(current), legal)
            current = apply_action(current, action)
            print(self._post_action_summary(current, action))

        print("max_steps_reached")
        return current

    def _active_player(self, state: GameState) -> int | None:
        if state.turn is not None and state.turn.priority_player is not None:
            return state.turn.priority_player
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player

    def _pre_action_summary(self, step: int, state: GameState, actor: int, legal: list[object]) -> str:
        phase = state.phase.name
        turn_step = state.turn.step.name if state.turn is not None else "SETUP"
        dice = state.turn.last_roll if state.turn is not None else None
        legal_summary = self._summarize_legal_actions(legal)
        score = ", ".join(
            f"P{pid}:VP={p.victory_points},RES={sum(p.resources.values())}"
            for pid, p in sorted(state.players.items())
        )
        return (
            f"step={step} phase={phase}/{turn_step} active=P{actor} "
            f"dice={dice} scores=[{score}] legal={legal_summary}"
        )

    def _post_action_summary(self, state: GameState, action: object) -> str:
        resources = " | ".join(
            f"P{pid}:{ {r.name: c for r, c in p.resources.items() if c > 0} }"
            for pid, p in sorted(state.players.items())
        )
        return f"applied={action} vp={ {pid: p.victory_points for pid, p in sorted(state.players.items())} } resources={resources}"

    def _summarize_legal_actions(self, legal: list[object]) -> str:
        counts: dict[str, int] = {}
        for action in legal:
            name = type(action).__name__
            counts[name] = counts.get(name, 0) + 1
        return ",".join(f"{k}:{v}" for k, v in sorted(counts.items()))

    def _terminal_line(self, state: GameState, step: int) -> str:
        if state.phase == GamePhase.GAME_OVER:
            return f"game_over winner={state.winner} step={step}"
        return f"terminal winner={state.winner} step={step}"
