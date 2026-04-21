from __future__ import annotations

from typing import Mapping

from catan.controllers.human_controller import HumanController
from catan.core.engine import get_legal_actions
from catan.core.models.state import GameState
from catan.runners.local_pygame_runner import LocalPygameRunner

from .input_mapper import PygameInputMapper
from .layout import build_circular_layout
from .renderer import PygameRenderer


class PygameApp:
    def __init__(self, pygame_module, *, width: int = 1000, height: int = 720) -> None:
        self.pg = pygame_module
        self.width = width
        self.height = height
        self.renderer = PygameRenderer(pygame_module)
        self.input_mapper = PygameInputMapper(pygame_module)
        self.runner = LocalPygameRunner()

    def run(self, initial_state: GameState, controllers: Mapping[int, HumanController]) -> GameState:
        self.pg.init()
        self.pg.display.set_caption("Catan MVP (Debug UI)")
        screen = self.pg.display.set_mode((self.width, self.height))
        clock = self.pg.time.Clock()

        state = initial_state
        layout = build_circular_layout(state.board, center=(340, 340), radius=260)
        event_log = ["game started"]
        selected_action_text: str | None = None

        running = True
        while running:
            active_player = self._active_player(state)
            legal = get_legal_actions(state, active_player) if active_player is not None else []
            drawn = self.renderer.render(screen, state, layout, legal, active_player, event_log, selected_action_text)

            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    running = False
                    break

                if active_player is None or active_player not in controllers:
                    continue

                mapped = self.input_mapper.map_event(
                    event,
                    legal_actions=legal,
                    layout=layout,
                    roll_rect=drawn.roll_button_rect,
                    end_rect=drawn.end_turn_button_rect,
                )
                if mapped.action is not None:
                    selected_action_text = str(mapped.action)
                    controllers[active_player].submit_action_intent(mapped.action)
                    if mapped.status:
                        event_log.append(f"P{active_player}: {mapped.status}")

            if active_player is not None and active_player in controllers:
                before = state
                state = self.runner.tick(state, controllers[active_player], active_player)
                if state != before:
                    event_log.append(f"applied: {selected_action_text or 'action'}")
                    selected_action_text = None

            self.pg.display.flip()
            clock.tick(30)

        self.pg.quit()
        return state

    def _active_player(self, state: GameState) -> int | None:
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player
