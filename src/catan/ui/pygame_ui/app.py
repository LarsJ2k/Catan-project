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
    MoveRobber,
    PlaceSetupRoad,
    PlaceSetupSettlement,
)
from catan.core.models.enums import DevelopmentCardType, PlayerTradePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState
from catan.runners.game_setup import (
    AppScreen,
    GameLaunchConfig,
    GameSetupState,
    TournamentSetupState,
    available_controller_types,
    controller_label,
)
from catan.runners.local_pygame_runner import LocalPygameRunner
from catan.runners.tournament import HeadlessTournamentRunner, TournamentFormat, export_tournament_result, generate_match_configs
from catan.controllers.bot_catalog import (
    create_custom_bot_definition,
    delete_custom_bot_definition,
    get_bot_definition,
    list_bot_definitions,
)
from catan.controllers.heuristic_params import merge_with_family_defaults

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
        self.return_to_main_menu = False

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
        tournament_state = TournamentSetupState()
        tournament_summary_lines: list[str] = []
        selected_seed_input = False
        list_scroll_offset = 0
        selected_lab_bot_id: str | None = None
        create_form_open = False
        new_bot_name = ""
        new_bot_description = ""
        new_bot_parameters: dict[str, str] = {}
        new_bot_param_keys: list[str] = []
        selected_new_bot_field_idx = 0
        bot_lab_scroll_offset = 0
        bot_lab_error: str | None = None
        delete_confirm_open = False

        while True:
            width, height = screen.get_size()
            title_rect = self.pg.Rect(40, 20, width - 80, 50)
            new_game_rect = self.pg.Rect(width // 2 - 120, height // 2 - 20, 240, 48)
            tournament_rect = self.pg.Rect(width // 2 - 120, height // 2 + 44, 240, 48)
            bot_lab_rect = self.pg.Rect(width // 2 - 120, height // 2 + 108, 240, 48)
            quit_rect = self.pg.Rect(width // 2 - 120, height // 2 + 172, 240, 48)
            back_rect = self.pg.Rect(40, height - 70, 160, 42)
            start_rect = self.pg.Rect(width - 220, height - 70, 180, 42)
            seed_slider_rect = self.pg.Rect(60, height - 230, 350, 36)
            seed_input_rect = self.pg.Rect(60, height - 180, 350, 42)
            left_slots_x = 60
            left_slots_y = 120
            slot_height = 68
            slot_width = 360
            slot_gap = 14
            slot_rects = [
                self.pg.Rect(left_slots_x, left_slots_y + idx * (slot_height + slot_gap), slot_width, slot_height)
                for idx in range(flow_state.max_players)
            ]
            arrow_rect = self.pg.Rect(left_slots_x + slot_width + 24, left_slots_y + 92, 64, 52)
            list_x = arrow_rect.right + 24
            list_y = left_slots_y
            list_height = min(4 * slot_height + 3 * slot_gap, height - 260)
            list_rect = self.pg.Rect(list_x, list_y, width - list_x - 60, list_height)
            list_entry_height = 52
            list_entry_gap = 8
            available_types = available_controller_types()
            total_list_height = len(available_types) * (list_entry_height + list_entry_gap)
            max_list_scroll = max(0, total_list_height - list_rect.height)
            list_scroll_offset = max(0, min(list_scroll_offset, max_list_scroll))
            remove_rects = {}
            for idx, slot_rect in enumerate(slot_rects):
                remove_rects[idx] = self.pg.Rect(slot_rect.right - 30, slot_rect.y + 8, 22, 22)

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
                        elif tournament_rect.collidepoint(event.pos):
                            flow_state = GameSetupState(screen=AppScreen.TOURNAMENT_SETUP)
                        elif bot_lab_rect.collidepoint(event.pos):
                            flow_state = GameSetupState(screen=AppScreen.BOT_LAB)
                            bots = list_bot_definitions()
                            selected_lab_bot_id = bots[0].bot_id if bots else None
                        elif quit_rect.collidepoint(event.pos):
                            self.pg.quit()
                            return None
                elif flow_state.screen == AppScreen.GAME_SETUP:
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
                        if seed_slider_rect.collidepoint(event.pos):
                            slider_mid_x = seed_slider_rect.centerx
                            if event.pos[0] < slider_mid_x:
                                flow_state = flow_state.with_random_seed()
                            elif flow_state.use_random_seed:
                                flow_state = flow_state.with_fixed_seed_text("")
                            continue
                        if arrow_rect.collidepoint(event.pos) and flow_state.can_add_player():
                            flow_state = flow_state.add_selected_player()
                            continue
                        clicked_remove = False
                        for idx, remove_rect in remove_rects.items():
                            if remove_rect.collidepoint(event.pos):
                                flow_state = flow_state.remove_player_at(idx)
                                clicked_remove = True
                                break
                        if clicked_remove:
                            continue
                        if list_rect.collidepoint(event.pos):
                            relative_y = event.pos[1] - list_rect.y + list_scroll_offset
                            option_idx = relative_y // (list_entry_height + list_entry_gap)
                            if 0 <= option_idx < len(available_types):
                                option_y_start = option_idx * (list_entry_height + list_entry_gap)
                                if relative_y <= option_y_start + list_entry_height:
                                    flow_state = flow_state.with_selected_controller(available_types[option_idx])
                            continue
                    if event.type == self.pg.MOUSEWHEEL and flow_state.screen == AppScreen.GAME_SETUP:
                        mouse_pos = self.pg.mouse.get_pos()
                        if list_rect.collidepoint(mouse_pos):
                            list_scroll_offset = max(0, min(max_list_scroll, list_scroll_offset - event.y * 28))
                    if selected_seed_input and event.type == self.pg.KEYDOWN and not flow_state.use_random_seed:
                        if event.key == self.pg.K_BACKSPACE:
                            flow_state = flow_state.with_fixed_seed_text(flow_state.fixed_seed_text[:-1])
                        elif event.unicode and (event.unicode.isdigit() or (event.unicode == "-" and not flow_state.fixed_seed_text)):
                            flow_state = flow_state.with_fixed_seed_text(flow_state.fixed_seed_text + event.unicode)
                elif flow_state.screen == AppScreen.TOURNAMENT_SETUP:
                    bot_specs = list_bot_definitions()
                    if tournament_state.selected_bot is None and bot_specs:
                        tournament_state = tournament_state.with_selected_bot(bot_specs[0].bot_id)
                    configured_bot_slots = [self.pg.Rect(60, 140 + idx * 56, 360, 46) for idx in range(8)]
                    remove_bot_rects = {
                        idx: self.pg.Rect(slot.right - 30, slot.y + 10, 24, 24) for idx, slot in enumerate(configured_bot_slots)
                    }
                    add_bot_rect = self.pg.Rect(448, 228, 64, 52)
                    available_bot_list_rect = self.pg.Rect(540, 140, width - 600, 360)
                    option_height = 44
                    option_gap = 8
                    options_total_height = len(bot_specs) * (option_height + option_gap)
                    max_bot_scroll = max(0, options_total_height - available_bot_list_rect.height)
                    list_scroll_offset = max(0, min(list_scroll_offset, max_bot_scroll))
                    fixed_format_rect = self.pg.Rect(60, height - 245, 220, 40)
                    round_robin_rect = self.pg.Rect(290, height - 245, 180, 40)
                    seat_rotation_rect = self.pg.Rect(60, height - 195, 180, 38)
                    export_json_rect = self.pg.Rect(250, height - 195, 170, 38)
                    export_excel_rect = self.pg.Rect(430, height - 195, 170, 38)
                    seed_minus_rect = self.pg.Rect(60, height - 145, 42, 36)
                    seed_plus_rect = self.pg.Rect(236, height - 145, 42, 36)
                    if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        if back_rect.collidepoint(event.pos):
                            flow_state = flow_state.back_to_menu()
                            continue
                        if start_rect.collidepoint(event.pos):
                            config = tournament_state.to_tournament_config()
                            if config is not None:
                                total_matches = len(generate_match_configs(config))

                                def _render_tournament_progress(completed_matches: int, total_matches_count: int) -> None:
                                    screen.fill((17, 17, 26))
                                    progress_title = font.render("Running Tournament...", True, (240, 240, 245))
                                    progress_text = small_font.render(
                                        f"{completed_matches}/{total_matches_count} matches complete",
                                        True,
                                        (210, 230, 210),
                                    )
                                    instruction = small_font.render("Please wait while matches are simulated.", True, (185, 185, 205))
                                    screen.blit(progress_title, (width // 2 - progress_title.get_width() // 2, height // 2 - 48))
                                    screen.blit(progress_text, (width // 2 - progress_text.get_width() // 2, height // 2 - 4))
                                    screen.blit(instruction, (width // 2 - instruction.get_width() // 2, height // 2 + 28))
                                    if hasattr(self.pg, "event"):
                                        self.pg.event.pump()
                                    self.pg.display.flip()

                                _render_tournament_progress(0, total_matches)
                                result = HeadlessTournamentRunner().run(config, progress_callback=_render_tournament_progress)
                                json_path, excel_path = export_tournament_result(result)
                                tournament_summary_lines = [
                                    f"Matches: {len(result.matches)}",
                                    f"JSON: {json_path}" if json_path is not None else "JSON: disabled",
                                    f"Excel: {excel_path}" if excel_path is not None else "Excel: disabled",
                                ]
                                for bot, agg in sorted(result.aggregates.items(), key=lambda item: item[1].win_rate, reverse=True):
                                    tournament_summary_lines.append(
                                        f"{controller_label(bot)} - games={agg.games_played}, wins={agg.wins}, "
                                        f"win%={agg.win_rate:.3f}, avg_vp={agg.average_final_vp:.2f}, avg_rank={agg.average_rank:.2f}"
                                    )
                            continue
                        if fixed_format_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.with_format(TournamentFormat.FIXED_LINEUP_BATCH.value)
                            continue
                        if round_robin_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.with_format(TournamentFormat.ROUND_ROBIN.value)
                            continue
                        if seat_rotation_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.with_seat_rotation_enabled(not tournament_state.seat_rotation_enabled)
                            continue
                        if export_json_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.with_export_json(not tournament_state.export_json)
                            continue
                        if export_excel_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.with_export_csv(not tournament_state.export_csv)
                            continue
                        if seed_minus_rect.collidepoint(event.pos):
                            new_seed_blocks = max(1, int(tournament_state.seed_blocks_text or "1") - 1)
                            tournament_state = tournament_state.with_seed_blocks_text(str(new_seed_blocks))
                            continue
                        if seed_plus_rect.collidepoint(event.pos):
                            new_seed_blocks = int(tournament_state.seed_blocks_text or "1") + 1
                            tournament_state = tournament_state.with_seed_blocks_text(str(new_seed_blocks))
                            continue
                        if add_bot_rect.collidepoint(event.pos):
                            tournament_state = tournament_state.add_selected_bot()
                            continue
                        removed = False
                        for idx, remove_rect in remove_bot_rects.items():
                            if remove_rect.collidepoint(event.pos):
                                tournament_state = tournament_state.remove_selected_bot_at(idx)
                                removed = True
                                break
                        if removed:
                            continue
                        if available_bot_list_rect.collidepoint(event.pos):
                            relative_y = event.pos[1] - available_bot_list_rect.y + list_scroll_offset
                            option_idx = relative_y // (option_height + option_gap)
                            if 0 <= option_idx < len(bot_specs):
                                option_y_start = option_idx * (option_height + option_gap)
                                if relative_y <= option_y_start + option_height:
                                    tournament_state = tournament_state.with_selected_bot(bot_specs[option_idx].bot_id)
                            continue
                    if event.type == self.pg.MOUSEWHEEL:
                        mouse_pos = self.pg.mouse.get_pos()
                        if available_bot_list_rect.collidepoint(mouse_pos):
                            list_scroll_offset = max(0, min(max_bot_scroll, list_scroll_offset - event.y * 28))
                    if event.type == self.pg.KEYDOWN:
                        if event.key == self.pg.K_1:
                            tournament_state = tournament_state.with_format(TournamentFormat.FIXED_LINEUP_BATCH.value)
                        elif event.key == self.pg.K_2:
                            tournament_state = tournament_state.with_format(TournamentFormat.ROUND_ROBIN.value)
                        elif event.key == self.pg.K_r:
                            tournament_state = tournament_state.with_seat_rotation_enabled(not tournament_state.seat_rotation_enabled)
                        elif event.key == self.pg.K_j:
                            tournament_state = tournament_state.with_export_json(not tournament_state.export_json)
                        elif event.key == self.pg.K_c:
                            tournament_state = tournament_state.with_export_csv(not tournament_state.export_csv)
                        elif event.key == self.pg.K_MINUS:
                            new_seed_blocks = max(1, int(tournament_state.seed_blocks_text or "1") - 1)
                            tournament_state = tournament_state.with_seed_blocks_text(str(new_seed_blocks))
                        elif event.key == self.pg.K_EQUALS:
                            new_seed_blocks = int(tournament_state.seed_blocks_text or "1") + 1
                            tournament_state = tournament_state.with_seed_blocks_text(str(new_seed_blocks))
                        elif self.pg.K_a <= event.key <= self.pg.K_z:
                            index = event.key - self.pg.K_a
                            if 0 <= index < len(bot_specs):
                                tournament_state = tournament_state.toggle_bot(bot_specs[index].bot_id)
                elif flow_state.screen == AppScreen.BOT_LAB:
                    bot_definitions = list_bot_definitions()
                    list_rect = self.pg.Rect(40, 90, width // 3, height - 180)
                    details_x = width // 3 + 70
                    details_width = width - details_x - 40
                    new_from_selected_rect = self.pg.Rect(details_x, height - 120, min(360, details_width), 42)
                    save_rect = self.pg.Rect(width - 220, height - 120, 180, 42)
                    delete_rect = self.pg.Rect(width - 430, height - 120, 180, 42)
                    detail_panel_rect = self.pg.Rect(details_x, 96, details_width, height - 226)
                    selected_definition = get_bot_definition(selected_lab_bot_id) if selected_lab_bot_id else None
                    if create_form_open:
                        detail_row_height = 42
                        detail_row_count = len(["__name__", "__description__", *new_bot_param_keys])
                    elif selected_definition is not None:
                        detail_row_height = 30
                        detail_row_count = 4 + len(selected_definition.parameters)
                    else:
                        detail_row_height = 30
                        detail_row_count = 0
                    max_rows = max(1, detail_panel_rect.height // detail_row_height)
                    max_detail_scroll = max(0, (detail_row_count - max_rows) * detail_row_height)
                    bot_lab_scroll_offset = max(0, min(bot_lab_scroll_offset, max_detail_scroll))
                    if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                        confirm_rect = self.pg.Rect(width // 2 - 260, height // 2 - 90, 520, 180)
                        confirm_cancel_rect = self.pg.Rect(confirm_rect.x + 34, confirm_rect.bottom - 58, 180, 40)
                        confirm_delete_rect = self.pg.Rect(confirm_rect.right - 214, confirm_rect.bottom - 58, 180, 40)
                        if delete_confirm_open:
                            if confirm_delete_rect.collidepoint(event.pos) and selected_definition is not None and not selected_definition.is_builtin:
                                removed = delete_custom_bot_definition(selected_definition.bot_id)
                                if removed:
                                    bot_definitions = list_bot_definitions()
                                    selected_lab_bot_id = bot_definitions[0].bot_id if bot_definitions else None
                                    create_form_open = False
                                    bot_lab_scroll_offset = 0
                                    bot_lab_error = None
                                else:
                                    bot_lab_error = "Could not delete selected custom bot."
                                delete_confirm_open = False
                            elif confirm_cancel_rect.collidepoint(event.pos) or not confirm_rect.collidepoint(event.pos):
                                delete_confirm_open = False
                            continue
                        if back_rect.collidepoint(event.pos):
                            flow_state = flow_state.back_to_menu()
                            create_form_open = False
                            bot_lab_error = None
                            delete_confirm_open = False
                            continue
                        if list_rect.collidepoint(event.pos):
                            row = (event.pos[1] - list_rect.y) // 38
                            if 0 <= row < len(bot_definitions):
                                selected_lab_bot_id = bot_definitions[row].bot_id
                                bot_lab_scroll_offset = 0
                            continue
                        if new_from_selected_rect.collidepoint(event.pos) and selected_lab_bot_id is not None:
                            base = get_bot_definition(selected_lab_bot_id)
                            if base is not None:
                                create_form_open = True
                                new_bot_name = f"{base.display_name} Copy"
                                new_bot_description = base.description
                                new_bot_parameters = {key: str(value) for key, value in base.parameters.items()}
                                new_bot_param_keys = list(new_bot_parameters.keys())
                                selected_new_bot_field_idx = 0
                                bot_lab_scroll_offset = 0
                                bot_lab_error = None
                            continue
                        if create_form_open and detail_panel_rect.collidepoint(event.pos):
                            editable_fields = ["__name__", "__description__", *new_bot_param_keys]
                            clicked_row = (event.pos[1] - detail_panel_rect.y + bot_lab_scroll_offset) // 42
                            if 0 <= clicked_row < len(editable_fields):
                                selected_new_bot_field_idx = int(clicked_row)
                            continue
                        if create_form_open and save_rect.collidepoint(event.pos):
                            try:
                                base_definition = get_bot_definition(selected_lab_bot_id or "")
                                if base_definition is None:
                                    raise ValueError("Selected base bot is missing.")
                                raw_params: dict[str, float | int | str | bool] = {}
                                for key, value in new_bot_parameters.items():
                                    raw_params[key] = value.strip()
                                parsed_params = merge_with_family_defaults(base_definition.base_controller_type, raw_params)
                                create_custom_bot_definition(
                                    name=new_bot_name,
                                    base_bot_id=selected_lab_bot_id or "",
                                    description=new_bot_description,
                                    parameters=parsed_params,
                                )
                                create_form_open = False
                                bot_lab_scroll_offset = 0
                                bot_lab_error = None
                            except ValueError as exc:
                                bot_lab_error = str(exc)
                        if (not create_form_open) and delete_rect.collidepoint(event.pos) and selected_definition is not None:
                            if selected_definition.is_builtin:
                                bot_lab_error = "Built-in bots cannot be deleted."
                            else:
                                delete_confirm_open = True
                                bot_lab_error = None
                    if event.type == self.pg.MOUSEWHEEL:
                        mouse_pos = self.pg.mouse.get_pos()
                        if (not delete_confirm_open) and detail_panel_rect.collidepoint(mouse_pos):
                            bot_lab_scroll_offset = max(0, min(max_detail_scroll, bot_lab_scroll_offset - event.y * 26))
                    if create_form_open and (not delete_confirm_open) and event.type == self.pg.KEYDOWN:
                        editable_fields = ["__name__", "__description__", *new_bot_param_keys]
                        visible_row_height = 42
                        if event.key in (self.pg.K_TAB, self.pg.K_DOWN):
                            selected_new_bot_field_idx = min(len(editable_fields) - 1, selected_new_bot_field_idx + 1)
                            target_top = selected_new_bot_field_idx * visible_row_height
                            target_bottom = target_top + visible_row_height
                            if target_bottom - bot_lab_scroll_offset > detail_panel_rect.height:
                                bot_lab_scroll_offset = target_bottom - detail_panel_rect.height
                            continue
                        if event.key == self.pg.K_UP:
                            selected_new_bot_field_idx = max(0, selected_new_bot_field_idx - 1)
                            target_top = selected_new_bot_field_idx * visible_row_height
                            if target_top < bot_lab_scroll_offset:
                                bot_lab_scroll_offset = target_top
                            continue
                        if event.key == self.pg.K_PAGEDOWN:
                            bot_lab_scroll_offset = min(max_detail_scroll, bot_lab_scroll_offset + detail_panel_rect.height // 2)
                            continue
                        if event.key == self.pg.K_PAGEUP:
                            bot_lab_scroll_offset = max(0, bot_lab_scroll_offset - detail_panel_rect.height // 2)
                            continue
                        selected_field = editable_fields[selected_new_bot_field_idx] if editable_fields else "__name__"
                        if selected_field == "__name__":
                            if event.key == self.pg.K_BACKSPACE:
                                new_bot_name = new_bot_name[:-1]
                            elif event.unicode and event.unicode.isprintable():
                                new_bot_name += event.unicode
                        elif selected_field == "__description__":
                            if event.key == self.pg.K_BACKSPACE:
                                new_bot_description = new_bot_description[:-1]
                            elif event.unicode and event.unicode.isprintable():
                                new_bot_description += event.unicode
                        else:
                            if event.key == self.pg.K_BACKSPACE:
                                new_bot_parameters[selected_field] = new_bot_parameters[selected_field][:-1]
                            elif event.unicode and event.unicode.isprintable():
                                new_bot_parameters[selected_field] += event.unicode
                    elif (not create_form_open) and (not delete_confirm_open) and event.type == self.pg.KEYDOWN and selected_definition is not None:
                        if event.key in (self.pg.K_PAGEDOWN, self.pg.K_DOWN):
                            bot_lab_scroll_offset = min(max_detail_scroll, bot_lab_scroll_offset + detail_panel_rect.height // 3)
                        elif event.key in (self.pg.K_PAGEUP, self.pg.K_UP):
                            bot_lab_scroll_offset = max(0, bot_lab_scroll_offset - detail_panel_rect.height // 3)

            screen.fill((20, 20, 28))
            if flow_state.screen == AppScreen.MAIN_MENU:
                title = "Main Menu"
            elif flow_state.screen == AppScreen.GAME_SETUP:
                title = "Game Setup"
            elif flow_state.screen == AppScreen.TOURNAMENT_SETUP:
                title = "Tournament / Simulation"
            else:
                title = "Bot Lab v1"
            screen.blit(font.render(title, True, (240, 240, 240)), (title_rect.x, title_rect.y))
            if flow_state.screen == AppScreen.MAIN_MENU:
                self.pg.draw.rect(screen, (70, 120, 70), new_game_rect)
                self.pg.draw.rect(screen, (70, 90, 130), tournament_rect)
                self.pg.draw.rect(screen, (100, 86, 150), bot_lab_rect)
                self.pg.draw.rect(screen, (120, 70, 70), quit_rect)
                screen.blit(font.render("New Game", True, (255, 255, 255)), (new_game_rect.x + 45, new_game_rect.y + 8))
                screen.blit(small_font.render("Tournament / Simulation", True, (255, 255, 255)), (tournament_rect.x + 15, tournament_rect.y + 12))
                screen.blit(small_font.render("Bot Lab v1", True, (255, 255, 255)), (bot_lab_rect.x + 70, bot_lab_rect.y + 12))
                screen.blit(font.render("Quit", True, (255, 255, 255)), (quit_rect.x + 85, quit_rect.y + 8))
            elif flow_state.screen == AppScreen.GAME_SETUP:
                screen.blit(small_font.render("Configured Players", True, (220, 220, 235)), (left_slots_x, 85))
                for idx, rect in enumerate(slot_rects):
                    slot_controller = flow_state.slot_controller(idx)
                    filled = slot_controller is not None
                    self.pg.draw.rect(screen, (60, 60, 90) if filled else (42, 42, 64), rect, border_radius=8)
                    self.pg.draw.rect(screen, (90, 100, 136), rect, 1, border_radius=8)
                    label = (
                        f"Player {idx + 1}: {controller_label(slot_controller)}"
                        if filled and slot_controller is not None
                        else f"Player {idx + 1}: (empty)"
                    )
                    screen.blit(small_font.render(label, True, (255, 255, 255) if filled else (180, 180, 200)), (rect.x + 10, rect.y + 21))
                    if filled:
                        remove_rect = remove_rects[idx]
                        self.pg.draw.rect(screen, (150, 70, 70), remove_rect, border_radius=4)
                        screen.blit(small_font.render("X", True, (255, 255, 255)), (remove_rect.x + 5, remove_rect.y - 1))
                add_color = (80, 130, 80) if flow_state.can_add_player() else (75, 75, 75)
                self.pg.draw.rect(screen, add_color, arrow_rect, border_radius=8)
                screen.blit(font.render("←", True, (255, 255, 255)), (arrow_rect.x + 20, arrow_rect.y + 6))
                screen.blit(small_font.render("Player Types", True, (220, 220, 235)), (list_rect.x, 85))
                self.pg.draw.rect(screen, (35, 35, 52), list_rect, border_radius=8)
                self.pg.draw.rect(screen, (90, 100, 136), list_rect, 1, border_radius=8)
                clip_before = screen.get_clip()
                screen.set_clip(list_rect)
                for option_idx, controller_type in enumerate(available_types):
                    option_y = list_rect.y + option_idx * (list_entry_height + list_entry_gap) - list_scroll_offset
                    option_rect = self.pg.Rect(list_rect.x + 6, option_y, list_rect.width - 12, list_entry_height)
                    is_selected = controller_type == flow_state.selected_controller
                    if option_rect.bottom < list_rect.y or option_rect.y > list_rect.bottom:
                        continue
                    self.pg.draw.rect(screen, (82, 110, 98) if is_selected else (58, 58, 86), option_rect, border_radius=6)
                    border_color = (166, 220, 188) if is_selected else (80, 84, 120)
                    self.pg.draw.rect(screen, border_color, option_rect, 2 if is_selected else 1, border_radius=6)
                    screen.blit(small_font.render(controller_label(controller_type), True, (248, 248, 248)), (option_rect.x + 10, option_rect.y + 13))
                screen.set_clip(clip_before)
                self.pg.draw.rect(screen, (80, 80, 120), seed_slider_rect, border_radius=18)
                slider_mid_x = seed_slider_rect.centerx
                self.pg.draw.line(
                    screen,
                    (120, 120, 160),
                    (slider_mid_x, seed_slider_rect.y + 5),
                    (slider_mid_x, seed_slider_rect.bottom - 5),
                    2,
                )
                knob_width = seed_slider_rect.width // 2
                knob_x = seed_slider_rect.x if flow_state.use_random_seed else slider_mid_x
                knob_rect = self.pg.Rect(knob_x, seed_slider_rect.y, knob_width, seed_slider_rect.height)
                self.pg.draw.rect(screen, (110, 160, 110), knob_rect, border_radius=18)
                screen.blit(
                    small_font.render("Random seed", True, (255, 255, 255)),
                    (seed_slider_rect.x + 16, seed_slider_rect.y + 7),
                )
                screen.blit(
                    small_font.render("Fixed seed", True, (255, 255, 255)),
                    (slider_mid_x + 16, seed_slider_rect.y + 7),
                )
                self.pg.draw.rect(screen, (40, 40, 60), seed_input_rect)
                seed_text = flow_state.fixed_seed_text if flow_state.fixed_seed_text else "(enter number)"
                screen.blit(small_font.render(f"Seed: {seed_text}", True, (240, 240, 240)), (seed_input_rect.x + 10, seed_input_rect.y + 10))
                start_color = (70, 120, 70) if flow_state.can_start_game() else (80, 80, 80)
                self.pg.draw.rect(screen, (90, 90, 90), back_rect)
                self.pg.draw.rect(screen, start_color, start_rect)
                screen.blit(small_font.render("Back", True, (255, 255, 255)), (back_rect.x + 55, back_rect.y + 10))
                screen.blit(small_font.render("Start Game", True, (255, 255, 255)), (start_rect.x + 35, start_rect.y + 10))
                if not flow_state.can_start_game():
                    msg = "Add at least 2 players and use a valid fixed seed."
                    screen.blit(small_font.render(msg, True, (220, 130, 130)), (60, height - 125))
            else:
                if flow_state.screen == AppScreen.BOT_LAB:
                    bot_definitions = list_bot_definitions()
                    self.pg.draw.rect(screen, (35, 35, 52), (40, 90, width // 3, height - 180), border_radius=8)
                    y = 100
                    for definition in bot_definitions:
                        is_selected = definition.bot_id == selected_lab_bot_id
                        row_rect = self.pg.Rect(50, y, width // 3 - 20, 34)
                        self.pg.draw.rect(screen, (82, 110, 98) if is_selected else (58, 58, 86), row_rect, border_radius=6)
                        tag = "built-in" if definition.is_builtin else "custom"
                        screen.blit(small_font.render(f"{definition.display_name} ({tag})", True, (248, 248, 248)), (58, y + 6))
                        y += 38
                    selected_definition = get_bot_definition(selected_lab_bot_id) if selected_lab_bot_id else None
                    details_x = width // 3 + 70
                    details_width = width - details_x - 40
                    detail_panel_rect = self.pg.Rect(details_x, 96, details_width, height - 226)
                    self.pg.draw.rect(screen, (30, 40, 58), detail_panel_rect, border_radius=8)
                    self.pg.draw.rect(screen, (90, 100, 136), detail_panel_rect, 1, border_radius=8)
                    if selected_definition is not None:
                        if create_form_open:
                            form_rows = [
                                ("New Bot Name", new_bot_name),
                                ("Description", new_bot_description),
                            ] + [(key, new_bot_parameters.get(key, "")) for key in new_bot_param_keys]
                            row_height = 42
                            max_rows = max(1, detail_panel_rect.height // row_height)
                            max_detail_scroll = max(0, (len(form_rows) - max_rows) * row_height)
                            bot_lab_scroll_offset = max(0, min(bot_lab_scroll_offset, max_detail_scroll))
                            instruction = "Edit selected row. TAB/UP/DOWN to move, mouse wheel to scroll."
                            screen.blit(small_font.render(instruction, True, (190, 210, 230)), (details_x + 10, 68))
                            clip_before = screen.get_clip()
                            screen.set_clip(detail_panel_rect)
                            for idx, (label, value) in enumerate(form_rows):
                                row_y = detail_panel_rect.y + idx * row_height - bot_lab_scroll_offset
                                row_rect = self.pg.Rect(detail_panel_rect.x + 8, row_y, detail_panel_rect.width - 16, row_height - 6)
                                if row_rect.bottom < detail_panel_rect.y or row_rect.y > detail_panel_rect.bottom:
                                    continue
                                is_selected = idx == selected_new_bot_field_idx
                                self.pg.draw.rect(screen, (78, 108, 138) if is_selected else (48, 62, 86), row_rect, border_radius=6)
                                text = f"{label}: {value}"
                                screen.blit(
                                    small_font.render(text, True, (255, 255, 255) if is_selected else (220, 230, 240)),
                                    (row_rect.x + 10, row_rect.y + 10),
                                )
                            screen.set_clip(clip_before)
                        else:
                            details = [
                                f"Name: {selected_definition.display_name}",
                                f"Base type: {selected_definition.base_controller_type.value}",
                                f"Description: {selected_definition.description or '(none)'}",
                                "Parameters:",
                            ] + [f"  - {key}: {value}" for key, value in selected_definition.parameters.items()]
                            instruction = "Mouse wheel / ↑↓ / PageUp PageDown to scroll."
                            screen.blit(small_font.render(instruction, True, (190, 210, 230)), (details_x + 10, 68))
                            clip_before = screen.get_clip()
                            screen.set_clip(detail_panel_rect)
                            row_y = detail_panel_rect.y + 10 - bot_lab_scroll_offset
                            for line in details:
                                screen.blit(small_font.render(line, True, (220, 220, 235)), (details_x + 10, row_y))
                                row_y += 30
                            screen.set_clip(clip_before)
                    new_from_selected_rect = self.pg.Rect(details_x, height - 120, min(360, details_width), 42)
                    self.pg.draw.rect(screen, (70, 90, 130), new_from_selected_rect, border_radius=8)
                    screen.blit(small_font.render("New Bot (based on selected bot)", True, (255, 255, 255)), (details_x + 12, height - 110))
                    if create_form_open:
                        save_rect = self.pg.Rect(width - 220, height - 120, 180, 42)
                        self.pg.draw.rect(screen, (70, 120, 70), save_rect, border_radius=8)
                        screen.blit(small_font.render("Save New Bot", True, (255, 255, 255)), (width - 200, height - 110))
                    elif selected_definition is not None:
                        delete_rect = self.pg.Rect(width - 430, height - 120, 180, 42)
                        can_delete = not selected_definition.is_builtin
                        self.pg.draw.rect(screen, (150, 70, 70) if can_delete else (90, 90, 90), delete_rect, border_radius=8)
                        delete_label = "Delete Bot" if can_delete else "Built-in locked"
                        screen.blit(small_font.render(delete_label, True, (255, 255, 255)), (delete_rect.x + 22, delete_rect.y + 10))
                    if bot_lab_error:
                        screen.blit(small_font.render(bot_lab_error, True, (240, 140, 140)), (details_x, height - 145))
                    if delete_confirm_open and selected_definition is not None and not selected_definition.is_builtin:
                        overlay = self.pg.Surface((width, height), self.pg.SRCALPHA)
                        overlay.fill((0, 0, 0, 120))
                        screen.blit(overlay, (0, 0))
                        confirm_rect = self.pg.Rect(width // 2 - 260, height // 2 - 90, 520, 180)
                        confirm_cancel_rect = self.pg.Rect(confirm_rect.x + 34, confirm_rect.bottom - 58, 180, 40)
                        confirm_delete_rect = self.pg.Rect(confirm_rect.right - 214, confirm_rect.bottom - 58, 180, 40)
                        self.pg.draw.rect(screen, (36, 42, 62), confirm_rect, border_radius=10)
                        self.pg.draw.rect(screen, (90, 100, 136), confirm_rect, 1, border_radius=10)
                        screen.blit(small_font.render("Delete selected bot?", True, (245, 245, 245)), (confirm_rect.x + 20, confirm_rect.y + 20))
                        bot_name = selected_definition.display_name[:42]
                        screen.blit(
                            small_font.render(f"'{bot_name}' will be permanently removed.", True, (220, 220, 235)),
                            (confirm_rect.x + 20, confirm_rect.y + 60),
                        )
                        self.pg.draw.rect(screen, (90, 90, 90), confirm_cancel_rect, border_radius=8)
                        self.pg.draw.rect(screen, (160, 70, 70), confirm_delete_rect, border_radius=8)
                        screen.blit(small_font.render("Cancel", True, (255, 255, 255)), (confirm_cancel_rect.x + 56, confirm_cancel_rect.y + 9))
                        screen.blit(small_font.render("Yes, delete", True, (255, 255, 255)), (confirm_delete_rect.x + 42, confirm_delete_rect.y + 9))
                    self.pg.draw.rect(screen, (90, 90, 90), back_rect)
                    screen.blit(small_font.render("Back", True, (255, 255, 255)), (back_rect.x + 55, back_rect.y + 10))
                else:
                    bot_specs = list_bot_definitions()
                    if tournament_state.selected_bot is None and bot_specs:
                        tournament_state = tournament_state.with_selected_bot(bot_specs[0].bot_id)
                    configured_bot_slots = [self.pg.Rect(60, 140 + idx * 56, 360, 46) for idx in range(8)]
                    remove_bot_rects = {
                        idx: self.pg.Rect(slot.right - 30, slot.y + 10, 24, 24) for idx, slot in enumerate(configured_bot_slots)
                    }
                    add_bot_rect = self.pg.Rect(448, 228, 64, 52)
                    available_bot_list_rect = self.pg.Rect(540, 140, width - 600, 360)
                    option_height = 44
                    option_gap = 8
                    screen.blit(small_font.render("Tournament Bots", True, (220, 220, 235)), (60, 100))
                    for idx, slot_rect in enumerate(configured_bot_slots):
                        slot_bot = tournament_state.selected_bots[idx] if idx < len(tournament_state.selected_bots) else None
                        filled = slot_bot is not None
                        self.pg.draw.rect(screen, (60, 60, 90) if filled else (42, 42, 64), slot_rect, border_radius=8)
                        self.pg.draw.rect(screen, (90, 100, 136), slot_rect, 1, border_radius=8)
                        label = f"Bot {idx + 1}: {controller_label(slot_bot)}" if filled else f"Bot {idx + 1}: (empty)"
                        screen.blit(small_font.render(label, True, (255, 255, 255) if filled else (180, 180, 200)), (slot_rect.x + 10, slot_rect.y + 12))
                        if filled:
                            remove_rect = remove_bot_rects[idx]
                            self.pg.draw.rect(screen, (150, 70, 70), remove_rect, border_radius=4)
                            screen.blit(small_font.render("X", True, (255, 255, 255)), (remove_rect.x + 6, remove_rect.y - 1))
                    self.pg.draw.rect(screen, (80, 130, 80), add_bot_rect, border_radius=8)
                    screen.blit(font.render("←", True, (255, 255, 255)), (add_bot_rect.x + 20, add_bot_rect.y + 5))
                    screen.blit(small_font.render("Bot List", True, (220, 220, 235)), (available_bot_list_rect.x, 100))
                    self.pg.draw.rect(screen, (35, 35, 52), available_bot_list_rect, border_radius=8)
                    self.pg.draw.rect(screen, (90, 100, 136), available_bot_list_rect, 1, border_radius=8)
                    clip_before = screen.get_clip()
                    screen.set_clip(available_bot_list_rect)
                    for option_idx, spec in enumerate(bot_specs):
                        option_y = available_bot_list_rect.y + option_idx * (option_height + option_gap) - list_scroll_offset
                        option_rect = self.pg.Rect(available_bot_list_rect.x + 6, option_y, available_bot_list_rect.width - 12, option_height)
                        if option_rect.bottom < available_bot_list_rect.y or option_rect.y > available_bot_list_rect.bottom:
                            continue
                        is_selected = spec.bot_id == tournament_state.selected_bot
                        self.pg.draw.rect(screen, (82, 110, 98) if is_selected else (58, 58, 86), option_rect, border_radius=6)
                        border_color = (166, 220, 188) if is_selected else (80, 84, 120)
                        self.pg.draw.rect(screen, border_color, option_rect, 2 if is_selected else 1, border_radius=6)
                        screen.blit(small_font.render(spec.display_name, True, (248, 248, 248)), (option_rect.x + 10, option_rect.y + 10))
                    screen.set_clip(clip_before)
                    fixed_format_rect = self.pg.Rect(60, height - 245, 220, 40)
                    round_robin_rect = self.pg.Rect(290, height - 245, 180, 40)
                    self.pg.draw.rect(
                        screen,
                        (82, 110, 98) if tournament_state.format == TournamentFormat.FIXED_LINEUP_BATCH.value else (58, 58, 86),
                        fixed_format_rect,
                        border_radius=8,
                    )
                    self.pg.draw.rect(
                        screen,
                        (82, 110, 98) if tournament_state.format == TournamentFormat.ROUND_ROBIN.value else (58, 58, 86),
                        round_robin_rect,
                        border_radius=8,
                    )
                    screen.blit(small_font.render("Fixed Lineup Batch", True, (255, 255, 255)), (fixed_format_rect.x + 18, fixed_format_rect.y + 10))
                    screen.blit(small_font.render("Round Robin", True, (255, 255, 255)), (round_robin_rect.x + 32, round_robin_rect.y + 10))
                    seat_rotation_rect = self.pg.Rect(60, height - 195, 180, 38)
                    export_json_rect = self.pg.Rect(250, height - 195, 170, 38)
                    export_excel_rect = self.pg.Rect(430, height - 195, 170, 38)
                    self._draw_toggle_button(screen, small_font, seat_rotation_rect, "Seat Rotation", tournament_state.seat_rotation_enabled)
                    self._draw_toggle_button(screen, small_font, export_json_rect, "Export JSON", tournament_state.export_json)
                    self._draw_toggle_button(screen, small_font, export_excel_rect, "Export Excel", tournament_state.export_csv)
                    seed_minus_rect = self.pg.Rect(60, height - 145, 42, 36)
                    seed_plus_rect = self.pg.Rect(236, height - 145, 42, 36)
                    self.pg.draw.rect(screen, (70, 80, 100), seed_minus_rect, border_radius=6)
                    self.pg.draw.rect(screen, (70, 80, 100), seed_plus_rect, border_radius=6)
                    screen.blit(font.render("-", True, (255, 255, 255)), (seed_minus_rect.x + 12, seed_minus_rect.y - 1))
                    screen.blit(font.render("+", True, (255, 255, 255)), (seed_plus_rect.x + 9, seed_plus_rect.y - 3))
                    screen.blit(
                        small_font.render(f"Seed Blocks: {tournament_state.seed_blocks_text}", True, (220, 220, 235)),
                        (112, height - 138),
                    )
                    start_color = (70, 120, 70) if tournament_state.to_tournament_config() is not None else (80, 80, 80)
                    self.pg.draw.rect(screen, (90, 90, 90), back_rect)
                    self.pg.draw.rect(screen, start_color, start_rect)
                    screen.blit(small_font.render("Back", True, (255, 255, 255)), (back_rect.x + 55, back_rect.y + 10))
                    screen.blit(small_font.render("Run Tournament", True, (255, 255, 255)), (start_rect.x + 20, start_rect.y + 10))
                    if tournament_state.to_tournament_config() is None:
                        help_text = (
                            "Fixed lineup needs at least 1 bot. Round robin needs at least 4 bots."
                            if tournament_state.format == TournamentFormat.ROUND_ROBIN.value
                            else "Select at least 1 bot to run a fixed lineup tournament."
                        )
                        screen.blit(small_font.render(help_text, True, (220, 130, 130)), (60, height - 98))
                    if tournament_summary_lines:
                        y = max(520, height // 2)
                        screen.blit(small_font.render("Summary:", True, (240, 240, 240)), (60, y))
                        y += 30
                        for line in tournament_summary_lines[:10]:
                            screen.blit(small_font.render(line, True, (200, 220, 200)), (60, y))
                            y += 24

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
        settings_menu_open = False
        settings_delay_input = self._format_bot_delay_input(self._current_bot_delay_seconds(controllers))
        settings_delay_error: str | None = None
        spectator_mode = self._is_spectator_mode(state, controllers)
        spectator_speed = 1.0
        base_bot_delay = self._current_bot_delay_seconds(controllers)
        spectator_decision_ui = {"fallback_message": "Waiting for bot decision..."}
        show_game_over_overlay = True
        self.return_to_main_menu = False

        running = True
        while running:
            board_center, board_radius = self._board_center_and_radius(screen)
            layout = build_circular_layout(state.board, center=board_center, radius=board_radius)

            active_player = self._active_player(state)
            hand_view_player = self._hand_view_player(state, active_player, controllers)
            discard_selection_player = self._sync_discard_selection(
                state,
                active_player,
                discard_selection,
                discard_selection_player,
            )
            legal = get_legal_actions(state, active_player) if active_player is not None else []
            render_legal = legal
            if active_player is not None and active_player in controllers:
                if not isinstance(controllers[active_player], HumanController):
                    render_legal = []
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
            effective_build_mode = self._effective_build_mode(state, build_mode)

            drawn = renderer.render(
                screen,
                state,
                layout,
                render_legal,
                active_player,
                event_log,
                selected_action_text,
                hover,
                last_applied_action,
                self.fullscreen,
                build_mode=effective_build_mode,
                trade_ui=trade_ui,
                discard_ui=discard_ui,
                dev_card_ui=dev_card_ui,
                event_log_offset=event_log_offset,
                hand_view_player=hand_view_player,
                spectator_mode=spectator_mode,
                spectator_data={**spectator_decision_ui, "speed": spectator_speed},
                show_game_over_overlay=show_game_over_overlay,
            )
            settings_ui = self._draw_settings_ui(
                screen,
                menu_open=settings_menu_open,
                bot_delay_input=settings_delay_input,
                delay_error=settings_delay_error,
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
                if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1:
                    if drawn.game_over_menu_button_rect is not None and drawn.game_over_menu_button_rect.collidepoint(event.pos):
                        self.return_to_main_menu = True
                        running = False
                        continue
                    if (
                        drawn.game_over_view_board_button_rect is not None
                        and drawn.game_over_view_board_button_rect.collidepoint(event.pos)
                    ):
                        show_game_over_overlay = False
                        continue
                    if spectator_mode:
                        selected_speed = self._match_speed_button(event.pos, drawn.speed_button_rects)
                        if selected_speed is not None:
                            spectator_speed = selected_speed
                            if selected_speed > 0:
                                self._apply_bot_delay(controllers, base_bot_delay / selected_speed)
                            event_log.append(f"[{action_counter:03d}] spectator speed {'pause' if selected_speed == 0 else f'{int(selected_speed)}x'}")
                            continue
                    settings_click = self._handle_settings_click(event.pos, settings_ui, settings_menu_open)
                    if settings_click == "toggle":
                        settings_menu_open = not settings_menu_open
                        continue
                    if settings_click == "quit_menu":
                        self.return_to_main_menu = True
                        running = False
                        continue
                    if settings_click == "quit_desktop":
                        self.return_to_main_menu = False
                        running = False
                        continue
                    if settings_click == "apply_delay":
                        parsed_delay = self._parse_bot_delay_input(settings_delay_input)
                        if parsed_delay is None:
                            settings_delay_error = "Invalid delay (use 0.0 or higher)."
                        else:
                            updated = self._apply_bot_delay(controllers, parsed_delay)
                            if updated:
                                settings_delay_error = None
                                settings_delay_input = self._format_bot_delay_input(parsed_delay)
                                event_log.append(f"[{action_counter:03d}] bot delay set to {parsed_delay:.2f}s")
                            else:
                                settings_delay_error = "No bot controllers found."
                        continue
                    if settings_click == "menu":
                        continue
                    if settings_menu_open:
                        settings_menu_open = False
                        continue
                if settings_menu_open and event.type == self.pg.KEYDOWN:
                    if event.key == self.pg.K_BACKSPACE:
                        settings_delay_input = settings_delay_input[:-1]
                        settings_delay_error = None
                    elif event.unicode in "0123456789.":
                        if not (event.unicode == "." and "." in settings_delay_input):
                            settings_delay_input += event.unicode
                            settings_delay_error = None

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
                            selected_action_text = self._action_label(discard_action, state) if spectator_mode else str(discard_action)
                            active_controller.submit_action_intent(discard_action)
                        continue
                    if dev_card_ui is not None:
                        dev_flow_action = self._handle_dev_card_overlay_click(event.pos, dev_card_ui, active_player, legal, year_of_plenty_selected)
                        if dev_flow_action is not None:
                            selected_action_text = self._action_label(dev_flow_action, state) if spectator_mode else str(dev_flow_action)
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
                        effective_build_mode,
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
                        selected_action_text = self._action_label(clicked_action, state) if spectator_mode else str(clicked_action)
                        active_controller.submit_action_intent(clicked_action)
                        continue
                    dev_click_action = self._dev_card_click_action(event.pos, drawn.dev_card_rects, legal)
                    if dev_click_action is not None:
                        selected_action_text = self._action_label(dev_click_action, state) if spectator_mode else str(dev_click_action)
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
                            selected_action_text = self._action_label(trade_action, state) if spectator_mode else str(trade_action)
                            active_controller.submit_action_intent(trade_action)
                            trade_window_open = False
                            trade_draft_offered = {r: 0 for r in ResourceType}
                            trade_draft_requested = {r: 0 for r in ResourceType}
                            continue
                    if state.player_trade is not None and trade_ui is not None:
                        player_trade_action = self._handle_player_trade_overlay_click(event.pos, trade_ui, state, active_player)
                        if player_trade_action is not None:
                            selected_action_text = self._action_label(player_trade_action, state) if spectator_mode else str(player_trade_action)
                            active_controller.submit_action_intent(player_trade_action)
                            continue

                if is_human and state.turn and state.turn.step == TurnStep.DISCARD:
                    discard_action = self._handle_discard_event(event, state, active_player, discard_selection)
                    if discard_action is not None:
                        selected_action_text = self._action_label(discard_action, state) if spectator_mode else str(discard_action)
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
                        selected_action_text = self._action_label(bank_trade_action, state) if spectator_mode else str(bank_trade_action)
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
                    if not self._is_board_action_allowed(mapped.action, effective_build_mode):
                        continue
                    selected_action_text = self._action_label(mapped.action, state) if spectator_mode else str(mapped.action)
                    active_controller.submit_action_intent(mapped.action)
                    if isinstance(mapped.action, (BuildRoad, BuildSettlement, BuildCity)):
                        build_mode = None
                    if mapped.status:
                        event_log.append(f"[{action_counter:03d}] P{active_player} {mapped.status}")

            if active_player is not None and active_player in controllers:
                if spectator_mode and spectator_speed == 0 and not isinstance(controllers[active_player], HumanController):
                    self.pg.display.flip()
                    clock.tick(30)
                    continue
                before = state
                state = self.runner.tick(state, controllers[active_player], active_player)
                if spectator_mode and not isinstance(controllers[active_player], HumanController):
                    spectator_decision_ui = self._spectator_decision_ui(controllers[active_player], before)
                if state != before:
                    action_counter += 1
                    if spectator_mode and not isinstance(controllers[active_player], HumanController):
                        last_applied_action = spectator_decision_ui.get("chosen_line") or selected_action_text or "action"
                    else:
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

    def _is_spectator_mode(self, state: GameState, controllers: Mapping[int, Controller]) -> bool:
        return len(state.players) == 4 and all(not isinstance(controllers.get(pid), HumanController) for pid in state.players)

    def _match_speed_button(self, pos: tuple[int, int], speed_rects: dict[float, object]) -> float | None:
        for speed, rect in speed_rects.items():
            if rect.collidepoint(pos):
                return float(speed)
        return None

    def _spectator_decision_ui(self, controller: Controller, state: GameState) -> dict[str, object]:
        getter = getattr(controller, "get_last_decision", None)
        if not callable(getter):
            return {"fallback_message": "No bot explanation data available"}
        payload = getter()
        if not isinstance(payload, dict):
            return {"fallback_message": "No bot explanation data available"}
        chosen = payload.get("chosen_action")
        chosen_line = self._action_label(chosen, state) if chosen is not None else None
        top_candidates = payload.get("top_candidates")
        if isinstance(top_candidates, list):
            formatted: list[str] = []
            for candidate in top_candidates[:3]:
                if not isinstance(candidate, tuple) or len(candidate) != 2:
                    continue
                action, score = candidate
                if not isinstance(score, (int, float)):
                    continue
                formatted.append(f"{self._action_label(action, state):<24} {score:+.2f}")
            if formatted:
                return {"chosen_line": chosen_line, "candidate_lines": formatted}
        return {
            "chosen_line": chosen_line,
            "fallback_message": str(payload.get("message", f"Random choice from {payload.get('legal_action_count', '?')} legal actions")),
        }

    def _action_label(self, action: object, state: GameState) -> str:
        if isinstance(action, (BuildSettlement, PlaceSetupSettlement)):
            return f"Settlement {self._node_token_label(state, action.node_id)}"
        if isinstance(action, (BuildRoad, PlaceSetupRoad)):
            return f"Road toward {self._road_toward_label(state, action.edge_id)}"
        if isinstance(action, MoveRobber):
            return f"Robber → {self._robber_tile_label(state, action.tile_id)}"
        return str(action)

    def _node_token_label(self, state: GameState, node_id: int) -> str:
        tile_ids = state.board.node_to_adjacent_tiles.get(node_id, ())
        token_by_tile = {tile.id: tile.number_token for tile in state.board.tiles}
        tokens = [token_by_tile.get(tile_id) for tile_id in tile_ids if token_by_tile.get(tile_id) is not None]
        if not tokens:
            return "coast"
        return "-".join(str(token) for token in tokens)

    def _road_toward_label(self, state: GameState, edge_id: int) -> str:
        node_a, node_b = state.board.edge_to_adjacent_nodes.get(edge_id, (None, None))
        if node_a is None or node_b is None:
            return "unknown"
        label_a = self._node_token_label(state, node_a)
        label_b = self._node_token_label(state, node_b)
        return label_a if len(label_a) >= len(label_b) else label_b

    def _robber_tile_label(self, state: GameState, tile_id: int) -> str:
        tile = next((tile for tile in state.board.tiles if tile.id == tile_id), None)
        if tile is None:
            return "unknown"
        number = tile.number_token if tile.number_token is not None else "Desert"
        return f"{number} ({self._terrain_resource(tile.terrain)})"

    def _terrain_resource(self, terrain: TerrainType) -> str:
        mapping = {
            TerrainType.HILLS: "Brick",
            TerrainType.FOREST: "Lumber",
            TerrainType.PASTURE: "Sheep",
            TerrainType.FIELDS: "Wheat",
            TerrainType.MOUNTAINS: "Ore",
            TerrainType.DESERT: "Desert",
        }
        return mapping.get(terrain, terrain.name.title())

    def _draw_settings_ui(
        self,
        screen,
        *,
        menu_open: bool,
        bot_delay_input: str,
        delay_error: str | None,
    ) -> dict[str, object]:
        small_font = self.pg.font.SysFont("arial", 18)
        width, _ = screen.get_size()
        settings_rect = self.pg.Rect(width - 52, 12, 40, 40)
        self.pg.draw.rect(screen, (60, 60, 70), settings_rect, border_radius=8)
        self._draw_settings_gear(screen, settings_rect)
        ui: dict[str, object] = {"settings_button_rect": settings_rect}
        if not menu_open:
            return ui
        menu_rect = self.pg.Rect(width - 312, 58, 300, 170)
        self.pg.draw.rect(screen, (42, 42, 50), menu_rect, border_radius=8)
        self.pg.draw.rect(screen, (80, 80, 95), menu_rect, width=1, border_radius=8)
        delay_label_rect = self.pg.Rect(menu_rect.x + 12, menu_rect.y + 10, menu_rect.width - 24, 22)
        delay_input_rect = self.pg.Rect(menu_rect.x + 12, menu_rect.y + 34, 160, 30)
        delay_apply_rect = self.pg.Rect(delay_input_rect.right + 10, delay_input_rect.y, 106, 30)
        to_menu_rect = self.pg.Rect(menu_rect.x + 12, menu_rect.y + 86, menu_rect.width - 24, 34)
        to_desktop_rect = self.pg.Rect(menu_rect.x + 12, menu_rect.y + 124, menu_rect.width - 24, 34)
        self.pg.draw.rect(screen, (62, 62, 74), delay_input_rect, border_radius=5)
        self.pg.draw.rect(screen, (88, 114, 90), delay_apply_rect, border_radius=5)
        self.pg.draw.rect(screen, (88, 114, 90), to_menu_rect, border_radius=5)
        self.pg.draw.rect(screen, (110, 78, 78), to_desktop_rect, border_radius=5)
        screen.blit(small_font.render("Bot turn delay (seconds)", True, (245, 245, 245)), (delay_label_rect.x, delay_label_rect.y))
        screen.blit(small_font.render(bot_delay_input or "0.0", True, (238, 238, 238)), (delay_input_rect.x + 9, delay_input_rect.y + 6))
        screen.blit(small_font.render("Apply", True, (245, 245, 245)), (delay_apply_rect.x + 29, delay_apply_rect.y + 6))
        screen.blit(small_font.render("Quit to Main Menu", True, (245, 245, 245)), (to_menu_rect.x + 14, to_menu_rect.y + 9))
        screen.blit(small_font.render("Quit to Desktop", True, (245, 245, 245)), (to_desktop_rect.x + 20, to_desktop_rect.y + 9))
        if delay_error:
            screen.blit(small_font.render(delay_error, True, (220, 130, 130)), (menu_rect.x + 12, menu_rect.y + 67))
        ui["settings_menu_rect"] = menu_rect
        ui["delay_input_rect"] = delay_input_rect
        ui["apply_delay_rect"] = delay_apply_rect
        ui["quit_to_menu_rect"] = to_menu_rect
        ui["quit_to_desktop_rect"] = to_desktop_rect
        return ui

    def _handle_settings_click(
        self,
        pos: tuple[int, int],
        settings_ui: dict[str, object],
        menu_open: bool,
    ) -> str | None:
        if settings_ui["settings_button_rect"].collidepoint(pos):
            return "toggle"
        if not menu_open:
            return None
        if settings_ui["quit_to_menu_rect"].collidepoint(pos):
            return "quit_menu"
        if settings_ui["quit_to_desktop_rect"].collidepoint(pos):
            return "quit_desktop"
        if settings_ui["apply_delay_rect"].collidepoint(pos):
            return "apply_delay"
        if settings_ui["settings_menu_rect"].collidepoint(pos):
            return "menu"
        return None

    def _current_bot_delay_seconds(self, controllers: Mapping[int, Controller]) -> float:
        for controller in controllers.values():
            delay_seconds = getattr(controller, "_delay_seconds", None)
            if isinstance(delay_seconds, (int, float)):
                return float(delay_seconds)
        return 0.0

    def _apply_bot_delay(self, controllers: Mapping[int, Controller], delay_seconds: float) -> bool:
        updated = False
        for controller in controllers.values():
            set_delay_seconds = getattr(controller, "set_delay_seconds", None)
            if callable(set_delay_seconds):
                set_delay_seconds(delay_seconds)
                updated = True
        return updated

    def _parse_bot_delay_input(self, value: str) -> float | None:
        if not value:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        if parsed < 0:
            return None
        return parsed

    def _format_bot_delay_input(self, value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _draw_dropdown_indicator(
        self,
        screen,
        *,
        center: tuple[int, int],
        open_state: bool,
        color: tuple[int, int, int],
    ) -> None:
        cx, cy = center
        if open_state:
            points = [(cx - 6, cy - 2), (cx + 6, cy - 2), (cx, cy + 5)]
        else:
            points = [(cx - 3, cy - 6), (cx - 3, cy + 6), (cx + 4, cy)]
        self.pg.draw.polygon(screen, color, points)

    def _draw_settings_gear(self, screen, rect) -> None:
        cx, cy = rect.centerx, rect.centery
        accent = (240, 240, 240)
        self.pg.draw.circle(screen, accent, (cx, cy), 9, width=2)
        self.pg.draw.circle(screen, accent, (cx, cy), 3)
        spokes = [
            (0, -13, 0, -9),
            (0, 13, 0, 9),
            (-13, 0, -9, 0),
            (13, 0, 9, 0),
            (-9, -9, -6, -6),
            (9, -9, 6, -6),
            (-9, 9, -6, 6),
            (9, 9, 6, 6),
        ]
        for sx, sy, ex, ey in spokes:
            self.pg.draw.line(screen, accent, (cx + sx, cy + sy), (cx + ex, cy + ey), 2)

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

    def _draw_toggle_button(self, screen, font, rect, label: str, enabled: bool) -> None:
        self.pg.draw.rect(screen, (82, 110, 98) if enabled else (58, 58, 86), rect, border_radius=8)
        status = "ON" if enabled else "OFF"
        text = f"{label}: {status}"
        screen.blit(font.render(text, True, (255, 255, 255)), (rect.x + 10, rect.y + 9))

    def _board_center_and_radius(self, screen) -> tuple[tuple[int, int], int]:
        width, height = screen.get_size()
        panel_width = max(int(width * 0.30), 360)
        bottom_bar_height = max(int(height * 0.18), 130)
        board_width = max(width - panel_width - 40, 200)
        board_height = max(height - bottom_bar_height - 90, 200)
        center = (20 + board_width // 2, 70 + board_height // 2)
        radius = int(min(board_width, board_height) * 0.42)
        return center, max(radius, 120)

    def _effective_build_mode(self, state: GameState, build_mode: str | None) -> str | None:
        if state.turn is not None and state.turn.step == TurnStep.ROAD_BUILDING:
            return "road"
        return build_mode

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
        suppress_yop_detail = (
            acting_player is not None
            and before.turn is not None
            and after.turn is not None
            and before.turn.step == TurnStep.YEAR_OF_PLENTY
            and after.turn.step == TurnStep.ACTIONS
        )
        suppress_monopoly_detail = (
            acting_player is not None
            and before.turn is not None
            and after.turn is not None
            and before.turn.step == TurnStep.MONOPOLY
            and after.turn.step == TurnStep.ACTIONS
        )

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
                    if not ((suppress_yop_detail or suppress_monopoly_detail) and pid == acting_player):
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

    def _hand_view_player(self, state: GameState, active_player: int | None, controllers: Mapping[int, Controller]) -> int | None:
        if active_player is None:
            return None
        controller = controllers.get(active_player)
        if isinstance(controller, HumanController):
            return active_player
        player_order = sorted(state.players.keys())
        if active_player not in player_order:
            return active_player
        human_players = {
            player_id
            for player_id in player_order
            if isinstance(controllers.get(player_id), HumanController)
        }
        if not human_players:
            return player_order[(player_order.index(active_player) - 1) % len(player_order)]
        active_idx = player_order.index(active_player)
        for offset in range(1, len(player_order) + 1):
            candidate = player_order[(active_idx - offset) % len(player_order)]
            if candidate in human_players:
                return candidate
        return min(human_players)
