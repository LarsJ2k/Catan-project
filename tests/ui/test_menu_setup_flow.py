from __future__ import annotations

from catan.controllers.random_bot_controller import RandomBotController
from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.controllers.heuristic_v1_1_bot_controller import HeuristicV1_1BotController
from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.controllers.heuristic_v2_positional_bot_controller import HeuristicV2PositionalBotController
from catan.controllers.human_controller import HumanController
from catan.runners.game_setup import AppScreen, ControllerType, GameSetupState, TournamentSetupState, available_controller_types
from catan.runners.tournament import TournamentFormat
from catan.runners.launcher import create_controllers


def test_menu_setup_state_transitions() -> None:
    state = GameSetupState()

    assert state.screen == AppScreen.MAIN_MENU
    setup_state = state.go_to_setup()
    assert setup_state.screen == AppScreen.GAME_SETUP
    menu_state = setup_state.back_to_menu()
    assert menu_state.screen == AppScreen.MAIN_MENU


def test_right_side_selection_has_single_active_entry() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.HUMAN.value)
    assert state.selected_controller == ControllerType.HUMAN.value

    next_state = state.with_selected_controller(ControllerType.RANDOM_BOT.value)
    assert next_state.selected_controller == ControllerType.RANDOM_BOT.value
    assert state.selected_controller == ControllerType.HUMAN.value


def test_add_button_inserts_in_first_empty_slot_and_respects_max_slots() -> None:
    state = GameSetupState().go_to_setup().with_selected_controller(ControllerType.RANDOM_BOT.value)

    state = state.add_selected_player()
    state = state.add_selected_player()
    assert state.slot_controller(0) == ControllerType.RANDOM_BOT.value
    assert state.slot_controller(1) == ControllerType.RANDOM_BOT.value
    assert state.configured_player_count() == 2

    filled = state
    for _ in range(4):
        filled = filled.add_selected_player()
    assert filled.configured_player_count() == 4
    assert filled.add_selected_player() == filled


def test_remove_compacts_lower_slots_upward() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.RANDOM_BOT.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.RANDOM_BOT.value).add_selected_player()

    compacted = state.remove_player_at(1)

    assert compacted.configured_player_count() == 3
    assert compacted.slot_controller(0) == ControllerType.HUMAN.value
    assert compacted.slot_controller(1) == ControllerType.HUMAN.value
    assert compacted.slot_controller(2) == ControllerType.RANDOM_BOT.value
    assert compacted.slot_controller(3) is None


def test_seed_selection_and_config_generation() -> None:
    random_state = GameSetupState().go_to_setup()
    random_state = random_state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player().add_selected_player()
    random_state = random_state.with_random_seed()
    random_config = random_state.to_launch_config()
    assert random_config is not None
    assert isinstance(random_config.seed, int)

    fixed_state = GameSetupState().go_to_setup().with_selected_controller(ControllerType.HUMAN.value).add_selected_player().add_selected_player()
    fixed_state = fixed_state.with_fixed_seed_text("12345")
    fixed_config = fixed_state.to_launch_config()
    assert fixed_config is not None
    assert fixed_config.seed == 12345

    invalid_fixed_state = GameSetupState().go_to_setup()
    invalid_fixed_state = invalid_fixed_state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player().add_selected_player()
    invalid_fixed_state = invalid_fixed_state.with_fixed_seed_text("abc")
    assert invalid_fixed_state.can_start_game() is False
    assert invalid_fixed_state.to_launch_config() is None


def test_launch_config_uses_ordered_left_slots_and_creates_expected_controllers() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.RANDOM_BOT.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HEURISTIC_BOT.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    state = state.with_fixed_seed_text("777")
    config = state.to_launch_config()
    assert config is not None
    assert [slot.player_id for slot in config.player_slots] == [1, 2, 3]
    assert [slot.controller_key for slot in config.player_slots] == [
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.HUMAN.value,
    ]

    controllers = create_controllers(config)

    assert isinstance(controllers[1], RandomBotController)
    assert isinstance(controllers[2], HeuristicBotController)
    assert isinstance(controllers[3], HumanController)


def test_cannot_start_when_too_few_players_configured() -> None:
    state = GameSetupState().go_to_setup().with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    assert state.can_start_game() is False
    assert state.to_launch_config() is None


def test_available_controller_types_keep_human_first() -> None:
    controller_types = available_controller_types()
    assert controller_types[0] == ControllerType.HUMAN.value
    assert ControllerType.RANDOM_BOT.value in controller_types
    assert ControllerType.HEURISTIC_BOT.value in controller_types
    assert ControllerType.HEURISTIC_V1_BASELINE.value in controller_types
    assert ControllerType.HEURISTIC_V1_FIXED.value in controller_types
    assert ControllerType.HEURISTIC_V1_1.value in controller_types
    assert ControllerType.HEURISTIC_V2_POSITIONAL.value in controller_types


def test_launch_config_can_create_new_v1_baseline_bot_controller() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.HEURISTIC_V1_BASELINE.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    config = state.with_fixed_seed_text("17").to_launch_config()
    assert config is not None

    controllers = create_controllers(config)
    assert isinstance(controllers[1], HeuristicV1BaselineBotController)


def test_launch_config_can_create_new_v1_1_bot_controller() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.HEURISTIC_V1_1.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    config = state.with_fixed_seed_text("19").to_launch_config()
    assert config is not None

    controllers = create_controllers(config)
    assert isinstance(controllers[1], HeuristicV1_1BotController)


def test_launch_config_can_create_new_v2_positional_bot_controller() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_selected_controller(ControllerType.HEURISTIC_V2_POSITIONAL.value).add_selected_player()
    state = state.with_selected_controller(ControllerType.HUMAN.value).add_selected_player()
    config = state.with_fixed_seed_text("23").to_launch_config()
    assert config is not None

    controllers = create_controllers(config)
    assert isinstance(controllers[1], HeuristicV2PositionalBotController)


def test_tournament_setup_requires_valid_selection() -> None:
    invalid = TournamentSetupState(
        selected_bots=(),
        format=TournamentFormat.FIXED_LINEUP_BATCH.value,
    )
    assert invalid.to_tournament_config() is None

    valid = TournamentSetupState(
        selected_bots=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
        format=TournamentFormat.FIXED_LINEUP_BATCH.value,
    )
    config = valid.to_tournament_config()
    assert config is not None
    assert config.fixed_lineup is not None
    assert len(config.fixed_lineup) == 4


def test_tournament_setup_add_remove_bot_list_flow() -> None:
    state = TournamentSetupState()
    state = state.with_selected_bot(ControllerType.RANDOM_BOT.value).add_selected_bot()
    state = state.with_selected_bot(ControllerType.HEURISTIC_BOT.value).add_selected_bot()
    duplicate_attempt = state.with_selected_bot(ControllerType.RANDOM_BOT.value).add_selected_bot()

    assert duplicate_attempt.selected_bots == state.selected_bots

    removed = state.remove_selected_bot_at(0)
    assert removed.selected_bots == (ControllerType.HEURISTIC_BOT.value,)


def test_tournament_setup_can_toggle_stalled_games_debug_export() -> None:
    state = TournamentSetupState(
        selected_bots=(ControllerType.RANDOM_BOT.value,),
        format=TournamentFormat.FIXED_LINEUP_BATCH.value,
    )
    config = state.with_export_stalled_games_debug(True).to_tournament_config()
    assert config is not None
    assert config.output_options.write_stalled_games_debug is True
