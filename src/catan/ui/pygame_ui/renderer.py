from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.action import BuildCity, BuildRoad, BuildSettlement, EndTurn, MoveRobber, PlaceSetupRoad, PlaceSetupSettlement, RollDice, StealResource
from catan.core.models.enums import ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState

from .input_mapper import HoverTarget
from .layout import BoardLayout


@dataclass
class DrawnUi:
    roll_button_rect: object
    end_turn_button_rect: object


def extract_legal_targets(state: GameState, legal_actions: Iterable[object]) -> tuple[set[int], set[int], set[int], set[int], bool, bool]:
    legal_nodes: set[int] = set()
    legal_edges: set[int] = set()
    legal_tiles: set[int] = set()
    steal_targets: set[int] = set()
    can_roll = False
    can_end = False

    for action in legal_actions:
        if isinstance(action, (PlaceSetupSettlement, BuildSettlement, BuildCity)):
            legal_nodes.add(action.node_id)
        elif isinstance(action, (PlaceSetupRoad, BuildRoad)):
            legal_edges.add(action.edge_id)
        elif isinstance(action, MoveRobber):
            legal_tiles.add(action.tile_id)
        elif isinstance(action, StealResource):
            steal_targets.add(action.target_player_id)
        elif isinstance(action, RollDice):
            can_roll = True
        elif isinstance(action, EndTurn):
            can_end = True

    steal_nodes: set[int] = set()
    robber_tile_id = state.robber_tile_id
    if robber_tile_id is not None and steal_targets:
        for node_id in state.board.tile_to_nodes.get(robber_tile_id, ()):
            owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
            if owner in steal_targets:
                steal_nodes.add(node_id)

    return legal_nodes, legal_edges, legal_tiles, steal_nodes, can_roll, can_end


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
        fullscreen: bool,
    ) -> DrawnUi:
        legal_nodes, legal_edges, legal_tiles, steal_nodes, can_roll, can_end = extract_legal_targets(state, legal_actions)
        width, height = screen.get_size()
        panel_width = 320
        panel_x = width - panel_width

        self.pg.draw.rect(screen, (28, 28, 32), (0, 0, width, height))
        self._draw_phase_banner(screen, state, width=width, panel_x=panel_x, fullscreen=fullscreen)
        self._draw_tiles(screen, state, layout, legal_tiles, hover_target.tile_id)
        self._draw_board(screen, state, layout, legal_nodes, legal_edges, steal_nodes, hover_target)
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
            panel_x=panel_x,
            panel_width=panel_width,
            height=height,
        )
        return DrawnUi(roll_button_rect=roll_rect, end_turn_button_rect=end_rect)

    def _draw_phase_banner(self, screen, state: GameState, *, width: int, panel_x: int, fullscreen: bool) -> None:
        is_setup = state.turn is None
        color = (120, 95, 40) if is_setup else (40, 95, 120)
        label = "SETUP PHASE" if is_setup else "MAIN TURN"
        board_width = max(panel_x - 40, 200)
        self.pg.draw.rect(screen, color, (20, 20, board_width, 30), border_radius=6)
        mode = "Fullscreen" if fullscreen else "Windowed"
        banner_text = f"{label}  |  {mode} (F11 toggle)"
        screen.blit(self.font.render(banner_text, True, (255, 255, 255)), (30, 26))

    def _draw_tiles(self, screen, state: GameState, layout: BoardLayout, legal_tiles: set[int], hover_tile: int | None) -> None:
        if not layout.tile_polygons:
            return
        for tile in state.board.tiles:
            polygon = layout.tile_polygons.get(tile.id)
            label_pos = layout.tile_label_positions.get(tile.id)
            if polygon is None or label_pos is None:
                continue

            color = self._terrain_color(tile.terrain)
            self.pg.draw.polygon(screen, color, polygon)
            border = (50, 50, 50)
            border_width = 2
            if tile.id in legal_tiles:
                border = (250, 240, 80)
                border_width = 4
            if hover_tile == tile.id:
                border = (255, 255, 170)
                border_width = 5
            self.pg.draw.polygon(screen, border, polygon, width=border_width)

            resource_label = self._terrain_name(tile.terrain)
            number_label = str(tile.number_token) if tile.number_token is not None else "-"
            center_x, center_y = label_pos
            has_robber = tile.id == state.robber_tile_id
            resource_y = center_y - 14
            number_y = center_y + (10 if has_robber else 2)
            screen.blit(self.small_font.render(resource_label, True, (20, 20, 20)), (center_x - 28, resource_y))
            screen.blit(self.font.render(number_label, True, (20, 20, 20)), (center_x - 8, number_y))
            screen.blit(self.small_font.render(f"#{tile.id}", True, (60, 60, 60)), (center_x - 10, center_y + 24))
            if has_robber:
                self.pg.draw.circle(screen, (240, 240, 240), (center_x, center_y), 18, width=2)
                self.pg.draw.circle(screen, (10, 10, 10), (center_x, center_y), 14)

    def _draw_board(
        self,
        screen,
        state: GameState,
        layout: BoardLayout,
        legal_nodes: set[int],
        legal_edges: set[int],
        steal_nodes: set[int],
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
            if node_id in steal_nodes:
                self.pg.draw.circle(screen, (255, 120, 120), (x, y), 17, width=4)
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
        *,
        panel_x: int,
        panel_width: int,
        height: int,
    ):
        self.pg.draw.rect(screen, (38, 38, 44), (panel_x, 0, panel_width, height))

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
            screen.blit(self.small_font.render(f"P{active_player} VP: {player.victory_points}", True, self._player_color(active_player)), (panel_x + 10, y))
            y += 20
            screen.blit(self.small_font.render("Resources:", True, (220, 220, 220)), (panel_x + 10, y))
            y += 18
            for resource in [ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]:
                label = self._resource_name(resource)
                amount = player.resources.get(resource, 0)
                screen.blit(self.small_font.render(f"{label}: {amount}", True, (220, 220, 220)), (panel_x + 10, y))
                y += 16

        y += 8
        roll_rect = self.pg.Rect(panel_x + 10, y, 145, 34)
        end_rect = self.pg.Rect(panel_x + 165, y, 145, 34)
        roll_color = (70, 95, 140) if can_roll else (55, 55, 60)
        end_color = (95, 70, 140) if can_end else (55, 55, 60)
        self.pg.draw.rect(screen, roll_color, roll_rect)
        self.pg.draw.rect(screen, end_color, end_rect)
        screen.blit(self.small_font.render("Roll [R]", True, (255, 255, 255)), (roll_rect.x + 35, roll_rect.y + 8))
        screen.blit(self.small_font.render("End [E]", True, (255, 255, 255)), (end_rect.x + 40, end_rect.y + 8))

        y += 48
        screen.blit(self.font.render("Legal actions", True, (238, 238, 238)), (panel_x + 10, y))
        y += 22
        for line in self._summarize_legal(legal_actions):
            screen.blit(self.small_font.render(line, True, (220, 220, 220)), (panel_x + 10, y))
            y += 17
        if state.turn and state.turn.step == TurnStep.ROBBER_STEAL:
            y += 2
            screen.blit(self.small_font.render("Select a victim settlement/city", True, (255, 160, 160)), (panel_x + 10, y))
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
        available_lines = max((height - y - 12) // 16, 6)
        for line in event_log[-available_lines:]:
            screen.blit(self.small_font.render(line[:48], True, (200, 200, 200)), (panel_x + 10, y))
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

    def _terrain_name(self, terrain: TerrainType) -> str:
        names = {
            TerrainType.HILLS: "Brick",
            TerrainType.FOREST: "Lumber",
            TerrainType.FIELDS: "Wheat",
            TerrainType.MOUNTAINS: "Ore",
            TerrainType.PASTURE: "Sheep",
            TerrainType.DESERT: "Desert",
        }
        return names.get(terrain, terrain.name.title())

    def _resource_name(self, resource: ResourceType) -> str:
        names = {
            ResourceType.BRICK: "Brick",
            ResourceType.LUMBER: "Lumber",
            ResourceType.GRAIN: "Wheat",
            ResourceType.ORE: "Ore",
            ResourceType.WOOL: "Sheep",
        }
        return names[resource]
