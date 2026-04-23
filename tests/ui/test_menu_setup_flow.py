from __future__ import annotations

from catan.controllers.bot_placeholder_controller import BotPlaceholderController
from catan.controllers.human_controller import HumanController
from catan.runners.game_setup import AppScreen, ControllerType, GameSetupState
from catan.runners.launcher import create_controllers


def test_menu_setup_state_transitions() -> None:
    state = GameSetupState()

    assert state.screen == AppScreen.MAIN_MENU
    setup_state = state.go_to_setup()
    assert setup_state.screen == AppScreen.GAME_SETUP
    menu_state = setup_state.back_to_menu()
    assert menu_state.screen == AppScreen.MAIN_MENU


def test_per_player_controller_selection_state() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_player_controller(1, ControllerType.BOT_PLACEHOLDER)
    state = state.with_player_controller(3, ControllerType.BOT_PLACEHOLDER)

    assert state.player_slots[0].controller_type == ControllerType.HUMAN
    assert state.player_slots[1].controller_type == ControllerType.BOT_PLACEHOLDER
    assert state.player_slots[2].controller_type == ControllerType.HUMAN
    assert state.player_slots[3].controller_type == ControllerType.BOT_PLACEHOLDER


def test_seed_selection_and_config_generation() -> None:
    random_state = GameSetupState().go_to_setup().with_random_seed()
    random_config = random_state.to_launch_config()
    assert random_config is not None
    assert isinstance(random_config.seed, int)

    fixed_state = GameSetupState().go_to_setup().with_fixed_seed_text("12345")
    fixed_config = fixed_state.to_launch_config()
    assert fixed_config is not None
    assert fixed_config.seed == 12345

    invalid_fixed_state = GameSetupState().go_to_setup().with_fixed_seed_text("abc")
    assert invalid_fixed_state.can_start_game() is False
    assert invalid_fixed_state.to_launch_config() is None


def test_launch_config_creates_expected_controller_instances() -> None:
    state = GameSetupState().go_to_setup()
    state = state.with_player_controller(0, ControllerType.BOT_PLACEHOLDER)
    state = state.with_player_controller(1, ControllerType.BOT_PLACEHOLDER)
    state = state.with_fixed_seed_text("777")
    config = state.to_launch_config()
    assert config is not None

    controllers = create_controllers(config)

    assert isinstance(controllers[1], BotPlaceholderController)
    assert isinstance(controllers[2], BotPlaceholderController)
    assert isinstance(controllers[3], HumanController)
    assert isinstance(controllers[4], HumanController)
