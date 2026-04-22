from __future__ import annotations

from typing import Mapping

from catan.controllers.human_controller import HumanController
from catan.core.engine import get_legal_actions
from catan.core.models.action import BankTrade, BuildCity, BuildRoad, BuildSettlement, DiscardResources, EndTurn, RollDice
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
        bank_trade_offer: ResourceType | None = None
        bank_trade_request: ResourceType | None = None
        event_log_offset = 0
        build_mode: str | None = None
        trade_draft_offered = {r: 0 for r in ResourceType}
        trade_draft_requested = {r: 0 for r in ResourceType}
        trade_window_open = False

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
            elif state.turn and state.turn.step == TurnStep.ACTIONS and trade_window_open:
                selected_action_text = self._trade_draft_status_text(trade_draft_offered, trade_draft_requested, legal, active_player)

            trade_ui = None
            if trade_window_open:
                trade_ui = {
                    "offer": trade_draft_offered,
                    "request": trade_draft_requested,
                    "valid_bank_trade": self._is_valid_bank_trade_draft(legal, active_player, trade_draft_offered, trade_draft_requested),
                    "bank_supply_rects": {},
                    "request_rects": {},
                    "offer_rects": {},
                    "hand_rects": {},
                }
            discard_ui = None
            if state.turn and state.turn.step == TurnStep.DISCARD and active_player is not None:
                discard_ui = {
                    "required": state.discard_requirements.get(active_player, 0),
                    "selected": discard_selection,
                    "selected_rects": {},
                    "hand_rects": {},
                }
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
                build_mode=build_mode,
                trade_ui=trade_ui,
                discard_ui=discard_ui,
                event_log_offset=event_log_offset,
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
                if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 4:
                    event_log_offset += 1
                    continue
                if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 5:
                    event_log_offset = max(event_log_offset - 1, 0)
                    continue

                if active_player is None or active_player not in controllers:
                    continue

                if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                    if drawn.event_log_scroll_up_rect is not None and drawn.event_log_scroll_up_rect.collidepoint(event.pos):
                        event_log_offset += 1
                        continue
                    if drawn.event_log_scroll_down_rect is not None and drawn.event_log_scroll_down_rect.collidepoint(event.pos):
                        event_log_offset = max(event_log_offset - 1, 0)
                        continue
                    if discard_ui is not None:
                        discard_action = self._handle_discard_overlay_click(event.pos, discard_ui, state, active_player, discard_selection)
                        if discard_action is not None:
                            selected_action_text = str(discard_action)
                            controllers[active_player].submit_action_intent(discard_action)
                        continue
                    clicked_action = self._handle_action_button_click(
                        event.pos,
                        drawn.action_button_rects,
                        legal,
                        state,
                        active_player,
                        build_mode,
                        trade_window_open,
                    )
                    if clicked_action is not None:
                        if isinstance(clicked_action, str):
                            if clicked_action.startswith("mode:"):
                                build_mode = clicked_action.split(":")[1]
                                trade_window_open = False
                            elif clicked_action == "clear_mode":
                                build_mode = None
                            elif clicked_action == "trade_open":
                                trade_window_open = True
                                build_mode = None
                            elif clicked_action == "trade_cancel":
                                trade_window_open = False
                                trade_draft_offered = {r: 0 for r in ResourceType}
                                trade_draft_requested = {r: 0 for r in ResourceType}
                                selected_action_text = "Trade draft cancelled"
                            elif clicked_action == "dev_placeholder":
                                event_log.append(f"[{action_counter:03d}] Dev cards not implemented yet")
                            continue
                        selected_action_text = str(clicked_action)
                        controllers[active_player].submit_action_intent(clicked_action)
                        continue
                    if trade_window_open and trade_ui is not None:
                        trade_action = self._handle_trade_overlay_click(
                            event.pos, trade_ui, legal, state, active_player, trade_draft_offered, trade_draft_requested
                        )
                        if trade_action is not None:
                            if isinstance(trade_action, str):
                                if trade_action == "cancel":
                                    trade_window_open = False
                                    trade_draft_offered = {r: 0 for r in ResourceType}
                                    trade_draft_requested = {r: 0 for r in ResourceType}
                                continue
                            selected_action_text = str(trade_action)
                            controllers[active_player].submit_action_intent(trade_action)
                            trade_window_open = False
                            trade_draft_offered = {r: 0 for r in ResourceType}
                            trade_draft_requested = {r: 0 for r in ResourceType}
                            continue

                if state.turn and state.turn.step == TurnStep.DISCARD:
                    discard_action = self._handle_discard_event(event, state, active_player, discard_selection)
                    if discard_action is not None:
                        selected_action_text = str(discard_action)
                        controllers[active_player].submit_action_intent(discard_action)
                    continue
                if state.turn and state.turn.step == TurnStep.ACTIONS:
                    bank_trade_action, bank_trade_offer, bank_trade_request = self._handle_bank_trade_event(
                        event,
                        active_player,
                        legal,
                        bank_trade_offer,
                        bank_trade_request,
                    )
                    if bank_trade_action is not None:
                        selected_action_text = str(bank_trade_action)
                        controllers[active_player].submit_action_intent(bank_trade_action)
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
                    if not self._is_board_action_allowed(mapped.action, build_mode):
                        continue
                    selected_action_text = str(mapped.action)
                    controllers[active_player].submit_action_intent(mapped.action)
                    if isinstance(mapped.action, (BuildRoad, BuildSettlement, BuildCity)):
                        build_mode = None
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
                    if state.turn is None or state.turn.step != TurnStep.ACTIONS:
                        bank_trade_offer = None
                        bank_trade_request = None
                        build_mode = None
                        trade_window_open = False
                        trade_draft_offered = {r: 0 for r in ResourceType}
                        trade_draft_requested = {r: 0 for r in ResourceType}
                    event_log_offset = 0

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
                return self._to_discard_action(player_id, selection)
        return None

    def _handle_discard_overlay_click(
        self,
        pos: tuple[int, int],
        discard_ui: dict[str, object],
        state: GameState,
        active_player: int,
        selection: dict[ResourceType, int],
    ) -> DiscardResources | None:
        required = int(discard_ui.get("required", 0))
        for resource, rect in discard_ui["hand_rects"].items():
            if rect.collidepoint(pos):
                player_have = state.players[active_player].resources.get(resource, 0)
                if selection[resource] < player_have and sum(selection.values()) < required:
                    selection[resource] += 1
                return None
        for resource, rect in discard_ui["selected_rects"].items():
            if rect.collidepoint(pos):
                if selection[resource] > 0:
                    selection[resource] -= 1
                return None
        if discard_ui["continue_button_rect"].collidepoint(pos) and sum(selection.values()) == required:
            return self._to_discard_action(active_player, selection)
        return None

    def _to_discard_action(self, player_id: int, selection: dict[ResourceType, int]) -> DiscardResources:
        resources = tuple((resource, amount) for resource, amount in selection.items() if amount > 0)
        return DiscardResources(player_id=player_id, resources=resources)

    def _handle_bank_trade_event(
        self,
        event,
        player_id: int,
        legal_actions: list[object],
        offer: ResourceType | None,
        request: ResourceType | None,
    ) -> tuple[BankTrade | None, ResourceType | None, ResourceType | None]:
        if event.type != self.pg.KEYDOWN:
            return None, offer, request
        offer_mapping = {
            self.pg.K_1: ResourceType.GRAIN,
            self.pg.K_2: ResourceType.LUMBER,
            self.pg.K_3: ResourceType.BRICK,
            self.pg.K_4: ResourceType.ORE,
            self.pg.K_5: ResourceType.WOOL,
        }
        request_mapping = {
            self.pg.K_z: ResourceType.GRAIN,
            self.pg.K_x: ResourceType.LUMBER,
            self.pg.K_c: ResourceType.BRICK,
            self.pg.K_v: ResourceType.ORE,
            self.pg.K_b: ResourceType.WOOL,
        }
        if event.key in offer_mapping:
            return None, offer_mapping[event.key], request
        if event.key in request_mapping:
            return None, offer, request_mapping[event.key]
        if event.key in (self.pg.K_BACKSPACE, self.pg.K_DELETE):
            return None, None, None
        if event.key in (self.pg.K_RETURN, self.pg.K_KP_ENTER) and offer is not None and request is not None:
            candidates = [
                action
                for action in legal_actions
                if isinstance(action, BankTrade)
                and action.player_id == player_id
                and action.offer_resource == offer
                and action.request_resource == request
            ]
            if candidates:
                return candidates[0], offer, request
        return None, offer, request

    def _create_display_surface(self):
        if self.fullscreen:
            info = self.pg.display.Info()
            self.width, self.height = info.current_w, info.current_h
            return self.pg.display.set_mode((self.width, self.height), self.pg.FULLSCREEN)
        return self.pg.display.set_mode((self.width, self.height), self.pg.RESIZABLE)

    def _board_center_and_radius(self, screen) -> tuple[tuple[int, int], int]:
        width, height = screen.get_size()
        panel_width = max(int(width * 0.30), 360)
        bottom_bar_height = max(int(height * 0.18), 130)
        board_width = max(width - panel_width - 40, 200)
        board_height = max(height - bottom_bar_height - 90, 200)
        center = (20 + board_width // 2, 70 + board_height // 2)
        radius = int(min(board_width, board_height) * 0.42)
        return center, max(radius, 120)

    def _is_board_action_allowed(self, action: object, build_mode: str | None) -> bool:
        if isinstance(action, BuildRoad):
            return build_mode == "road"
        if isinstance(action, BuildSettlement):
            return build_mode == "settlement"
        if isinstance(action, BuildCity):
            return build_mode == "city"
        return True

    def _handle_action_button_click(
        self,
        pos: tuple[int, int],
        button_rects: dict[str, object],
        legal_actions: list[object],
        state: GameState,
        active_player: int,
        build_mode: str | None,
        trade_window_open: bool,
    ) -> object | str | None:
        if button_rects.get("trade") and button_rects["trade"].collidepoint(pos):
            if any(isinstance(a, BankTrade) for a in legal_actions):
                return "trade_open"
        if button_rects.get("dev") and button_rects["dev"].collidepoint(pos):
            if self._can_afford_cost(state, active_player, {ResourceType.ORE: 1, ResourceType.GRAIN: 1, ResourceType.WOOL: 1}):
                return "dev_placeholder"
        if button_rects.get("road") and button_rects["road"].collidepoint(pos):
            if build_mode == "road":
                return "clear_mode"
            return "mode:road" if any(isinstance(a, BuildRoad) for a in legal_actions) else None
        if button_rects.get("settlement") and button_rects["settlement"].collidepoint(pos):
            if build_mode == "settlement":
                return "clear_mode"
            return "mode:settlement" if any(isinstance(a, BuildSettlement) for a in legal_actions) else None
        if button_rects.get("city") and button_rects["city"].collidepoint(pos):
            if build_mode == "city":
                return "clear_mode"
            return "mode:city" if any(isinstance(a, BuildCity) for a in legal_actions) else None
        if button_rects.get("primary") and button_rects["primary"].collidepoint(pos):
            roll = next((a for a in legal_actions if isinstance(a, RollDice)), None)
            if roll is not None:
                return roll
            end = next((a for a in legal_actions if isinstance(a, EndTurn)), None)
            if end is not None:
                return end
        if button_rects.get("dice") and button_rects["dice"].collidepoint(pos):
            roll = next((a for a in legal_actions if isinstance(a, RollDice)), None)
            if roll is not None:
                return roll
        if trade_window_open and button_rects.get("trade_cancel") and button_rects["trade_cancel"].collidepoint(pos):
            return "trade_cancel"
        return None

    def _handle_trade_overlay_click(
        self,
        pos: tuple[int, int],
        trade_ui: dict[str, object],
        legal_actions: list[object],
        state: GameState,
        active_player: int,
        offered: dict[ResourceType, int],
        requested: dict[ResourceType, int],
    ) -> BankTrade | str | None:
        for resource, rect in trade_ui["bank_supply_rects"].items():
            if rect.collidepoint(pos):
                requested[resource] += 1
                return None
        for resource, rect in trade_ui["request_rects"].items():
            if rect.collidepoint(pos):
                if requested[resource] > 0:
                    requested[resource] -= 1
                return None
        for resource, rect in trade_ui["hand_rects"].items():
            if rect.collidepoint(pos):
                max_offer = state.players[active_player].resources.get(resource, 0)
                if offered[resource] < max_offer:
                    offered[resource] += 1
                return None
        for resource, rect in trade_ui["offer_rects"].items():
            if rect.collidepoint(pos):
                if offered[resource] > 0:
                    offered[resource] -= 1
                return None
        if trade_ui["cancel_button_rect"].collidepoint(pos):
            return "cancel"
        if trade_ui["bank_button_rect"].collidepoint(pos):
            return self._to_bank_trade_action(legal_actions, active_player, offered, requested)
        return None

    def _to_bank_trade_action(
        self, legal_actions: list[object], player_id: int, offered: dict[ResourceType, int], requested: dict[ResourceType, int]
    ) -> BankTrade | None:
        offered_items = [(r, n) for r, n in offered.items() if n > 0]
        requested_items = [(r, n) for r, n in requested.items() if n > 0]
        if len(offered_items) != 1 or len(requested_items) != 1:
            return None
        offer_resource, offer_count = offered_items[0]
        request_resource, request_count = requested_items[0]
        if request_count != 1:
            return None
        for action in legal_actions:
            if (
                isinstance(action, BankTrade)
                and action.player_id == player_id
                and action.offer_resource == offer_resource
                and action.request_resource == request_resource
                and action.trade_rate == offer_count
            ):
                return action
        return None

    def _is_valid_bank_trade_draft(
        self, legal_actions: list[object], player_id: int, offered: dict[ResourceType, int], requested: dict[ResourceType, int]
    ) -> bool:
        return self._to_bank_trade_action(legal_actions, player_id, offered, requested) is not None

    def _trade_draft_status_text(
        self, offered: dict[ResourceType, int], requested: dict[ResourceType, int], legal_actions: list[object], player_id: int
    ) -> str:
        offer_txt = ", ".join(f"{self._resource_name(r)}:{n}" for r, n in offered.items() if n > 0) or "-"
        req_txt = ", ".join(f"{self._resource_name(r)}:{n}" for r, n in requested.items() if n > 0) or "-"
        valid = self._is_valid_bank_trade_draft(legal_actions, player_id, offered, requested)
        return f"Trade draft offer=[{offer_txt}] request=[{req_txt}] bank_valid={'yes' if valid else 'no'}"

    def _can_afford_cost(self, state: GameState, player_id: int, cost: dict[ResourceType, int]) -> bool:
        resources = state.players[player_id].resources
        return all(resources.get(resource, 0) >= need for resource, need in cost.items())

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
        bank_trade_line = self._detect_bank_trade(before, after)
        if bank_trade_line is not None:
            lines.append(bank_trade_line)
        return lines

    def _detect_bank_trade(self, before: GameState, after: GameState) -> str | None:
        if before.turn is None:
            return None
        player_id = before.turn.current_player
        if player_id not in before.players or player_id not in after.players:
            return None

        player_changes: dict[ResourceType, int] = {}
        for resource in ResourceType:
            delta = after.players[player_id].resources.get(resource, 0) - before.players[player_id].resources.get(resource, 0)
            if delta != 0:
                player_changes[resource] = delta

        for other_id in before.players:
            if other_id == player_id:
                continue
            for resource in ResourceType:
                if before.players[other_id].resources.get(resource, 0) != after.players[other_id].resources.get(resource, 0):
                    return None

        if len(player_changes) != 2:
            return None

        offered = next((resource for resource, delta in player_changes.items() if delta < 0), None)
        requested = next((resource for resource, delta in player_changes.items() if delta == 1), None)
        if offered is None or requested is None:
            return None
        rate = -player_changes[offered]
        if rate == 2:
            return f"P{player_id} traded 2 {self._resource_name(offered)} for 1 {self._resource_name(requested)} via {self._resource_name(offered)} port"
        if rate == 3:
            return f"P{player_id} traded 3 {self._resource_name(offered)} for 1 {self._resource_name(requested)} via 3:1 port"
        return f"P{player_id} traded 4 {self._resource_name(offered)} for 1 {self._resource_name(requested)}"

    def _selected_trade_rate_text(self, legal_actions: list[object], offer: ResourceType | None) -> str:
        if offer is None:
            return "-"
        rates = sorted(
            {
                action.trade_rate
                for action in legal_actions
                if isinstance(action, BankTrade) and action.offer_resource == offer
            }
        )
        if not rates:
            return "n/a"
        return str(rates[0])

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
