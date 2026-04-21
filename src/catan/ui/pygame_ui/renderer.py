from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.state import GameState

from .layout import BoardLayout


@dataclass
class DrawnUi:
    roll_button_rect: object
    end_turn_button_rect: object


class PygameRenderer:
    def __init__(self, pygame_module) -> None:
        self.pg = pygame_module
        self.font = self.pg.font.SysFont("arial", 18)
        self.small_font = self.pg.font.SysFont("arial", 14)

    def render(
        self,
        screen,
        state: GameState,
        layout: BoardLayout,
        legal_actions: Iterable[object],
        active_player: int | None,
        event_log: list[str],
        selected_action_text: str | None,
    ) -> DrawnUi:
        self.pg.draw.rect(screen, (28, 28, 32), (0, 0, 1000, 720))
        self._draw_board(screen, state, layout)
        roll_rect, end_rect = self._draw_side_panel(screen, state, active_player, legal_actions, event_log, selected_action_text)
        return DrawnUi(roll_button_rect=roll_rect, end_turn_button_rect=end_rect)

    def _draw_board(self, screen, state: GameState, layout: BoardLayout) -> None:
        for edge in state.board.edges:
            ax, ay = layout.node_positions[edge.node_a]
            bx, by = layout.node_positions[edge.node_b]
            owner = state.placed.roads.get(edge.id)
            color = (90, 90, 90) if owner is None else self._player_color(owner)
            width = 3 if owner is None else 6
            self.pg.draw.line(screen, color, (ax, ay), (bx, by), width)
            mx, my = layout.edge_midpoints[edge.id]
            screen.blit(self.small_font.render(str(edge.id), True, (180, 180, 180)), (mx + 4, my + 2))

        for node_id, (x, y) in layout.node_positions.items():
            if node_id in state.placed.cities:
                owner = state.placed.cities[node_id]
                self.pg.draw.rect(screen, self._player_color(owner), (x - 12, y - 12, 24, 24))
            elif node_id in state.placed.settlements:
                owner = state.placed.settlements[node_id]
                self.pg.draw.circle(screen, self._player_color(owner), (x, y), 11)
            else:
                self.pg.draw.circle(screen, (200, 200, 200), (x, y), 9, width=2)
            screen.blit(self.small_font.render(str(node_id), True, (220, 220, 220)), (x + 10, y - 10))

    def _draw_side_panel(self, screen, state: GameState, active_player: int | None, legal_actions, event_log, selected_action_text):
        panel_x = 700
        self.pg.draw.rect(screen, (38, 38, 44), (panel_x, 0, 300, 720))

        phase = state.phase.name
        step = state.turn.step.name if state.turn else "SETUP"
        dice = state.turn.last_roll if state.turn else None
        y = 12
        for text in [
            f"Phase: {phase}",
            f"Step: {step}",
            f"Active: P{active_player}" if active_player is not None else "Active: -",
            f"Dice: {dice}",
        ]:
            screen.blit(self.font.render(text, True, (238, 238, 238)), (panel_x + 10, y))
            y += 24

        y += 8
        screen.blit(self.font.render("Players", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for pid, player in sorted(state.players.items()):
            resources = ", ".join(f"{r.name[0]}:{c}" for r, c in player.resources.items() if c > 0) or "none"
            txt = f"P{pid} VP:{player.victory_points} RES:{resources}"
            screen.blit(self.small_font.render(txt, True, self._player_color(pid)), (panel_x + 10, y))
            y += 20

        roll_rect = self.pg.Rect(panel_x + 10, 260, 130, 32)
        end_rect = self.pg.Rect(panel_x + 150, 260, 130, 32)
        self.pg.draw.rect(screen, (70, 95, 140), roll_rect)
        self.pg.draw.rect(screen, (95, 70, 140), end_rect)
        screen.blit(self.small_font.render("Roll [R]", True, (255, 255, 255)), (roll_rect.x + 28, roll_rect.y + 8))
        screen.blit(self.small_font.render("End [E]", True, (255, 255, 255)), (end_rect.x + 32, end_rect.y + 8))

        y = 310
        screen.blit(self.font.render("Legal actions", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for line in self._summarize_legal(legal_actions):
            screen.blit(self.small_font.render(line, True, (220, 220, 220)), (panel_x + 10, y))
            y += 18

        if selected_action_text:
            y += 8
            screen.blit(self.small_font.render(f"Selected: {selected_action_text}", True, (255, 255, 190)), (panel_x + 10, y))
            y += 20

        y += 8
        screen.blit(self.font.render("Event log", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for line in event_log[-12:]:
            screen.blit(self.small_font.render(line[:45], True, (200, 200, 200)), (panel_x + 10, y))
            y += 18

        return roll_rect, end_rect

    def _summarize_legal(self, legal_actions):
        counts: dict[str, int] = {}
        for action in legal_actions:
            name = type(action).__name__
            counts[name] = counts.get(name, 0) + 1
        return [f"{name}: {count}" for name, count in sorted(counts.items())] or ["none"]

    def _player_color(self, player_id: int) -> tuple[int, int, int]:
        palette = {
            1: (235, 87, 87),
            2: (92, 178, 92),
            3: (86, 145, 235),
            4: (235, 195, 86),
        }
        return palette.get(player_id, (210, 210, 210))
