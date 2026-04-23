from __future__ import annotations

from typing import Mapping

from catan.controllers.human_controller import HumanController
from catan.controllers.base import Controller
from catan.core.engine import get_legal_actions
from catan.core.models.action import (
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    ChooseMonopolyResource,
    ChooseTradePartner,
    ChooseYearOfPlentyResources,
    DiscardResources,
    EndTurn,
    FinishRoadBuildingCard,
    ProposePlayerTrade,
    RejectTradeResponses,
    RespondToTradeInterested,
    RespondToTradePass,
    RollDice,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
)
from catan.core.models.enums import DevelopmentCardType, PlayerTradePhase, ResourceType, TurnStep
from catan.core.models.state import GameState
from catan.runners.game_setup import AppScreen, ControllerType, GameLaunchConfig, GameSetupState
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

    def run_main_menu_and_setup(self) -> GameLaunchConfig | None:
        self.pg.init()
        if hasattr(self.pg, "font"):
            self.pg.font.init()
        self.pg.display.set_caption("Catan MVP (Menu + Setup)")
        screen = self._create_display_surface()
        clock = self.pg.time.Clock()
        font = self.pg.font.SysFont("arial", 28)
        small_font = self.pg.font.SysFont("arial", 22)
        flow_state = GameSetupState()
        selected_seed_input = False

        while True:
            width, height = screen.get_size()
            title_rect = self.pg.Rect(40, 20, width - 80, 50)
            new_game_rect = self.pg.Rect(width // 2 - 120, height // 2 - 20, 240, 48)
            quit_rect = self.pg.Rect(width // 2 - 120, height // 2 + 44, 240, 48)
            back_rect = self.pg.Rect(40, height - 70, 160, 42)
            start_rect = self.pg.Rect(width - 220, height - 70, 180, 42)
            random_seed_rect = self.pg.Rect(60, 380, 170, 36)
            fixed_seed_rect = self.pg.Rect(250, 380, 160, 36)
            seed_input_rect = self.pg.Rect(60, 430, 350, 42)
            slot_rects = [self.pg.Rect(60, 120 + idx * 55, 520, 40) for idx in range(4)]

            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    self.pg.quit()
                    return None
                if event.type == self.pg.KEYDOWN and event.key == self.pg.K_F11:
                    self.fullscreen = not self.fullscreen
                    screen = self._create_display_surface()
                    continue
                if event.type == self.pg.VIDEORESIZE and not self.fullscreen:
                    self.width, self.height = event.w, event.h
                    screen = self._create_display_surface()
                    continue
                if flow_state.screen == AppScreen.MAIN_MENU:
                    if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        if new_game_rect.collidepoint(event.pos):
                            flow_state = flow_state.go_to_setup()
                        elif quit_rect.collidepoint(event.pos):
                            self.pg.quit()
                            return None
                else:
                    if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        selected_seed_input = seed_input_rect.collidepoint(event.pos)
                        if back_rect.collidepoint(event.pos):
                            flow_state = flow_state.back_to_menu()
                            selected_seed_input = False
                            continue
                        if start_rect.collidepoint(event.pos):
                            config = flow_state.to_launch_config()
                            if config is not None:
                                self.pg.quit()
                                return config
                        if random_seed_rect.collidepoint(event.pos):
                            flow_state = flow_state.with_random_seed()
                            continue
                        if fixed_seed_rect.collidepoint(event.pos):
                            if flow_state.use_random_seed:
                                flow_state = flow_state.with_fixed_seed_text("")
                            continue
                        for idx, rect in enumerate(slot_rects):
                            if rect.collidepoint(event.pos):
                                current = flow_state.player_slots[idx].controller_type
                                next_type = ControllerType.BOT_PLACEHOLDER if current == ControllerType.HUMAN else ControllerType.HUMAN
                                flow_state = flow_state.with_player_controller(idx, next_type)
                                break
                    if selected_seed_input and event.type == self.pg.KEYDOWN and not flow_state.use_random_seed:
                        if event.key == self.pg.K_BACKSPACE:
                            flow_state = flow_state.with_fixed_seed_text(flow_state.fixed_seed_text[:-1])
                        elif event.unicode and (event.unicode.isdigit() or (event.unicode == "-" and not flow_state.fixed_seed_text)):
                            flow_state = flow_state.with_fixed_seed_text(flow_state.fixed_seed_text + event.unicode)

            screen.fill((20, 20, 28))
            title = "Main Menu" if flow_state.screen == AppScreen.MAIN_MENU else "Game Setup"
            screen.blit(font.render(title, True, (240, 240, 240)), (title_rect.x, title_rect.y))
            if flow_state.screen == AppScreen.MAIN_MENU:
                self.pg.draw.rect(screen, (70, 120, 70), new_game_rect)
                self.pg.draw.rect(screen, (120, 70, 70), quit_rect)
                screen.blit(font.render("New Game", True, (255, 255, 255)), (new_game_rect.x + 45, new_game_rect.y + 8))
                screen.blit(font.render("Quit", True, (255, 255, 255)), (quit_rect.x + 85, quit_rect.y + 8))
            else:
                screen.blit(small_font.render("Click slot to toggle controller: Human/Bot", True, (200, 200, 220)), (60, 85))
                for idx, rect in enumerate(slot_rects):
                    slot = flow_state.player_slots[idx]
                    self.pg.draw.rect(screen, (60, 60, 90), rect)
                    label = f"Player {slot.player_id}: {'Human' if slot.controller_type == ControllerType.HUMAN else 'Bot (placeholder)'}"
                    screen.blit(small_font.render(label, True, (255, 255, 255)), (rect.x + 10, rect.y + 8))
                self.pg.draw.rect(screen, (80, 80, 120), random_seed_rect)
                self.pg.draw.rect(screen, (80, 80, 120), fixed_seed_rect)
                screen.blit(small_font.render("Random seed", True, (255, 255, 255)), (random_seed_rect.x + 12, random_seed_rect.y + 7))
                screen.blit(small_font.render("Fixed seed", True, (255, 255, 255)), (fixed_seed_rect.x + 20, fixed_seed_rect.y + 7))
                seed_label = "ACTIVE" if flow_state.use_random_seed else "INACTIVE"
                fixed_label = "ACTIVE" if not flow_state.use_random_seed else "INACTIVE"
                screen.blit(small_font.render(seed_label, True, (170, 230, 170)), (random_seed_rect.right + 12, random_seed_rect.y + 7))
                screen.blit(small_font.render(fixed_label, True, (170, 230, 170)), (fixed_seed_rect.right + 12, fixed_seed_rect.y + 7))
                self.pg.draw.rect(screen, (40, 40, 60), seed_input_rect)
                seed_text = flow_state.fixed_seed_text if flow_state.fixed_seed_text else "(enter number)"
                screen.blit(small_font.render(f"Seed: {seed_text}", True, (240, 240, 240)), (seed_input_rect.x + 10, seed_input_rect.y + 10))
                start_color = (70, 120, 70) if flow_state.can_start_game() else (80, 80, 80)
                self.pg.draw.rect(screen, (90, 90, 90), back_rect)
                self.pg.draw.rect(screen, start_color, start_rect)
                screen.blit(small_font.render("Back", True, (255, 255, 255)), (back_rect.x + 55, back_rect.y + 10))
                screen.blit(small_font.render("Start Game", True, (255, 255, 255)), (start_rect.x + 35, start_rect.y + 10))
                if not flow_state.can_start_game():
                    screen.blit(small_font.render("Fixed seed must be a valid integer.", True, (220, 130, 130)), (60, 485))

            self.pg.display.flip()
            clock.tick(30)

    def run(self, initial_state: GameState, controllers: Mapping[int, Controller]) -> GameState:
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
        discard_selection_player: int | None = None
        bank_trade_offer: ResourceType | None = None
        bank_trade_request: ResourceType | None = None
        event_log_offset = 0
        build_mode: str | None = None
        trade_draft_offered = {r: 0 for r in ResourceType}
        trade_draft_requested = {r: 0 for r in ResourceType}
        trade_window_open = False
        year_of_plenty_selected = {r: 0 for r in ResourceType}

        running = True
        while running:
            board_center, board_radius = self._board_center_and_radius(screen)
            layout = build_circular_layout(state.board, center=board_center, radius=board_radius)

            active_player = self._active_player(state)
            discard_selection_player = self._sync_discard_selection(
                state,
                active_player,
                discard_selection,
                discard_selection_player,
            )
            legal = get_legal_actions(state, active_player) if active_player is not None else []
            hover = input_mapper.get_hover_target(self.pg.mouse.get_pos(), layout) if hasattr(self.pg, "mouse") else HoverTarget()

            if state.turn and state.turn.step == TurnStep.DISCARD and active_player is not None:
                required = state.discard_requirements.get(active_player, 0)
                selected_action_text = f"Discard {required}: " + ", ".join(f"{r.name}:{n}" for r, n in discard_selection.items() if n > 0)
            elif state.turn and state.turn.step == TurnStep.ACTIONS and trade_window_open:
                selected_action_text = self._trade_draft_status_text(trade_draft_offered, trade_draft_requested, legal, active_player)
            elif state.player_trade is not None:
                selected_action_text = self._player_trade_status_text(state)

            trade_ui = None
            if state.player_trade is not None:
                trade_ui = {
                    "mode": "response" if state.player_trade.phase == PlayerTradePhase.RESPONSES else "selection",
                    "offer": dict(state.player_trade.offered_resources),
                    "request": dict(state.player_trade.requested_resources),
                    "current_responder": self._current_trade_responder(state),
                    "eligible_responders": set(state.player_trade.eligible_responders),
                    "interested_responders": tuple(state.player_trade.interested_responders),
                    "response_interested_rect": None,
                    "response_pass_rect": None,
                    "selection_rects": {},
                    "reject_all_rect": None,
                }
            elif trade_window_open:
                trade_ui = {
                    "mode": "draft",
                    "offer": trade_draft_offered,
                    "request": trade_draft_requested,
                    "valid_bank_trade": self._is_valid_bank_trade_draft(legal, active_player, trade_draft_offered, trade_draft_requested),
                    "valid_player_trade": self._is_valid_player_trade_draft(state, active_player, trade_draft_offered, trade_draft_requested),
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
            dev_card_ui = None
            if state.turn and state.turn.step == TurnStep.YEAR_OF_PLENTY:
                dev_card_ui = {
                    "mode": "year_of_plenty",
                    "selected": year_of_plenty_selected,
                    "resource_rects": {},
                    "submit_rect": None,
                }
            elif state.turn and state.turn.step == TurnStep.MONOPOLY:
                dev_card_ui = {
                    "mode": "monopoly",
                    "resource_rects": {},
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
                dev_card_ui=dev_card_ui,
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
                active_controller = controllers[active_player]
                is_human = isinstance(active_controller, HumanController)

                if is_human and event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
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
                            active_controller.submit_action_intent(discard_action)
                        continue
                    if dev_card_ui is not None:
                        dev_flow_action = self._handle_dev_card_overlay_click(event.pos, dev_card_ui, active_player, legal, year_of_plenty_selected)
                        if dev_flow_action is not None:
                            selected_action_text = str(dev_flow_action)
                            active_controller.submit_action_intent(dev_flow_action)
                            if isinstance(dev_flow_action, ChooseYearOfPlentyResources):
                                year_of_plenty_selected = {r: 0 for r in ResourceType}
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
                            continue
                        selected_action_text = str(clicked_action)
                        active_controller.submit_action_intent(clicked_action)
                        continue
                    dev_click_action = self._dev_card_click_action(event.pos, drawn.dev_card_rects, legal)
                    if dev_click_action is not None:
                        selected_action_text = str(dev_click_action)
                        active_controller.submit_action_intent(dev_click_action)
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
                            active_controller.submit_action_intent(trade_action)
                            trade_window_open = False
                            trade_draft_offered = {r: 0 for r in ResourceType}
                            trade_draft_requested = {r: 0 for r in ResourceType}
                            continue
                    if state.player_trade is not None and trade_ui is not None:
                        player_trade_action = self._handle_player_trade_overlay_click(event.pos, trade_ui, state, active_player)
                        if player_trade_action is not None:
                            selected_action_text = str(player_trade_action)
                            active_controller.submit_action_intent(player_trade_action)
                            continue

                if is_human and state.turn and state.turn.step == TurnStep.DISCARD:
                    discard_action = self._handle_discard_event(event, state, active_player, discard_selection)
                    if discard_action is not None:
                        selected_action_text = str(discard_action)
                        active_controller.submit_action_intent(discard_action)
                    continue
                if is_human and state.turn and state.turn.step == TurnStep.ACTIONS:
                    bank_trade_action, bank_trade_offer, bank_trade_request = self._handle_bank_trade_event(
                        event,
                        active_player,
                        legal,
                        bank_trade_offer,
                        bank_trade_request,
                    )
                    if bank_trade_action is not None:
                        selected_action_text = str(bank_trade_action)
                        active_controller.submit_action_intent(bank_trade_action)
                        continue

                if not is_human:
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
                    active_controller.submit_action_intent(mapped.action)
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
                        discard_selection_player = None
                    if state.turn is None or state.turn.step != TurnStep.ACTIONS:
                        bank_trade_offer = None
                        bank_trade_request = None
                        build_mode = None
                        trade_window_open = False
                        trade_draft_offered = {r: 0 for r in ResourceType}
                        trade_draft_requested = {r: 0 for r in ResourceType}
                    if state.turn is None or state.turn.step != TurnStep.YEAR_OF_PLENTY:
                        year_of_plenty_selected = {r: 0 for r in ResourceType}
                    event_log_offset = 0

            self.pg.display.flip()
            clock.tick(30)

        self.pg.quit()
        return state

    def _sync_discard_selection(
        self,
        state: GameState,
        active_player: int | None,
        selection: dict[ResourceType, int],
        current_selection_player: int | None,
    ) -> int | None:
        if not (state.turn and state.turn.step == TurnStep.DISCARD and active_player is not None):
            for resource in ResourceType:
                selection[resource] = 0
            return None
        if current_selection_player != active_player:
            for resource in ResourceType:
                selection[resource] = 0
        return active_player

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

    def _handle_dev_card_overlay_click(
        self,
        pos: tuple[int, int],
        dev_card_ui: dict[str, object],
        active_player: int,
        legal_actions: list[object],
        year_of_plenty_selected: dict[ResourceType, int],
    ) -> ChooseYearOfPlentyResources | ChooseMonopolyResource | None:
        mode = dev_card_ui.get("mode")
        if mode == "year_of_plenty":
            for resource, rect in dev_card_ui["resource_rects"].items():
                if rect.collidepoint(pos):
                    if sum(year_of_plenty_selected.values()) < 2:
                        year_of_plenty_selected[resource] += 1
                    return None
            if dev_card_ui["submit_rect"] is not None and dev_card_ui["submit_rect"].collidepoint(pos):
                picked = [resource for resource, amount in year_of_plenty_selected.items() for _ in range(amount)]
                if len(picked) != 2:
                    return None
                action = ChooseYearOfPlentyResources(player_id=active_player, first_resource=picked[0], second_resource=picked[1])
                return action if action in legal_actions else None
            return None
        if mode == "monopoly":
            for resource, rect in dev_card_ui["resource_rects"].items():
                if rect.collidepoint(pos):
                    action = ChooseMonopolyResource(player_id=active_player, resource=resource)
                    return action if action in legal_actions else None
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
            if state.turn is not None and state.turn.step == TurnStep.ACTIONS and state.player_trade is None:
                return "trade_open"
        if button_rects.get("dev") and button_rects["dev"].collidepoint(pos):
            return next((a for a in legal_actions if isinstance(a, BuyDevelopmentCard)), None)
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
            done = next((a for a in legal_actions if isinstance(a, FinishRoadBuildingCard)), None)
            if done is not None:
                return done
        if button_rects.get("dice") and button_rects["dice"].collidepoint(pos):
            roll = next((a for a in legal_actions if isinstance(a, RollDice)), None)
            if roll is not None:
                return roll
        if trade_window_open and button_rects.get("trade_cancel") and button_rects["trade_cancel"].collidepoint(pos):
            return "trade_cancel"
        return None

    def _dev_card_click_action(self, pos: tuple[int, int], dev_card_rects: dict[DevelopmentCardType, object], legal_actions: list[object]) -> object | None:
        for card_type, rect in dev_card_rects.items():
            if not rect.collidepoint(pos):
                continue
            if card_type == DevelopmentCardType.KNIGHT:
                return next((action for action in legal_actions if isinstance(action, PlayKnightCard)), None)
            if card_type == DevelopmentCardType.ROAD_BUILDING:
                return next((action for action in legal_actions if isinstance(action, PlayRoadBuildingCard)), None)
            if card_type == DevelopmentCardType.YEAR_OF_PLENTY:
                return next((action for action in legal_actions if isinstance(action, PlayYearOfPlentyCard)), None)
            if card_type == DevelopmentCardType.MONOPOLY:
                return next((action for action in legal_actions if isinstance(action, PlayMonopolyCard)), None)
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
    ) -> BankTrade | ProposePlayerTrade | str | None:
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
        if trade_ui["player_button_rect"].collidepoint(pos):
            if self._is_valid_player_trade_draft(state, active_player, offered, requested):
                return ProposePlayerTrade(
                    player_id=active_player,
                    offered_resources=tuple((resource, amount) for resource, amount in offered.items() if amount > 0),
                    requested_resources=tuple((resource, amount) for resource, amount in requested.items() if amount > 0),
                )
        return None

    def _handle_player_trade_overlay_click(
        self,
        pos: tuple[int, int],
        trade_ui: dict[str, object],
        state: GameState,
        active_player: int,
    ) -> RespondToTradeInterested | RespondToTradePass | ChooseTradePartner | RejectTradeResponses | None:
        mode = trade_ui.get("mode")
        if mode == "response":
            if trade_ui["response_interested_rect"].collidepoint(pos):
                return RespondToTradeInterested(player_id=active_player)
            if trade_ui["response_pass_rect"].collidepoint(pos):
                return RespondToTradePass(player_id=active_player)
            return None
        if mode == "selection":
            for player_id, rect in trade_ui["selection_rects"].items():
                if rect.collidepoint(pos):
                    return ChooseTradePartner(player_id=active_player, partner_player_id=player_id)
            if trade_ui["reject_all_rect"].collidepoint(pos):
                return RejectTradeResponses(player_id=active_player)
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

    def _is_valid_player_trade_draft(
        self,
        state: GameState,
        player_id: int,
        offered: dict[ResourceType, int],
        requested: dict[ResourceType, int],
    ) -> bool:
        if state.turn is None or state.turn.current_player != player_id:
            return False
        offered_items = [(r, n) for r, n in offered.items() if n > 0]
        requested_items = [(r, n) for r, n in requested.items() if n > 0]
        if not offered_items or not requested_items:
            return False
        return all(state.players[player_id].resources.get(resource, 0) >= amount for resource, amount in offered_items)

    def _current_trade_responder(self, state: GameState) -> int | None:
        if state.player_trade is None:
            return None
        idx = state.player_trade.current_responder_index
        if idx >= len(state.player_trade.responder_order):
            return None
        return state.player_trade.responder_order[idx]

    def _player_trade_status_text(self, state: GameState) -> str:
        trade = state.player_trade
        if trade is None:
            return ""
        offer_txt = ", ".join(f"{self._resource_name(r)}:{n}" for r, n in trade.offered_resources)
        request_txt = ", ".join(f"{self._resource_name(r)}:{n}" for r, n in trade.requested_resources)
        if trade.phase == PlayerTradePhase.RESPONSES:
            responder = self._current_trade_responder(state)
            return f"Player trade response: offer=[{offer_txt}] request=[{request_txt}] waiting=P{responder}"
        interested = ", ".join(f"P{pid}" for pid in trade.interested_responders)
        return f"Player trade select partner: interested=[{interested}]"

    def _describe_transition(self, before: GameState, after: GameState, action_text: str) -> list[str]:
        lines: list[str] = [f"applied {action_text}"]
        acting_player = before.turn.current_player if before.turn is not None else None

        before_roll = before.turn.last_roll if before.turn else None
        after_roll = after.turn.last_roll if after.turn else None
        if after_roll is not None and after_roll != before_roll:
            total = after_roll[0] + after_roll[1]
            lines.append(f"Dice rolled {after_roll[0]} + {after_roll[1]} = {total}")

        if before.robber_tile_id != after.robber_tile_id and acting_player is not None:
            lines.append(f"P{acting_player} moved the robber to tile {after.robber_tile_id}")
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
        if acting_player is not None and after.players[acting_player].knights_played > before.players[acting_player].knights_played:
            lines.append(f"P{acting_player} played a Knight card")
            lines.append(f"P{acting_player} now has {after.players[acting_player].knights_played} Knights played")
        if acting_player is not None and before.turn and before.turn.step == TurnStep.ACTIONS and after.turn:
            if after.turn.step == TurnStep.ROAD_BUILDING:
                lines.append(f"P{acting_player} played Road Building")
            if after.turn.step == TurnStep.YEAR_OF_PLENTY:
                lines.append(f"P{acting_player} played Year of Plenty")
            if after.turn.step == TurnStep.MONOPOLY:
                lines.append(f"P{acting_player} played Monopoly")
        if acting_player is not None and before.turn and after.turn:
            if before.turn.step == TurnStep.ROAD_BUILDING and after.turn.step == TurnStep.ACTIONS:
                roads_before = sum(1 for _, owner in before.placed.roads.items() if owner == acting_player)
                roads_after = sum(1 for _, owner in after.placed.roads.items() if owner == acting_player)
                gained = max(roads_after - roads_before, 0)
                lines.append(f"P{acting_player} placed {gained} free roads")
            if before.turn.step == TurnStep.YEAR_OF_PLENTY and after.turn.step == TurnStep.ACTIONS:
                gains = []
                for resource in ResourceType:
                    delta = after.players[acting_player].resources.get(resource, 0) - before.players[acting_player].resources.get(resource, 0)
                    if delta > 0:
                        gains.append(f"{delta} {self._resource_name(resource)}")
                if gains:
                    lines.append(f"P{acting_player} received {' and '.join(gains)}")
            if before.turn.step == TurnStep.MONOPOLY and after.turn.step == TurnStep.ACTIONS:
                collected_total = 0
                chosen_resource: ResourceType | None = None
                for resource in ResourceType:
                    delta = after.players[acting_player].resources.get(resource, 0) - before.players[acting_player].resources.get(resource, 0)
                    if delta > 0:
                        collected_total = delta
                        chosen_resource = resource
                if chosen_resource is not None:
                    lines.append(f"P{acting_player} played Monopoly on {self._resource_name(chosen_resource)}")
                    lines.append(f"P{acting_player} collected {collected_total} {self._resource_name(chosen_resource)}")
        if before.largest_army_holder != after.largest_army_holder:
            if before.largest_army_holder is not None:
                lines.append(f"P{before.largest_army_holder} lost Largest Army")
            if after.largest_army_holder is not None:
                lines.append(f"P{after.largest_army_holder} claimed Largest Army")
        if before.longest_road_holder != after.longest_road_holder:
            if before.longest_road_holder is not None:
                lines.append(f"P{before.longest_road_holder} lost Longest Road")
            if after.longest_road_holder is not None:
                lines.append(f"P{after.longest_road_holder} claimed Longest Road")
        bank_trade_line = self._detect_bank_trade(before, after)
        if bank_trade_line is not None:
            lines.append(bank_trade_line)
        if self._did_player_buy_development_card(before, after):
            buyer = before.turn.current_player if before.turn is not None else after.turn.current_player if after.turn is not None else None
            if buyer is not None:
                lines.append(f"P{buyer} bought a development card")
        lines.extend(self._detect_player_trade_lines(before, after))
        return lines

    def _did_player_buy_development_card(self, before: GameState, after: GameState) -> bool:
        if len(after.dev_deck) != len(before.dev_deck) - 1:
            return False
        for player_id in before.players:
            before_count = sum(before.players[player_id].dev_cards.values())
            after_count = sum(after.players[player_id].dev_cards.values())
            if after_count == before_count + 1:
                return True
        return False

    def _detect_player_trade_lines(self, before: GameState, after: GameState) -> list[str]:
        lines: list[str] = []
        before_trade = before.player_trade
        after_trade = after.player_trade
        if before_trade is None and after_trade is not None:
            offer = ", ".join(f"{n} {self._resource_name(r)}" for r, n in after_trade.offered_resources)
            request = ", ".join(f"{n} {self._resource_name(r)}" for r, n in after_trade.requested_resources)
            lines.append(f"P{after_trade.proposer_player_id} offered all players: {offer} for {request}")
            responder = self._current_trade_responder(after)
            if responder is not None:
                for pid in after_trade.responder_order[: after_trade.current_responder_index]:
                    if pid not in after_trade.eligible_responders:
                        lines.append(f"P{pid} cannot accept and is skipped")
            return lines
        if before_trade is None:
            return lines
        if after_trade is None:
            trade_line = self._detect_player_trade_execution(before, after, before_trade.proposer_player_id)
            if before_trade.phase == PlayerTradePhase.RESPONSES and not before_trade.interested_responders:
                lines.append("No players were interested")
            elif before_trade.phase == PlayerTradePhase.PARTNER_SELECTION and trade_line is None:
                lines.append(f"P{before_trade.proposer_player_id} rejected all trade responses")
            if trade_line is not None:
                lines.append(trade_line)
            return lines

        if before_trade.phase == PlayerTradePhase.RESPONSES and after_trade.phase == PlayerTradePhase.RESPONSES:
            responder = before_trade.responder_order[before_trade.current_responder_index]
            if responder in after_trade.interested_responders:
                lines.append(f"P{responder} is interested")
            else:
                lines.append(f"P{responder} is not interested")

        if before_trade.phase == PlayerTradePhase.RESPONSES and after_trade.phase == PlayerTradePhase.PARTNER_SELECTION:
            responder = before_trade.responder_order[before_trade.current_responder_index]
            if responder in after_trade.interested_responders:
                lines.append(f"P{responder} is interested")
            else:
                lines.append(f"P{responder} is not interested")

        if before_trade.phase == PlayerTradePhase.PARTNER_SELECTION and after_trade is None:
            partner = self._find_trade_partner_from_delta(before, after, before_trade.proposer_player_id)
            if partner is not None:
                lines.append(f"P{before_trade.proposer_player_id} chose to trade with P{partner}")
        return lines

    def _detect_player_trade_execution(self, before: GameState, after: GameState, proposer_id: int) -> str | None:
        partner = self._find_trade_partner_from_delta(before, after, proposer_id)
        if partner is None:
            return None
        offer_parts = []
        request_parts = []
        for resource in ResourceType:
            delta = after.players[proposer_id].resources.get(resource, 0) - before.players[proposer_id].resources.get(resource, 0)
            if delta < 0:
                offer_parts.append(f"{-delta} {self._resource_name(resource)}")
            elif delta > 0:
                request_parts.append(f"{delta} {self._resource_name(resource)}")
        offer_txt = ", ".join(offer_parts)
        request_txt = ", ".join(request_parts)
        return f"P{proposer_id} traded {offer_txt} for {request_txt} with P{partner}"

    def _find_trade_partner_from_delta(self, before: GameState, after: GameState, proposer_id: int) -> int | None:
        changed_others = [
            pid
            for pid in before.players
            if pid != proposer_id and any(before.players[pid].resources.get(resource, 0) != after.players[pid].resources.get(resource, 0) for resource in ResourceType)
        ]
        if len(changed_others) != 1:
            return None
        return changed_others[0]

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
