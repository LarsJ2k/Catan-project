from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.action import BankTrade, BuildCity, BuildRoad, BuildSettlement, EndTurn, MoveRobber, PlaceSetupRoad, PlaceSetupSettlement, RollDice, StealResource
from catan.core.models.enums import ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState

from .input_mapper import HoverTarget
from .layout import BoardLayout


@dataclass
class DrawnUi:
    roll_button_rect: object
    end_turn_button_rect: object
    action_button_rects: dict[str, object]
    event_log_scroll_up_rect: object | None
    event_log_scroll_down_rect: object | None


def probability_dot_count(number_token: int | None) -> int:
    mapping = {2: 1, 12: 1, 3: 2, 11: 2, 4: 3, 10: 3, 5: 4, 9: 4, 6: 5, 8: 5}
    if number_token is None:
        return 0
    return mapping.get(number_token, 0)


def primary_turn_button_state(*, can_roll: bool, can_end: bool) -> str:
    if can_roll:
        return "Roll Dice"
    if can_end:
        return "End Turn"
    return "Waiting"


def extract_legal_targets(
    state: GameState, legal_actions: Iterable[object], *, build_mode: str | None = None
) -> tuple[set[int], set[int], set[int], set[int], bool, bool]:
    legal_nodes: set[int] = set()
    legal_edges: set[int] = set()
    legal_tiles: set[int] = set()
    steal_targets: set[int] = set()
    can_roll = False
    can_end = False

    for action in legal_actions:
        if isinstance(action, PlaceSetupSettlement):
            legal_nodes.add(action.node_id)
        elif isinstance(action, PlaceSetupRoad):
            legal_edges.add(action.edge_id)
        elif isinstance(action, BuildSettlement):
            if build_mode == "settlement":
                legal_nodes.add(action.node_id)
        elif isinstance(action, BuildCity):
            if build_mode == "city":
                legal_nodes.add(action.node_id)
        elif isinstance(action, BuildRoad):
            if build_mode == "road":
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
        *,
        build_mode: str | None,
        trade_ui: dict[str, object] | None,
        event_log_offset: int = 0,
    ) -> DrawnUi:
        legal_nodes, legal_edges, legal_tiles, steal_nodes, can_roll, can_end = extract_legal_targets(
            state, legal_actions, build_mode=build_mode
        )
        width, height = screen.get_size()
        panel_width = max(int(width * 0.30), 360)
        bottom_bar_height = max(int(height * 0.18), 130)
        panel_x = width - panel_width

        self.pg.draw.rect(screen, (28, 28, 32), (0, 0, width, height))
        self._draw_phase_banner(screen, state, width=width, panel_x=panel_x, fullscreen=fullscreen, bottom_bar_height=bottom_bar_height)
        self._draw_tiles(screen, state, layout, legal_tiles, hover_target.tile_id)
        self._draw_board(screen, state, layout, legal_nodes, legal_edges, steal_nodes, hover_target)
        self._draw_ports(screen, state, layout)
        roll_rect, end_rect, action_button_rects, scroll_up_rect, scroll_down_rect = self._draw_side_panel(
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
            event_log_offset=event_log_offset,
        )
        self._draw_bottom_bar(screen, state, active_player, legal_actions, width, height, panel_x, bottom_bar_height, action_button_rects, trade_ui)
        if trade_ui:
            self._draw_trade_overlay(screen, state, active_player, panel_x, height, bottom_bar_height, trade_ui)
        return DrawnUi(
            roll_button_rect=roll_rect,
            end_turn_button_rect=end_rect,
            action_button_rects=action_button_rects,
            event_log_scroll_up_rect=scroll_up_rect,
            event_log_scroll_down_rect=scroll_down_rect,
        )

    def _draw_phase_banner(self, screen, state: GameState, *, width: int, panel_x: int, fullscreen: bool, bottom_bar_height: int) -> None:
        is_setup = state.turn is None
        color = (120, 95, 40) if is_setup else (40, 95, 120)
        label = "SETUP PHASE" if is_setup else "MAIN TURN"
        board_width = max(panel_x - 40, 200)
        board_height_limit = max(40, bottom_bar_height // 8)
        self.pg.draw.rect(screen, color, (20, 20, board_width, 30), border_radius=6)
        mode = "Fullscreen" if fullscreen else "Windowed"
        banner_text = f"{label}  |  {mode} (F11 toggle)"
        screen.blit(self.font.render(banner_text, True, (255, 255, 255)), (30, 26))
        self.pg.draw.line(screen, (70, 70, 75), (20, 55 + board_height_limit), (panel_x - 20, 55 + board_height_limit), 1)

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
            dot_count = probability_dot_count(tile.number_token)
            if dot_count:
                dot_start_x = center_x - ((dot_count - 1) * 5) // 2
                dot_y = center_y + 22
                for idx in range(dot_count):
                    self.pg.draw.circle(screen, (120, 40, 40), (dot_start_x + idx * 5, dot_y), 2)
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
        event_log_offset: int,
    ):
        self.pg.draw.rect(screen, (38, 38, 44), (panel_x, 0, panel_width, height))
        y = 12
        screen.blit(self.font.render("Event log", True, (238, 238, 238)), (panel_x + 10, y))
        up_rect = self.pg.Rect(panel_x + panel_width - 60, y - 2, 22, 20)
        down_rect = self.pg.Rect(panel_x + panel_width - 34, y - 2, 22, 20)
        self.pg.draw.rect(screen, (60, 60, 70), up_rect, border_radius=3)
        self.pg.draw.rect(screen, (60, 60, 70), down_rect, border_radius=3)
        screen.blit(self.small_font.render("˄", True, (230, 230, 230)), (up_rect.x + 8, up_rect.y + 2))
        screen.blit(self.small_font.render("˅", True, (230, 230, 230)), (down_rect.x + 8, down_rect.y + 2))
        y += 24
        event_end = int(height * 0.34)
        log_line_height = 16
        visible = max((event_end - y) // log_line_height, 5)
        max_offset = max(len(event_log) - visible, 0)
        offset = min(max(event_log_offset, 0), max_offset)
        start = max(len(event_log) - visible - offset, 0)
        end = start + visible
        for line in event_log[start:end]:
            screen.blit(self.small_font.render(line[:50], True, (200, 200, 200)), (panel_x + 10, y))
            y += log_line_height

        y = event_end + 12
        screen.blit(self.font.render("Bank", True, (238, 238, 238)), (panel_x + 10, y))
        y += 24
        bank_counts = self._bank_counts(state)
        card_width = 58
        card_gap = 6
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            x = panel_x + 10 + idx * (card_width + card_gap)
            self._draw_resource_card(screen, x, y, card_width, 72, resource, bank_counts[resource], compact=True)

        y += 84
        screen.blit(self.font.render("Players", True, (238, 238, 238)), (panel_x + 10, y))
        y += 24
        for pid in sorted(state.players):
            p = state.players[pid]
            hand_size = sum(p.resources.values())
            row = self.pg.Rect(panel_x + 8, y, panel_width - 16, 24)
            self.pg.draw.rect(screen, (50, 50, 60), row, border_radius=4)
            screen.blit(self.small_font.render(f"P{pid}", True, self._player_color(pid)), (row.x + 8, row.y + 4))
            screen.blit(self.small_font.render(f"VP {p.victory_points}", True, (220, 220, 220)), (row.x + 46, row.y + 4))
            screen.blit(self.small_font.render(f"Cards {hand_size}", True, (220, 220, 220)), (row.right - 88, row.y + 4))
            y += 28

        roll_rect = self.pg.Rect(0, 0, 0, 0)
        end_rect = self.pg.Rect(0, 0, 0, 0)
        action_button_rects = {
            "trade": self.pg.Rect(0, 0, 0, 0),
            "dev": self.pg.Rect(0, 0, 0, 0),
            "road": self.pg.Rect(0, 0, 0, 0),
            "settlement": self.pg.Rect(0, 0, 0, 0),
            "city": self.pg.Rect(0, 0, 0, 0),
            "primary": self.pg.Rect(0, 0, 0, 0),
            "bank_trade": self.pg.Rect(0, 0, 0, 0),
            "player_trade": self.pg.Rect(0, 0, 0, 0),
            "trade_cancel": self.pg.Rect(0, 0, 0, 0),
        }
        return roll_rect, end_rect, action_button_rects, up_rect, down_rect

    def _draw_bottom_bar(self, screen, state: GameState, active_player: int | None, legal_actions, width: int, height: int, panel_x: int, bottom_h: int, action_button_rects: dict[str, object], trade_ui: dict[str, object] | None) -> None:
        bar_y = height - bottom_h
        self.pg.draw.rect(screen, (34, 34, 40), (0, bar_y, panel_x, bottom_h))
        if active_player is None:
            return
        player = state.players[active_player]
        start_x = 16
        card_w = 78
        card_h = 84
        gap = 10
        resources = [ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]
        offered = trade_ui.get("offer", {}) if trade_ui else {}
        for idx, resource in enumerate(resources):
            x = start_x + idx * (card_w + gap)
            shown_amount = max(player.resources.get(resource, 0) - int(offered.get(resource, 0)), 0)
            self._draw_resource_card(screen, x, bar_y + 44, card_w, card_h, resource, shown_amount)
        labels = [("Trade", "trade"), ("Buy Dev Card", "dev"), ("Buy Road", "road"), ("Buy Settlement", "settlement"), ("Buy City", "city")]
        bx = start_x + 5 * (card_w + gap) + 18
        by = bar_y + 10
        bw = 112
        bh = 30
        for idx, (label, key) in enumerate(labels):
            rect = self.pg.Rect(bx + idx * (bw + 8), by, bw, bh)
            enabled = self._is_action_enabled(key, legal_actions, state, active_player)
            self.pg.draw.rect(screen, (78, 110, 95) if enabled else (70, 70, 72), rect, border_radius=5)
            screen.blit(self.small_font.render(label, True, (245, 245, 245)), (rect.x + 10, rect.y + 8))
            action_button_rects[key] = rect
        can_roll = any(isinstance(a, RollDice) for a in legal_actions)
        can_end = any(isinstance(a, EndTurn) for a in legal_actions)
        primary_label = primary_turn_button_state(can_roll=can_roll, can_end=can_end)
        primary_enabled = can_roll or can_end
        p_rect = self.pg.Rect(bx, by + bh + 10, 170, 34)
        self.pg.draw.rect(screen, (86, 112, 150) if primary_enabled else (72, 72, 74), p_rect, border_radius=6)
        screen.blit(self.small_font.render(primary_label, True, (250, 250, 250)), (p_rect.x + 18, p_rect.y + 9))
        action_button_rects["primary"] = p_rect

    def _draw_trade_overlay(self, screen, state: GameState, active_player: int | None, panel_x: int, height: int, bottom_h: int, trade_ui: dict[str, object]) -> None:
        if active_player is None:
            return
        overlay_h = max(int(bottom_h * 0.72), 118)
        y = height - bottom_h - overlay_h - 8
        self.pg.draw.rect(screen, (45, 45, 52), (10, y, panel_x - 20, overlay_h), border_radius=8)
        screen.blit(self.font.render("Trade Draft", True, (240, 240, 240)), (24, y + 10))
        req = trade_ui.get("request", {})
        offer = trade_ui.get("offer", {})
        valid = trade_ui.get("valid_bank_trade", False)
        status = "Valid bank trade" if valid else "Invalid bank trade"
        screen.blit(self.small_font.render(status, True, (120, 220, 120) if valid else (220, 140, 140)), (24, y + 34))
        rx = 24
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(rx + idx * 72, y + 52, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(req.get(resource, 0)), compact=True)
            trade_ui["request_rects"][resource] = rect
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(rx + idx * 72, y + 102, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(offer.get(resource, 0)), compact=True)
            trade_ui["offer_rects"][resource] = rect
        right_x = panel_x - 190
        trade_ui["bank_button_rect"] = self.pg.Rect(right_x, y + 46, 160, 30)
        trade_ui["player_button_rect"] = self.pg.Rect(right_x, y + 82, 160, 30)
        trade_ui["cancel_button_rect"] = self.pg.Rect(right_x, y + 118, 160, 30)
        self.pg.draw.rect(screen, (78, 110, 95) if valid else (70, 70, 72), trade_ui["bank_button_rect"], border_radius=4)
        self.pg.draw.rect(screen, (70, 70, 72), trade_ui["player_button_rect"], border_radius=4)
        self.pg.draw.rect(screen, (92, 70, 70), trade_ui["cancel_button_rect"], border_radius=4)
        screen.blit(self.small_font.render("Bank Trade", True, (250, 250, 250)), (right_x + 40, y + 53))
        screen.blit(self.small_font.render("Player Trade", True, (190, 190, 190)), (right_x + 36, y + 89))
        screen.blit(self.small_font.render("Cancel", True, (250, 250, 250)), (right_x + 57, y + 125))

    def _draw_resource_card(self, screen, x: int, y: int, width: int, height: int, resource: ResourceType, amount: int, *, compact: bool = False) -> None:
        color = {
            ResourceType.BRICK: (186, 100, 90),
            ResourceType.LUMBER: (92, 140, 92),
            ResourceType.GRAIN: (210, 190, 102),
            ResourceType.ORE: (130, 130, 140),
            ResourceType.WOOL: (160, 200, 130),
        }[resource]
        self.pg.draw.rect(screen, color, (x, y, width, height), border_radius=6)
        self.pg.draw.rect(screen, (32, 32, 32), (x, y, width, height), width=2, border_radius=6)
        text = self._resource_name(resource)
        font = self.small_font if compact else self.font
        text_surface = font.render(text, True, (24, 24, 24))
        screen.blit(text_surface, (x + 8, y + (9 if compact else 14)))
        count_rect = self.pg.Rect(x + width - 24, y + 4, 20, 18)
        self.pg.draw.rect(screen, (245, 245, 245), count_rect, border_radius=4)
        screen.blit(self.small_font.render(str(amount), True, (30, 30, 30)), (count_rect.x + 6, count_rect.y + 2))

    def _bank_counts(self, state: GameState) -> dict[ResourceType, int]:
        counts = {resource: 19 for resource in ResourceType}
        for player in state.players.values():
            for resource in ResourceType:
                counts[resource] -= player.resources.get(resource, 0)
        return counts

    def _is_action_enabled(self, key: str, legal_actions, state: GameState, active_player: int | None) -> bool:
        if key == "trade":
            return any(isinstance(a, BankTrade) for a in legal_actions)
        if key == "road":
            return any(isinstance(a, BuildRoad) for a in legal_actions)
        if key == "settlement":
            return any(isinstance(a, BuildSettlement) for a in legal_actions)
        if key == "city":
            return any(isinstance(a, BuildCity) for a in legal_actions)
        if key == "dev":
            if active_player is None:
                return False
            player = state.players[active_player]
            return (
                player.resources.get(ResourceType.ORE, 0) >= 1
                and player.resources.get(ResourceType.GRAIN, 0) >= 1
                and player.resources.get(ResourceType.WOOL, 0) >= 1
            )
        return False

    def _summarize_legal(self, legal_actions):
        counts: dict[str, int] = {}
        for action in legal_actions:
            name = type(action).__name__
            counts[name] = counts.get(name, 0) + 1
        return [f"{name}: {count}" for name, count in sorted(counts.items())] or ["none"]

    def _draw_ports(self, screen, state: GameState, layout: BoardLayout) -> None:
        for port in state.board.ports:
            if port.edge_id not in layout.edge_midpoints:
                continue
            mx, my = layout.edge_midpoints[port.edge_id]
            node_a, node_b = port.node_ids
            ax, ay = layout.node_positions[node_a]
            bx, by = layout.node_positions[node_b]
            dx = mx - (ax + bx) / 2
            dy = my - (ay + by) / 2
            label_x = int(mx + dx * 1.6)
            label_y = int(my + dy * 1.6)
            label = "3:1" if port.trade_resource is None else f"2:1 {self._resource_name(port.trade_resource)}"
            self.pg.draw.circle(screen, (30, 30, 30), (label_x, label_y), 16)
            self.pg.draw.circle(screen, (235, 235, 180), (label_x, label_y), 15)
            text = self.small_font.render(label, True, (20, 20, 20))
            screen.blit(text, (label_x - text.get_width() // 2, label_y - text.get_height() // 2))

    def _player_port_labels(self, state: GameState, player_id: int) -> list[str]:
        port_ids: set[int] = set()
        for node_id, owner in state.placed.settlements.items():
            if owner == player_id:
                port_ids.update(state.board.node_to_ports.get(node_id, ()))
        for node_id, owner in state.placed.cities.items():
            if owner == player_id:
                port_ids.update(state.board.node_to_ports.get(node_id, ()))
        labels: list[str] = []
        for port_id in sorted(port_ids):
            port = state.board.ports[port_id]
            labels.append("3:1" if port.trade_resource is None else f"2:1 {self._resource_name(port.trade_resource)}")
        return labels

    def _trade_rate_summaries(self, legal_actions) -> list[str]:
        offers: dict[ResourceType, int] = {}
        for action in legal_actions:
            if isinstance(action, BankTrade):
                current = offers.get(action.offer_resource)
                if current is None or action.trade_rate < current:
                    offers[action.offer_resource] = action.trade_rate
        return [f"{self._resource_name(resource)} {rate}:1" for resource, rate in sorted(offers.items(), key=lambda x: x[0].name)]

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
