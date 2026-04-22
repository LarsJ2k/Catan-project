from __future__ import annotations

from typing import Mapping

from catan.controllers.human_controller import HumanController
from catan.core.engine import get_legal_actions
from catan.core.models.action import DiscardResources
from catan.core.models.enums import ResourceType, TurnStep
from catan.core.models.state import GameState
from catan.runners.local_pygame_runner import LocalPygameRunner

from .input_mapper import HoverTarget, PygameInputMapper
from .layout import build_circular_layout
from .renderer import PygameRenderer


class PygameApp:
    def __init__(self, pygame_module, *, width: int = 1200, height: int = 820) -> None:
        self.pg = pygame_module
        self.width = width
        self.height = height
        self.fullscreen = False
        self.runner = LocalPygameRunner()

    def run(self, initial_state: GameState, controllers: Mapping[int, HumanController]) -> GameState:
        self.pg.init()
        if hasattr(self.pg, "font"):
            self.pg.font.init()

        self.pg.display.set_caption("Catan MVP (Debug UI)")
        screen = self._create_display_surface()
        clock = self.pg.time.Clock()

        renderer = PygameRenderer(self.pg)
        input_mapper = PygameInputMapper(self.pg)

        state = initial_state
        event_log = ["[000] game started"]
        selected_action_text: str | None = None
        last_applied_action: str | None = None
        action_counter = 0
        discard_selection: dict[ResourceType, int] = {r: 0 for r in ResourceType}

        running = True
        while running:
            board_center, board_radius = self._board_center_and_radius(screen)
            layout = build_circular_layout(state.board, center=board_center, radius=board_radius)

            active_player = self._active_player(state)
            legal = get_legal_actions(state, active_player) if active_player is not None else []
            hover = input_mapper.get_hover_target(self.pg.mouse.get_pos(), layout) if hasattr(self.pg, "mouse") else HoverTarget()

            if state.turn and state.turn.step == TurnStep.DISCARD and active_player is not None:
                required = state.discard_requirements.get(active_player, 0)
                selected_action_text = f"Discard {required}: " + ", ".join(f"{r.name}:{n}" for r, n in discard_selection.items() if n > 0)

            drawn = renderer.render(
                screen,
                state,
                layout,
                legal,
                active_player,
                event_log,
                selected_action_text,
                hover,
                last_applied_action,
                self.fullscreen,
            )

            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    running = False
                    break
                if event.type == self.pg.KEYDOWN and event.key == self.pg.K_F11:
                    self.fullscreen = not self.fullscreen
                    screen = self._create_display_surface()
                    event_log.append(f"[{action_counter:03d}] display toggled {'Fullscreen' if self.fullscreen else 'Windowed'}")
                    continue
                if event.type == self.pg.VIDEORESIZE and not self.fullscreen:
                    self.width, self.height = event.w, event.h
                    screen = self._create_display_surface()
                    continue

                if active_player is None or active_player not in controllers:
                    continue

                if state.turn and state.turn.step == TurnStep.DISCARD:
                    discard_action = self._handle_discard_event(event, state, active_player, discard_selection)
                    if discard_action is not None:
                        selected_action_text = str(discard_action)
                        controllers[active_player].submit_action_intent(discard_action)
                    continue

                mapped = input_mapper.map_event(
                    event,
                    legal_actions=legal,
                    layout=layout,
                    roll_rect=drawn.roll_button_rect,
                    end_rect=drawn.end_turn_button_rect,
                    state=state,
                )
                if mapped.action is not None:
                    selected_action_text = str(mapped.action)
                    controllers[active_player].submit_action_intent(mapped.action)
                    if mapped.status:
                        event_log.append(f"[{action_counter:03d}] P{active_player} {mapped.status}")

            if active_player is not None and active_player in controllers:
                before = state
                state = self.runner.tick(state, controllers[active_player], active_player)
                if state != before:
                    action_counter += 1
                    last_applied_action = selected_action_text or "action"
                    for line in self._describe_transition(before, state, last_applied_action):
                        event_log.append(f"[{action_counter:03d}] {line}")
                    selected_action_text = None
                    if not (state.turn and state.turn.step == TurnStep.DISCARD):
                        discard_selection = {r: 0 for r in ResourceType}

            self.pg.display.flip()
            clock.tick(30)

        self.pg.quit()
        return state

    def _handle_discard_event(self, event, state: GameState, player_id: int, selection: dict[ResourceType, int]):
        if event.type != self.pg.KEYDOWN:
            return None
        mapping = {
            self.pg.K_1: ResourceType.GRAIN,
            self.pg.K_2: ResourceType.LUMBER,
            self.pg.K_3: ResourceType.BRICK,
            self.pg.K_4: ResourceType.ORE,
            self.pg.K_5: ResourceType.WOOL,
        }
        required = state.discard_requirements.get(player_id, 0)

        if event.key in mapping:
            resource = mapping[event.key]
            player_have = state.players[player_id].resources.get(resource, 0)
            if selection[resource] < player_have and sum(selection.values()) < required:
                selection[resource] += 1
            return None
        if event.key == self.pg.K_BACKSPACE:
            for resource in ResourceType:
                selection[resource] = 0
            return None
        if event.key in (self.pg.K_RETURN, self.pg.K_KP_ENTER):
            if sum(selection.values()) == required:
                resources = tuple((resource, amount) for resource, amount in selection.items() if amount > 0)
                return DiscardResources(player_id=player_id, resources=resources)
        return None

    def _create_display_surface(self):
        if self.fullscreen:
            info = self.pg.display.Info()
            self.width, self.height = info.current_w, info.current_h
            return self.pg.display.set_mode((self.width, self.height), self.pg.FULLSCREEN)
        return self.pg.display.set_mode((self.width, self.height), self.pg.RESIZABLE)

    def _board_center_and_radius(self, screen) -> tuple[tuple[int, int], int]:
        width, height = screen.get_size()
        panel_width = 320
        board_width = max(width - panel_width - 40, 200)
        board_height = max(height - 80, 200)
        center = (20 + board_width // 2, 70 + board_height // 2)
        radius = int(min(board_width, board_height) * 0.42)
        return center, max(radius, 120)

    def _describe_transition(self, before: GameState, after: GameState, action_text: str) -> list[str]:
        lines: list[str] = [f"applied {action_text}"]

        before_roll = before.turn.last_roll if before.turn else None
        after_roll = after.turn.last_roll if after.turn else None
        if after_roll is not None and after_roll != before_roll:
            total = after_roll[0] + after_roll[1]
            lines.append(f"Dice rolled {after_roll[0]} + {after_roll[1]} = {total}")

        if before.robber_tile_id != after.robber_tile_id:
            lines.append(f"Robber moved to tile {after.robber_tile_id}")
            if after.turn and after.turn.step == TurnStep.ROBBER_STEAL:
                lines.append("Select a victim to steal from")

        steals: list[tuple[int, int, ResourceType]] = []
        for pid in sorted(after.players.keys()):
            for resource in [ResourceType.GRAIN, ResourceType.LUMBER, ResourceType.BRICK, ResourceType.ORE, ResourceType.WOOL]:
                before_amount = before.players[pid].resources.get(resource, 0)
                after_amount = after.players[pid].resources.get(resource, 0)
                delta = after_amount - before_amount
                if delta > 0:
                    lines.append(f"P{pid} received {delta} {self._resource_name(resource)}")
                    if before.turn and before.turn.step in (TurnStep.ROBBER_MOVE, TurnStep.ROBBER_STEAL) and delta == 1:
                        victims = [other for other in sorted(after.players.keys()) if other != pid and before.players[other].resources.get(resource, 0) - after.players[other].resources.get(resource, 0) == 1]
                        if victims:
                            steals.append((pid, victims[0], resource))

        if before.turn and before.turn.step == TurnStep.ROBBER_MOVE and after.turn and after.turn.step == TurnStep.ACTIONS and before.robber_tile_id != after.robber_tile_id and not steals:
            lines.append("No eligible victim to steal from")
        for thief, victim, resource in steals:
            lines.append(f"P{thief} stole 1 {self._resource_name(resource)} from P{victim}")
        return lines

    def _resource_name(self, resource: ResourceType) -> str:
        names = {
            ResourceType.BRICK: "Brick",
            ResourceType.LUMBER: "Lumber",
            ResourceType.GRAIN: "Wheat",
            ResourceType.ORE: "Ore",
            ResourceType.WOOL: "Sheep",
        }
        return names[resource]

    def _active_player(self, state: GameState) -> int | None:
        if state.turn is not None and state.turn.priority_player is not None:
            return state.turn.priority_player
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player
