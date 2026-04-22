from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from catan.core.models.action import BuildCity, BuildRoad, BuildSettlement, EndTurn, PlaceSetupRoad, PlaceSetupSettlement, RollDice

from .layout import BoardLayout


@dataclass(frozen=True)
class InputResult:
    action: object | None
    status: str | None = None


@dataclass(frozen=True)
class HoverTarget:
    node_id: int | None = None
    edge_id: int | None = None


class PygameInputMapper:
    def __init__(self, pygame_module) -> None:
        self.pg = pygame_module

    def map_event(self, event, legal_actions: Iterable[object], layout: BoardLayout, roll_rect, end_rect) -> InputResult:
        legal = list(legal_actions)
        if event.type == self.pg.KEYDOWN:
            if event.key == self.pg.K_r:
                return InputResult(action=self._find_singleton(legal, RollDice), status="hotkey R")
            if event.key == self.pg.K_e:
                return InputResult(action=self._find_singleton(legal, EndTurn), status="hotkey E")

        if event.type != self.pg.MOUSEBUTTONDOWN or event.button != 1:
            return InputResult(action=None)

        mouse = event.pos
        if roll_rect.collidepoint(mouse):
            return InputResult(action=self._find_singleton(legal, RollDice), status="clicked Roll")
        if end_rect.collidepoint(mouse):
            return InputResult(action=self._find_singleton(legal, EndTurn), status="clicked End")

        node_id = self._nearest_node(mouse, layout, radius=22)
        edge_id = self._nearest_edge(mouse, layout, radius=18)

        if node_id is not None:
            action = self._find_node_action(legal, node_id)
            if action is not None:
                return InputResult(action=action, status=f"clicked node {node_id}")

        if edge_id is not None:
            action = self._find_edge_action(legal, edge_id)
            if action is not None:
                return InputResult(action=action, status=f"clicked edge {edge_id}")

        return InputResult(action=None)

    def get_hover_target(self, mouse_pos: tuple[int, int], layout: BoardLayout) -> HoverTarget:
        return HoverTarget(
            node_id=self._nearest_node(mouse_pos, layout, radius=24),
            edge_id=self._nearest_edge(mouse_pos, layout, radius=20),
        )

    def _find_singleton(self, legal: list[object], action_type: type) -> object | None:
        for action in legal:
            if isinstance(action, action_type):
                return action
        return None

    def _find_node_action(self, legal: list[object], node_id: int) -> object | None:
        node_types = (PlaceSetupSettlement, BuildSettlement, BuildCity)
        for action in legal:
            if isinstance(action, node_types) and action.node_id == node_id:
                return action
        return None

    def _find_edge_action(self, legal: list[object], edge_id: int) -> object | None:
        edge_types = (PlaceSetupRoad, BuildRoad)
        for action in legal:
            if isinstance(action, edge_types) and action.edge_id == edge_id:
                return action
        return None

    def _nearest_node(self, mouse, layout: BoardLayout, radius: int = 18):
        mx, my = mouse
        best = None
        best_dist2 = radius * radius
        for node_id, (x, y) in layout.node_positions.items():
            d2 = (mx - x) ** 2 + (my - y) ** 2
            if d2 <= best_dist2:
                best = node_id
                best_dist2 = d2
        return best

    def _nearest_edge(self, mouse, layout: BoardLayout, radius: int = 14):
        mx, my = mouse
        best = None
        best_dist2 = radius * radius
        for edge_id, (x, y) in layout.edge_midpoints.items():
            d2 = (mx - x) ** 2 + (my - y) ** 2
            if d2 <= best_dist2:
                best = edge_id
                best_dist2 = d2
        return best
