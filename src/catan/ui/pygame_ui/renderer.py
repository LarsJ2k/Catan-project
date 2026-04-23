from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.action import (
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    EndTurn,
    FinishRoadBuildingCard,
    MoveRobber,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
    RollDice,
    StealResource,
)
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState

from .input_mapper import HoverTarget
from .layout import BoardLayout


@dataclass
class DrawnUi:
    roll_button_rect: object
    end_turn_button_rect: object
    action_button_rects: dict[str, object]
    dev_card_rects: dict[DevelopmentCardType, object]
    event_log_scroll_up_rect: object | None
    event_log_scroll_down_rect: object | None
    speed_button_rects: dict[float, object]


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
        discard_ui: dict[str, object] | None,
        dev_card_ui: dict[str, object] | None = None,
        event_log_offset: int = 0,
        hand_view_player: int | None = None,
        spectator_mode: bool = False,
        spectator_data: dict[str, object] | None = None,
    ) -> DrawnUi:
        legal_nodes, legal_edges, legal_tiles, steal_nodes, can_roll, can_end = extract_legal_targets(
            state, legal_actions, build_mode=build_mode
        )
        width, height = screen.get_size()
        panel_width = max(int(width * 0.24), 320)
        bottom_bar_height = max(int(height * (0.30 if spectator_mode else 0.18)), 130)
        panel_x = width - panel_width

        self.pg.draw.rect(screen, (28, 28, 32), (0, 0, width, height))
        self._draw_phase_banner(screen, state, width=width, panel_x=panel_x, fullscreen=fullscreen, bottom_bar_height=bottom_bar_height)
        self._draw_tiles(screen, state, layout, legal_tiles, hover_target.tile_id)
        self._draw_board(screen, state, layout, legal_nodes, legal_edges, steal_nodes, hover_target)
        self._draw_ports(screen, state, layout)
        roll_rect, end_rect, action_button_rects, scroll_up_rect, scroll_down_rect, speed_button_rects = self._draw_side_panel(
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
            spectator_mode=spectator_mode,
            spectator_data=spectator_data or {},
        )
        hand_player = active_player if hand_view_player is None else hand_view_player
        if spectator_mode:
            dev_card_rects = self._draw_spectator_dashboard(screen, state, active_player, panel_x, height, bottom_bar_height)
        else:
            dev_card_rects = self._draw_bottom_bar(
                screen, state, hand_player, width, height, panel_x, bottom_bar_height, trade_ui, discard_ui, legal_actions
            )
            self._draw_dice_button_in_board_area(
                screen,
                state,
                panel_x=panel_x,
                height=height,
                bottom_h=bottom_bar_height,
                can_roll=can_roll,
                action_button_rects=action_button_rects,
            )
        if trade_ui:
            self._draw_trade_overlay(screen, state, active_player, panel_x, height, bottom_bar_height, trade_ui)
        if discard_ui:
            self._draw_discard_overlay(screen, state, active_player, panel_x, height, bottom_bar_height, discard_ui)
        if dev_card_ui:
            self._draw_dev_card_overlay(screen, state, active_player, panel_x, height, bottom_bar_height, dev_card_ui)
        if state.phase == GamePhase.GAME_OVER and state.winner is not None:
            self._draw_game_over_overlay(screen, state.winner)
        return DrawnUi(
            roll_button_rect=roll_rect,
            end_turn_button_rect=end_rect,
            action_button_rects=action_button_rects,
            dev_card_rects=dev_card_rects,
            event_log_scroll_up_rect=scroll_up_rect,
            event_log_scroll_down_rect=scroll_down_rect,
            speed_button_rects=speed_button_rects,
        )

    def _draw_phase_banner(self, screen, state: GameState, *, width: int, panel_x: int, fullscreen: bool, bottom_bar_height: int) -> None:
        color, label = self._phase_banner_config(state)
        board_width = max(panel_x - 40, 200)
        board_height_limit = max(40, bottom_bar_height // 8)
        self.pg.draw.rect(screen, color, (20, 20, board_width, 30), border_radius=6)
        screen.blit(self.font.render(label, True, (255, 255, 255)), (30, 26))
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
        spectator_mode: bool = False,
        spectator_data: dict[str, object] | None = None,
    ):
        self.pg.draw.rect(screen, (38, 38, 44), (panel_x, 0, panel_width, height))
        y = 12
        screen.blit(self.font.render("Event log", True, (238, 238, 238)), (panel_x + 10, y))
        # Keep the event-log controls clear of the global settings button at the top-right.
        up_rect = self.pg.Rect(panel_x + panel_width - 112, y - 2, 22, 20)
        down_rect = self.pg.Rect(panel_x + panel_width - 86, y - 2, 22, 20)
        self.pg.draw.rect(screen, (60, 60, 70), up_rect, border_radius=3)
        self.pg.draw.rect(screen, (60, 60, 70), down_rect, border_radius=3)
        self._draw_triangle_icon(screen, up_rect, direction="up", color=(230, 230, 230))
        self._draw_triangle_icon(screen, down_rect, direction="down", color=(230, 230, 230))
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
        speed_button_rects: dict[float, object] = {}
        if spectator_mode:
            speed_label_y = y
            screen.blit(self.font.render("Speed", True, (238, 238, 238)), (panel_x + 10, speed_label_y))
            y += 24
            speed_options = [0.0, 1.0, 2.0, 4.0]
            active_speed = float((spectator_data or {}).get("speed", 1.0))
            button_w = (panel_width - 26) // 4
            labels = {0.0: "Pause", 1.0: "1x", 2.0: "2x", 4.0: "4x"}
            for idx, speed in enumerate(speed_options):
                rect = self.pg.Rect(panel_x + 10 + idx * (button_w + 2), y, button_w, 28)
                is_active = speed == active_speed
                self.pg.draw.rect(screen, (86, 112, 150) if is_active else (70, 70, 72), rect, border_radius=5)
                screen.blit(self.small_font.render(labels[speed], True, (245, 245, 245)), (rect.x + 10, rect.y + 7))
                speed_button_rects[speed] = rect
            y += 38
        screen.blit(self.font.render("Bank", True, (238, 238, 238)), (panel_x + 10, y))
        y += 24
        bank_counts = self._bank_counts(state)
        card_width = 58
        card_gap = 6
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            x = panel_x + 10 + idx * (card_width + card_gap)
            self._draw_resource_card(screen, x, y, card_width, 72, resource, bank_counts[resource], compact=True)
        dev_card_x = panel_x + 10 + 5 * (card_width + card_gap)
        self._draw_dev_deck_remaining_card(screen, dev_card_x, y, card_width, 72, len(state.dev_deck))

        y += 84
        screen.blit(self.font.render("Players", True, (238, 238, 238)), (panel_x + 10, y))
        y += 24
        for pid in sorted(state.players):
            p = state.players[pid]
            hand_size = sum(p.resources.values())
            dev_count = sum(p.dev_cards.values())
            row = self.pg.Rect(panel_x + 8, y, panel_width - 16, 24)
            self.pg.draw.rect(screen, (50, 50, 60), row, border_radius=4)
            screen.blit(self.small_font.render(f"P{pid}", True, self._player_color(pid)), (row.x + 8, row.y + 4))
            vp_text = self._scoreboard_vp_text(state, player_id=pid)
            screen.blit(self.small_font.render(vp_text, True, (220, 220, 220)), (row.x + 46, row.y + 4))
            screen.blit(self.small_font.render(f"Cards {hand_size}", True, (220, 220, 220)), (row.x + 112, row.y + 4))
            knight_color = (120, 220, 120) if state.largest_army_holder == pid else (220, 220, 220)
            road_color = (120, 220, 120) if state.longest_road_holder == pid else (220, 220, 220)
            screen.blit(self.small_font.render(f"K {p.knights_played}", True, knight_color), (row.x + 184, row.y + 4))
            screen.blit(self.small_font.render(f"R {p.longest_road_length}", True, road_color), (row.x + 228, row.y + 4))
            screen.blit(self.small_font.render(f"Dev {dev_count}", True, (220, 220, 220)), (row.right - 54, row.y + 4))
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
        if spectator_mode:
            self._draw_decision_panel(
                screen,
                panel_x=panel_x,
                panel_width=panel_width,
                height=height,
                spectator_data=spectator_data or {},
            )
        else:
            self._draw_sidebar_buttons(screen, state, legal_actions, can_roll, can_end, panel_x, panel_width, height, action_button_rects)
        return roll_rect, end_rect, action_button_rects, up_rect, down_rect, speed_button_rects

    def _draw_decision_panel(self, screen, *, panel_x: int, panel_width: int, height: int, spectator_data: dict[str, object]) -> None:
        panel_h = 140
        rect = self.pg.Rect(panel_x + 8, height - panel_h - 8, panel_width - 16, panel_h)
        self.pg.draw.rect(screen, (46, 46, 54), rect, border_radius=8)
        self.pg.draw.rect(screen, (78, 78, 88), rect, width=1, border_radius=8)
        screen.blit(self.font.render("Bot decision", True, (238, 238, 238)), (rect.x + 10, rect.y + 10))
        chosen = spectator_data.get("chosen_line")
        if isinstance(chosen, str):
            screen.blit(self.small_font.render(f"✓ {chosen[:40]}", True, (150, 225, 150)), (rect.x + 10, rect.y + 38))
        lines = spectator_data.get("candidate_lines", [])
        if isinstance(lines, list):
            for idx, line in enumerate(lines[:2]):
                screen.blit(self.small_font.render(f"{idx + 1}. {str(line)[:42]}", True, (215, 215, 215)), (rect.x + 10, rect.y + 60 + idx * 20))
        fallback = spectator_data.get("fallback_message")
        if isinstance(fallback, str):
            screen.blit(self.small_font.render(fallback[:46], True, (215, 215, 215)), (rect.x + 10, rect.y + 102))

    def _draw_spectator_dashboard(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        panel_x: int,
        height: int,
        bottom_h: int,
    ) -> dict[DevelopmentCardType, object]:
        bar_y = height - bottom_h
        self.pg.draw.rect(screen, (34, 34, 40), (0, bar_y, panel_x, bottom_h))
        self.pg.draw.line(screen, (70, 70, 75), (0, bar_y), (panel_x, bar_y), 1)
        players = sorted(state.players)
        if not players:
            return {}
        cols = 4
        rows = 2
        left_pad = 10
        top_pad = 10
        row_gap = 10
        card_gap = 6
        cell_w = max((panel_x - left_pad * 2 - (cols - 1) * card_gap) // cols, 70)
        cell_h = max((bottom_h - top_pad * 2 - row_gap) // rows, 56)
        resources = [ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]
        dev_types = [DevelopmentCardType.KNIGHT, DevelopmentCardType.ROAD_BUILDING, DevelopmentCardType.YEAR_OF_PLENTY, DevelopmentCardType.MONOPOLY, DevelopmentCardType.VICTORY_POINT]
        for idx, player_id in enumerate(players[:4]):
            base_col = 0 if idx in (0, 2) else 2
            row = 0 if idx < 2 else 1
            y = bar_y + top_pad + row * (cell_h + row_gap)
            px = left_pad + base_col * (cell_w + card_gap)
            dx = left_pad + (base_col + 1) * (cell_w + card_gap)
            for x, title, bg in (
                (px, f"P{player_id} Resources", (48, 48, 58)),
                (dx, f"P{player_id} Dev", (44, 44, 54)),
            ):
                rect = self.pg.Rect(x, y, cell_w, cell_h)
                border = self._player_color(player_id) if player_id == active_player else (84, 84, 98)
                self.pg.draw.rect(screen, bg, rect, border_radius=6)
                self.pg.draw.rect(screen, border, rect, width=3 if player_id == active_player else 1, border_radius=6)
                screen.blit(self.small_font.render(title, True, (230, 230, 236)), (rect.x + 4, rect.y + 4))
            player = state.players[player_id]
            row_y = y + 22
            for card_idx, resource in enumerate(resources):
                card_x = px + 3 + card_idx * ((cell_w - 10) // 5)
                amount = player.resources.get(resource, 0)
                self._draw_resource_card(screen, card_x, row_y, 18, 28, resource, amount, compact=True)
            for card_idx, card_type in enumerate(dev_types):
                card_x = dx + 3 + card_idx * ((cell_w - 10) // 5)
                amount = player.dev_cards.get(card_type, 0)
                self.pg.draw.rect(screen, (78, 88, 112), (card_x, row_y, 18, 28), border_radius=3)
                if amount > 0:
                    screen.blit(self.small_font.render(str(amount), True, (245, 245, 245)), (card_x + 4, row_y + 7))
        return {}

    def _draw_triangle_icon(self, screen, rect, *, direction: str, color: tuple[int, int, int]) -> None:
        cx, cy = rect.centerx, rect.centery
        if direction == "up":
            points = [(cx, cy - 4), (cx - 5, cy + 3), (cx + 5, cy + 3)]
        else:
            points = [(cx - 5, cy - 3), (cx + 5, cy - 3), (cx, cy + 4)]
        self.pg.draw.polygon(screen, color, points)

    def _draw_bottom_bar(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        width: int,
        height: int,
        panel_x: int,
        bottom_h: int,
        trade_ui: dict[str, object] | None,
        discard_ui: dict[str, object] | None,
        legal_actions: Iterable[object],
    ) -> dict[DevelopmentCardType, object]:
        bar_y = height - bottom_h
        self.pg.draw.rect(screen, (34, 34, 40), (0, bar_y, panel_x, bottom_h))
        if active_player is None:
            return {}
        player = state.players[active_player]
        start_x = 16
        card_w = 78
        card_h = 94
        gap = 10
        resources = [ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]
        offered = trade_ui.get("offer", {}) if trade_ui else {}
        discard_selected = discard_ui.get("selected", {}) if discard_ui else {}
        trade_hand_rects = trade_ui.setdefault("hand_rects", {}) if trade_ui is not None else None
        discard_hand_rects = discard_ui.setdefault("hand_rects", {}) if discard_ui is not None else None
        for idx, resource in enumerate(resources):
            x = start_x + idx * (card_w + gap)
            shown_amount = max(
                player.resources.get(resource, 0)
                - int(offered.get(resource, 0))
                - int(discard_selected.get(resource, 0)),
                0,
            )
            self._draw_resource_card(screen, x, bar_y + 34, card_w, card_h, resource, shown_amount)
            if trade_hand_rects is not None:
                trade_hand_rects[resource] = self.pg.Rect(x, bar_y + 34, card_w, card_h)
            if discard_hand_rects is not None:
                discard_hand_rects[resource] = self.pg.Rect(x, bar_y + 34, card_w, card_h)
        return self._draw_dev_card_panel(
            screen,
            state,
            active_player,
            start_x + 5 * (card_w + gap) + 18,
            bar_y + 34,
            legal_actions,
        )

    def _draw_dev_card_panel(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        start_x: int,
        start_y: int,
        legal_actions: Iterable[object],
    ) -> dict[DevelopmentCardType, object]:
        if active_player is None:
            return {}
        player = state.players[active_player]
        card_w = 78
        card_h = 94
        gap = 10
        screen.blit(self.small_font.render("Dev cards", True, (236, 236, 236)), (start_x, start_y - 20))
        visible_card_types = [card_type for card_type, count in player.dev_cards.items() if count > 0]
        knight_playable = any(isinstance(action, PlayKnightCard) for action in legal_actions)
        road_playable = any(isinstance(action, PlayRoadBuildingCard) for action in legal_actions)
        yop_playable = any(isinstance(action, PlayYearOfPlentyCard) for action in legal_actions)
        monopoly_playable = any(isinstance(action, PlayMonopolyCard) for action in legal_actions)
        clickable_rects: dict[DevelopmentCardType, object] = {}
        for idx, card_type in enumerate(visible_card_types):
            x = start_x + idx * (card_w + gap)
            rect = self.pg.Rect(x, start_y, card_w, card_h)
            count = player.dev_cards.get(card_type, 0)
            is_playable = (
                (card_type == DevelopmentCardType.KNIGHT and knight_playable)
                or (card_type == DevelopmentCardType.ROAD_BUILDING and road_playable)
                or (card_type == DevelopmentCardType.YEAR_OF_PLENTY and yop_playable)
                or (card_type == DevelopmentCardType.MONOPOLY and monopoly_playable)
            )
            is_disabled = card_type in (
                DevelopmentCardType.KNIGHT,
                DevelopmentCardType.ROAD_BUILDING,
                DevelopmentCardType.YEAR_OF_PLENTY,
                DevelopmentCardType.MONOPOLY,
            ) and not is_playable
            face_color = (84, 92, 120) if not is_disabled else (62, 62, 70)
            border_color = (120, 220, 120) if is_playable else (138, 145, 176)
            self.pg.draw.rect(screen, face_color, rect, border_radius=6)
            self.pg.draw.rect(screen, border_color, rect, width=3 if is_playable else 2, border_radius=6)
            label = self._dev_card_name(card_type)
            label_surface = self.small_font.render(label, True, (235, 235, 240) if not is_disabled else (182, 182, 182))
            screen.blit(label_surface, (x + 8, start_y + 12))
            count_rect = self.pg.Rect(rect.right - 24, rect.y + 4, 20, 18)
            self.pg.draw.rect(screen, (245, 245, 245), count_rect, border_radius=4)
            screen.blit(self.small_font.render(str(count), True, (24, 24, 24)), (count_rect.x + 6, count_rect.y + 2))
            if is_playable:
                screen.blit(self.small_font.render("Play", True, (120, 220, 120)), (x + 8, start_y + 66))
                clickable_rects[card_type] = rect
            elif is_disabled:
                screen.blit(self.small_font.render("New", True, (150, 150, 150)), (x + 8, start_y + 66))
        return clickable_rects

    def _draw_dice_button(self, screen, x: int, y: int, can_roll: bool, action_button_rects: dict[str, object], state: GameState) -> None:
        dice_rect = self.pg.Rect(x, y, 88, 72)
        self.pg.draw.rect(screen, (95, 118, 155) if can_roll else (72, 72, 74), dice_rect, border_radius=8)
        die_w = 34
        die_h = 34
        die_1 = self.pg.Rect(dice_rect.x + 8, dice_rect.y + 19, die_w, die_h)
        die_2 = self.pg.Rect(dice_rect.x + 46, dice_rect.y + 19, die_w, die_h)
        self.pg.draw.rect(screen, (245, 245, 245), die_1, border_radius=6)
        self.pg.draw.rect(screen, (245, 245, 245), die_2, border_radius=6)
        roll = state.turn.last_roll if state.turn and state.turn.last_roll is not None else (1, 1)
        self._draw_die_pips(screen, die_1, roll[0])
        self._draw_die_pips(screen, die_2, roll[1])
        action_button_rects["dice"] = dice_rect

    def _draw_dice_button_in_board_area(
        self,
        screen,
        state: GameState,
        *,
        panel_x: int,
        height: int,
        bottom_h: int,
        can_roll: bool,
        action_button_rects: dict[str, object],
    ) -> None:
        margin = 14
        x = panel_x - 88 - margin
        y = height - bottom_h - 72 - margin
        self._draw_dice_button(screen, x, y, can_roll, action_button_rects, state)

    def _draw_sidebar_buttons(
        self,
        screen,
        state: GameState,
        legal_actions,
        can_roll: bool,
        can_end: bool,
        panel_x: int,
        panel_width: int,
        height: int,
        action_button_rects: dict[str, object],
    ) -> None:
        labels = [("Trade", "trade"), ("Buy Dev", "dev"), ("Road", "road"), ("Settlement", "settlement"), ("City", "city")]
        button_h = 30
        button_gap = 6
        side_pad = 10
        dice_y = height - 84
        column_w = panel_width - 24 - 96
        right_x = panel_x + panel_width - side_pad - column_w
        for idx, (label, key) in enumerate(labels):
            rect = self.pg.Rect(right_x, dice_y - (len(labels) - idx) * (button_h + button_gap) - 8, column_w, button_h)
            enabled = self._is_action_enabled(key, legal_actions, state, state.turn.current_player if state.turn else None)
            self.pg.draw.rect(screen, (78, 110, 95) if enabled else (70, 70, 72), rect, border_radius=5)
            screen.blit(self.small_font.render(label, True, (245, 245, 245)), (rect.x + 10, rect.y + 8))
            action_button_rects[key] = rect
        primary_label = primary_turn_button_state(can_roll=can_roll, can_end=can_end)
        primary_enabled = can_roll or can_end
        primary_rect = self.pg.Rect(right_x, dice_y - 2, column_w, 30)
        self.pg.draw.rect(screen, (86, 112, 150) if primary_enabled else (72, 72, 74), primary_rect, border_radius=6)
        screen.blit(self.small_font.render(primary_label, True, (250, 250, 250)), (primary_rect.x + 10, primary_rect.y + 8))
        action_button_rects["primary"] = primary_rect

    def _draw_die_pips(self, screen, die_rect, value: int) -> None:
        cx, cy = die_rect.centerx, die_rect.centery
        left = die_rect.x + 10
        right = die_rect.right - 10
        top = die_rect.y + 10
        bottom = die_rect.bottom - 10
        mapping = {
            1: [(cx, cy)],
            2: [(left, top), (right, bottom)],
            3: [(left, top), (cx, cy), (right, bottom)],
            4: [(left, top), (right, top), (left, bottom), (right, bottom)],
            5: [(left, top), (right, top), (cx, cy), (left, bottom), (right, bottom)],
            6: [(left, top), (right, top), (left, cy), (right, cy), (left, bottom), (right, bottom)],
        }
        for pip in mapping.get(value, mapping[1]):
            self.pg.draw.circle(screen, (30, 30, 30), pip, 3)

    def _phase_banner_config(self, state: GameState) -> tuple[tuple[int, int, int], str]:
        if state.phase == GamePhase.GAME_OVER and state.winner is not None:
            return self._player_color(state.winner), f"Game over • P{state.winner} heeft gewonnen"
        active_player = self._active_player_for_banner(state)
        if active_player is None:
            return (120, 95, 40), "Speler onbekend"
        if state.turn is None:
            if state.setup.pending_settlement_player is not None:
                return self._player_color(active_player), f"Setup fase • P{active_player}: plaats een settlement"
            if state.setup.pending_road_player is not None:
                return self._player_color(active_player), f"Setup fase • P{active_player}: plaats een road"
            return self._player_color(active_player), f"Setup fase • P{active_player} aan zet"
        step_labels = {
            TurnStep.ROLL: f"P{active_player}: gooi de dobbelstenen",
            TurnStep.DISCARD: f"P{active_player}: kies kaarten om te discarden",
            TurnStep.ROBBER_MOVE: f"P{active_player}: zet de struikrover op een tile",
            TurnStep.ROBBER_STEAL: f"P{active_player}: kies een tegenstander om van te stelen",
            TurnStep.ACTIONS: f"P{active_player}: bouw, trade of eindig je beurt",
            TurnStep.PLAYER_TRADE: f"P{active_player}: reageer op trade",
            TurnStep.ROAD_BUILDING: f"P{active_player}: Road Building - plaats tot 2 roads",
            TurnStep.YEAR_OF_PLENTY: f"P{active_player}: Year of Plenty - kies 2 resources",
            TurnStep.MONOPOLY: f"P{active_player}: Monopoly - kies 1 resource",
        }
        return self._player_color(active_player), step_labels.get(state.turn.step, f"Speler P{active_player} aan zet")

    def _active_player_for_banner(self, state: GameState) -> int | None:
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player

    def _draw_trade_overlay(self, screen, state: GameState, active_player: int | None, panel_x: int, height: int, bottom_h: int, trade_ui: dict[str, object]) -> None:
        if active_player is None:
            return
        mode = trade_ui.get("mode", "draft")
        if mode != "draft":
            self._draw_player_trade_overlay(screen, panel_x, height, bottom_h, trade_ui)
            return
        overlay_h = max(int(bottom_h * 1.14), 220)
        y = height - bottom_h - overlay_h - 8
        self.pg.draw.rect(screen, (45, 45, 52), (10, y, panel_x - 20, overlay_h), border_radius=8)
        screen.blit(self.font.render("Trade Draft", True, (240, 240, 240)), (24, y + 10))
        req = trade_ui.get("request", {})
        offer = trade_ui.get("offer", {})
        valid = trade_ui.get("valid_bank_trade", False)
        status = "Valid bank trade" if valid else "Invalid bank trade"
        screen.blit(self.small_font.render(status, True, (120, 220, 120) if valid else (220, 140, 140)), (24, y + 34))
        rx = 24
        labels = [
            "Rij 1: Bank/Tegenstander (klik om toe te voegen)",
            "Rij 2: Trade opponent (klik om te verwijderen)",
            "Rij 3: Trade mijn kant (klik om terug te zetten)",
            "Rij 4: Mijn resources (onderste rij)",
        ]
        for idx, label in enumerate(labels):
            screen.blit(self.small_font.render(label, True, (214, 214, 214)), (24, y + 52 + idx * 50 - 14))
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(rx + idx * 72, y + 52, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, 99, compact=True)
            trade_ui["bank_supply_rects"][resource] = rect
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(rx + idx * 72, y + 102, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(req.get(resource, 0)), compact=True)
            trade_ui["request_rects"][resource] = rect
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(rx + idx * 72, y + 152, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(offer.get(resource, 0)), compact=True)
            trade_ui["offer_rects"][resource] = rect
        right_x = panel_x - 190
        trade_ui["bank_button_rect"] = self.pg.Rect(right_x, y + 46, 160, 30)
        trade_ui["player_button_rect"] = self.pg.Rect(right_x, y + 82, 160, 30)
        trade_ui["cancel_button_rect"] = self.pg.Rect(right_x, y + 118, 160, 30)
        self.pg.draw.rect(screen, (78, 110, 95) if valid else (70, 70, 72), trade_ui["bank_button_rect"], border_radius=4)
        self.pg.draw.rect(screen, (78, 110, 95) if trade_ui.get("valid_player_trade", False) else (70, 70, 72), trade_ui["player_button_rect"], border_radius=4)
        self.pg.draw.rect(screen, (92, 70, 70), trade_ui["cancel_button_rect"], border_radius=4)
        screen.blit(self.small_font.render("Bank Trade", True, (250, 250, 250)), (right_x + 40, y + 53))
        screen.blit(self.small_font.render("Player Trade", True, (190, 190, 190)), (right_x + 36, y + 89))
        screen.blit(self.small_font.render("Cancel", True, (250, 250, 250)), (right_x + 57, y + 125))

    def _draw_game_over_overlay(self, screen, winner_player_id: int) -> None:
        width, height = screen.get_size()
        overlay = self.pg.Surface((width, height), self.pg.SRCALPHA)
        overlay.fill((8, 8, 12, 145))
        screen.blit(overlay, (0, 0))

        panel_w = min(max(int(width * 0.46), 360), 700)
        panel_h = min(max(int(height * 0.22), 150), 260)
        panel_x = (width - panel_w) // 2
        panel_y = (height - panel_h) // 2
        self.pg.draw.rect(screen, (36, 36, 44), (panel_x, panel_y, panel_w, panel_h), border_radius=10)
        self.pg.draw.rect(screen, self._player_color(winner_player_id), (panel_x, panel_y, panel_w, panel_h), width=3, border_radius=10)

        title_font = self.pg.font.SysFont("arial", 30, bold=True)
        text_font = self.pg.font.SysFont("arial", 24)
        title = title_font.render("Spel afgelopen", True, (245, 245, 245))
        winner_text = text_font.render(f"Speler P{winner_player_id} heeft gewonnen!", True, (245, 245, 245))
        screen.blit(title, (panel_x + (panel_w - title.get_width()) // 2, panel_y + 30))
        screen.blit(winner_text, (panel_x + (panel_w - winner_text.get_width()) // 2, panel_y + 82))

    def _draw_player_trade_overlay(self, screen, panel_x: int, height: int, bottom_h: int, trade_ui: dict[str, object]) -> None:
        overlay_h = max(int(bottom_h * 0.92), 165)
        y = height - bottom_h - overlay_h - 8
        self.pg.draw.rect(screen, (45, 45, 52), (10, y, panel_x - 20, overlay_h), border_radius=8)
        offer = trade_ui.get("offer", {})
        request = trade_ui.get("request", {})
        offer_txt = ", ".join(f"{n} {self._resource_name(r)}" for r, n in offer.items() if n > 0)
        request_txt = ", ".join(f"{n} {self._resource_name(r)}" for r, n in request.items() if n > 0)
        screen.blit(self.font.render("Player Trade", True, (240, 240, 240)), (24, y + 10))
        screen.blit(self.small_font.render(f"Offer: {offer_txt}", True, (214, 214, 214)), (24, y + 42))
        screen.blit(self.small_font.render(f"Request: {request_txt}", True, (214, 214, 214)), (24, y + 62))

        if trade_ui.get("mode") == "response":
            responder = trade_ui.get("current_responder")
            screen.blit(self.small_font.render(f"Current responder: P{responder}", True, (214, 214, 214)), (24, y + 86))
            interested_rect = self.pg.Rect(24, y + 110, 170, 34)
            pass_rect = self.pg.Rect(204, y + 110, 170, 34)
            self.pg.draw.rect(screen, (78, 110, 95), interested_rect, border_radius=4)
            self.pg.draw.rect(screen, (90, 90, 94), pass_rect, border_radius=4)
            screen.blit(self.small_font.render("Interested", True, (245, 245, 245)), (65, y + 120))
            screen.blit(self.small_font.render("Pass", True, (245, 245, 245)), (267, y + 120))
            trade_ui["response_interested_rect"] = interested_rect
            trade_ui["response_pass_rect"] = pass_rect
            return

        screen.blit(self.small_font.render("Interested players:", True, (214, 214, 214)), (24, y + 86))
        y_cursor = y + 108
        for player_id in trade_ui.get("interested_responders", ()):
            rect = self.pg.Rect(24, y_cursor, 210, 28)
            self.pg.draw.rect(screen, (78, 110, 95), rect, border_radius=4)
            screen.blit(self.small_font.render(f"Trade with P{player_id}", True, (245, 245, 245)), (40, y_cursor + 8))
            trade_ui["selection_rects"][player_id] = rect
            y_cursor += 34
        reject_rect = self.pg.Rect(246, y + 108, 170, 30)
        self.pg.draw.rect(screen, (92, 70, 70), reject_rect, border_radius=4)
        screen.blit(self.small_font.render("Reject all", True, (250, 250, 250)), (293, y + 116))
        trade_ui["reject_all_rect"] = reject_rect

    def _draw_discard_overlay(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        panel_x: int,
        height: int,
        bottom_h: int,
        discard_ui: dict[str, object],
    ) -> None:
        if active_player is None:
            return
        required = int(discard_ui.get("required", 0))
        selected = discard_ui.get("selected", {})
        selected_total = sum(int(selected.get(resource, 0)) for resource in ResourceType)
        can_continue = selected_total == required
        overlay_h = max(int(bottom_h * 0.82), 120)
        y = height - bottom_h - overlay_h - 8
        self.pg.draw.rect(screen, (45, 45, 52), (10, y, panel_x - 20, overlay_h), border_radius=8)
        header = f"Kaarten discarden ({selected_total}/{required})"
        screen.blit(self.font.render(header, True, (240, 240, 240)), (24, y + 10))
        screen.blit(self.small_font.render("Klik kaart onder om toe te voegen, klik boven om te verwijderen.", True, (214, 214, 214)), (24, y + 36))

        start_x = 24
        for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
            rect = self.pg.Rect(start_x + idx * 72, y + 58, 66, 42)
            self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(selected.get(resource, 0)), compact=True)
            discard_ui["selected_rects"][resource] = rect

        right_x = panel_x - 190
        discard_ui["continue_button_rect"] = self.pg.Rect(right_x, y + 58, 160, 30)
        self.pg.draw.rect(screen, (86, 112, 150) if can_continue else (70, 70, 72), discard_ui["continue_button_rect"], border_radius=4)
        screen.blit(self.small_font.render("Doorgaan", True, (250, 250, 250)), (right_x + 50, y + 65))

    def _draw_dev_card_overlay(
        self,
        screen,
        state: GameState,
        active_player: int | None,
        panel_x: int,
        height: int,
        bottom_h: int,
        dev_card_ui: dict[str, object],
    ) -> None:
        if active_player is None:
            return
        mode = dev_card_ui.get("mode")
        overlay_h = max(int(bottom_h * 0.82), 120)
        y = height - bottom_h - overlay_h - 8
        self.pg.draw.rect(screen, (45, 45, 52), (10, y, panel_x - 20, overlay_h), border_radius=8)
        if mode == "year_of_plenty":
            selected = dev_card_ui.get("selected", {})
            total = sum(int(selected.get(resource, 0)) for resource in ResourceType)
            screen.blit(self.font.render(f"Year of Plenty ({total}/2)", True, (240, 240, 240)), (24, y + 10))
            screen.blit(self.small_font.render("Selecteer 2 resources.", True, (214, 214, 214)), (24, y + 36))
            start_x = 24
            for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
                rect = self.pg.Rect(start_x + idx * 72, y + 58, 66, 42)
                self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, int(selected.get(resource, 0)), compact=True)
                dev_card_ui["resource_rects"][resource] = rect
            right_x = panel_x - 190
            dev_card_ui["submit_rect"] = self.pg.Rect(right_x, y + 58, 160, 30)
            self.pg.draw.rect(screen, (86, 112, 150) if total == 2 else (70, 70, 72), dev_card_ui["submit_rect"], border_radius=4)
            screen.blit(self.small_font.render("Bevestig", True, (250, 250, 250)), (right_x + 52, y + 65))
            return

        if mode == "monopoly":
            screen.blit(self.font.render("Monopoly", True, (240, 240, 240)), (24, y + 10))
            screen.blit(self.small_font.render("Kies 1 resource type.", True, (214, 214, 214)), (24, y + 36))
            start_x = 24
            for idx, resource in enumerate([ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]):
                rect = self.pg.Rect(start_x + idx * 72, y + 58, 66, 42)
                self._draw_resource_card(screen, rect.x, rect.y, rect.width, rect.height, resource, 0, compact=True)
                dev_card_ui["resource_rects"][resource] = rect

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

    def _draw_dev_deck_remaining_card(self, screen, x: int, y: int, width: int, height: int, amount: int) -> None:
        self.pg.draw.rect(screen, (125, 88, 178), (x, y, width, height), border_radius=6)
        self.pg.draw.rect(screen, (32, 32, 32), (x, y, width, height), width=2, border_radius=6)
        qmark_surface = self.font.render("?", True, (245, 245, 245))
        screen.blit(qmark_surface, (x + (width - qmark_surface.get_width()) // 2, y + 20))
        dev_surface = self.small_font.render("dev", True, (245, 245, 245))
        screen.blit(dev_surface, (x + (width - dev_surface.get_width()) // 2, y + height - 20))
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
            return state.turn is not None and state.turn.step == TurnStep.ACTIONS and state.player_trade is None
        if key == "road":
            return any(isinstance(a, BuildRoad) for a in legal_actions)
        if key == "settlement":
            return any(isinstance(a, BuildSettlement) for a in legal_actions)
        if key == "city":
            return any(isinstance(a, BuildCity) for a in legal_actions)
        if key == "dev":
            return any(isinstance(a, BuyDevelopmentCard) for a in legal_actions)
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

    def _dev_card_name(self, card_type: DevelopmentCardType) -> str:
        names = {
            DevelopmentCardType.KNIGHT: "Knight",
            DevelopmentCardType.VICTORY_POINT: "VP",
            DevelopmentCardType.ROAD_BUILDING: "Road",
            DevelopmentCardType.YEAR_OF_PLENTY: "YOP",
            DevelopmentCardType.MONOPOLY: "Mono",
        }
        return names[card_type]

    def _scoreboard_vp_text(self, state: GameState, player_id: int) -> str:
        player = state.players[player_id]
        award_vp = 0
        if state.largest_army_holder == player_id:
            award_vp += 2
        if state.longest_road_holder == player_id:
            award_vp += 2
        public_vp = player.victory_points + award_vp
        if state.turn is not None and state.turn.current_player == player_id:
            hidden_vp = player.dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
            if hidden_vp > 0:
                return f"VP {public_vp}({public_vp + hidden_vp})"
        return f"VP {public_vp}"
