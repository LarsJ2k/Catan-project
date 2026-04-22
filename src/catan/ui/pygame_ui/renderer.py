from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.action import BuildCity, BuildRoad, BuildSettlement, EndTurn, PlaceSetupRoad, PlaceSetupSettlement, RollDice
from catan.core.models.enums import TerrainType
from catan.core.models.state import GameState

from .input_mapper import HoverTarget
from .layout import BoardLayout


@dataclass
class DrawnUi:
    roll_button_rect: object
    end_turn_button_rect: object


def extract_legal_targets(legal_actions: Iterable[object]) -> tuple[set[int], set[int], bool, bool]:
    legal_nodes: set[int] = set()
    legal_edges: set[int] = set()
    can_roll = False
    can_end = False

    for action in legal_actions:
        if isinstance(action, (PlaceSetupSettlement, BuildSettlement, BuildCity)):
            legal_nodes.add(action.node_id)
        elif isinstance(action, (PlaceSetupRoad, BuildRoad)):
            legal_edges.add(action.edge_id)
        elif isinstance(action, RollDice):
            can_roll = True
        elif isinstance(action, EndTurn):
            can_end = True

    return legal_nodes, legal_edges, can_roll, can_end


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
        hover_target: HoverTarget,
        last_applied_action: str | None,
    ) -> DrawnUi:
        legal_nodes, legal_edges, can_roll, can_end = extract_legal_targets(legal_actions)

        self.pg.draw.rect(screen, (28, 28, 32), (0, 0, 1000, 720))
        self._draw_phase_banner(screen, state)
        self._draw_tiles(screen, state, layout)
        self._draw_board(screen, state, layout, legal_nodes, legal_edges, hover_target)
        roll_rect, end_rect = self._draw_side_panel(
            screen,
            state,
            active_player,
            legal_actions,
            event_log,
            selected_action_text,
            can_roll,
            can_end,
            last_applied_action,
        )
        return DrawnUi(roll_button_rect=roll_rect, end_turn_button_rect=end_rect)

    def _draw_phase_banner(self, screen, state: GameState) -> None:
        is_setup = state.turn is None
        color = (120, 95, 40) if is_setup else (40, 95, 120)
        label = "SETUP PHASE" if is_setup else "MAIN TURN"
        self.pg.draw.rect(screen, color, (20, 20, 650, 28), border_radius=6)
        screen.blit(self.font.render(label, True, (255, 255, 255)), (30, 25))

    def _draw_tiles(self, screen, state: GameState, layout: BoardLayout) -> None:
        if not layout.tile_polygons:
            return
        for tile in state.board.tiles:
            polygon = layout.tile_polygons.get(tile.id)
            label_pos = layout.tile_label_positions.get(tile.id)
            if polygon is None or label_pos is None:
                continue

            color = self._terrain_color(tile.terrain)
            self.pg.draw.polygon(screen, color, polygon)
            self.pg.draw.polygon(screen, (50, 50, 50), polygon, width=2)

            resource_label = tile.terrain.name[:3]
            number_label = str(tile.number_token) if tile.number_token is not None else "-"
            center_x, center_y = label_pos
            screen.blit(self.small_font.render(resource_label, True, (20, 20, 20)), (center_x - 14, center_y - 14))
            screen.blit(self.font.render(number_label, True, (20, 20, 20)), (center_x - 10, center_y + 2))
            screen.blit(self.small_font.render(f"#{tile.id}", True, (60, 60, 60)), (center_x - 10, center_y + 24))

    def _draw_board(
        self,
        screen,
        state: GameState,
        layout: BoardLayout,
        legal_nodes: set[int],
        legal_edges: set[int],
        hover_target: HoverTarget,
    ) -> None:
        for edge in state.board.edges:
            ax, ay = layout.node_positions[edge.node_a]
            bx, by = layout.node_positions[edge.node_b]
            owner = state.placed.roads.get(edge.id)
            color = (95, 95, 95) if owner is None else self._player_color(owner)
            width = 3 if owner is None else 7

            if edge.id in legal_edges:
                color = (240, 235, 90)
                width = 9
            if hover_target.edge_id == edge.id:
                color = (255, 255, 170)
                width = max(width, 11)

            self.pg.draw.line(screen, color, (ax, ay), (bx, by), width)

        for node_id, (x, y) in layout.node_positions.items():
            if node_id in state.placed.cities:
                owner = state.placed.cities[node_id]
                self.pg.draw.rect(screen, self._player_color(owner), (x - 12, y - 12, 24, 24))
            elif node_id in state.placed.settlements:
                owner = state.placed.settlements[node_id]
                self.pg.draw.circle(screen, self._player_color(owner), (x, y), 11)
            else:
                self.pg.draw.circle(screen, (210, 210, 210), (x, y), 9, width=2)

            if node_id in legal_nodes:
                self.pg.draw.circle(screen, (250, 240, 80), (x, y), 15, width=3)
            if hover_target.node_id == node_id:
                self.pg.draw.circle(screen, (255, 255, 170), (x, y), 19, width=3)

    def _draw_side_panel(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        legal_actions,
        event_log,
        selected_action_text,
        can_roll: bool,
        can_end: bool,
        last_applied_action: str | None,
    ):
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
            f"Last Roll: {dice}",
        ]:
            screen.blit(self.font.render(text, True, (238, 238, 238)), (panel_x + 10, y))
            y += 24

        y += 8
        screen.blit(self.font.render("Current Player", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        if active_player is not None:
            player = state.players[active_player]
            resources = ", ".join(f"{r.name[0]}:{c}" for r, c in player.resources.items() if c > 0) or "none"
            screen.blit(self.small_font.render(f"P{active_player} VP: {player.victory_points}", True, self._player_color(active_player)), (panel_x + 10, y))
            y += 18
            screen.blit(self.small_font.render(f"Resources: {resources}", True, (220, 220, 220)), (panel_x + 10, y))
            y += 18

        y += 8
        roll_rect = self.pg.Rect(panel_x + 10, y, 130, 34)
        end_rect = self.pg.Rect(panel_x + 150, y, 130, 34)
        roll_color = (70, 95, 140) if can_roll else (55, 55, 60)
        end_color = (95, 70, 140) if can_end else (55, 55, 60)
        self.pg.draw.rect(screen, roll_color, roll_rect)
        self.pg.draw.rect(screen, end_color, end_rect)
        screen.blit(self.small_font.render("Roll [R]", True, (255, 255, 255)), (roll_rect.x + 28, roll_rect.y + 8))
        screen.blit(self.small_font.render("End [E]", True, (255, 255, 255)), (end_rect.x + 32, end_rect.y + 8))

        y += 48
        screen.blit(self.font.render("Legal actions", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for line in self._summarize_legal(legal_actions):
            screen.blit(self.small_font.render(line, True, (220, 220, 220)), (panel_x + 10, y))
            y += 17

        y += 6
        if selected_action_text:
            screen.blit(self.small_font.render(f"Selected: {selected_action_text}", True, (255, 255, 190)), (panel_x + 10, y))
            y += 18
        if last_applied_action:
            screen.blit(self.small_font.render(f"Applied: {last_applied_action}", True, (170, 240, 170)), (panel_x + 10, y))
            y += 18

        y += 8
        screen.blit(self.font.render("Event log", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for line in event_log[-14:]:
            screen.blit(self.small_font.render(line[:46], True, (200, 200, 200)), (panel_x + 10, y))
            y += 16

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

    def _terrain_color(self, terrain: TerrainType) -> tuple[int, int, int]:
        colors = {
            TerrainType.FOREST: (104, 165, 90),
            TerrainType.HILLS: (197, 129, 96),
            TerrainType.PASTURE: (170, 207, 117),
            TerrainType.FIELDS: (218, 205, 120),
            TerrainType.MOUNTAINS: (160, 160, 160),
            TerrainType.DESERT: (226, 209, 162),
        }
        return colors.get(terrain, (200, 200, 200))
