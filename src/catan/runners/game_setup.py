from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import randint


class AppScreen(str, Enum):
    MAIN_MENU = "main_menu"
    GAME_SETUP = "game_setup"


class ControllerType(str, Enum):
    HUMAN = "human"
    RANDOM_BOT = "random_bot"
    HEURISTIC_BOT = "heuristic_bot"


def available_controller_types() -> tuple[ControllerType, ...]:
    return tuple(ControllerType)


def controller_label(controller_type: ControllerType) -> str:
    labels = {
        ControllerType.HUMAN: "Human",
        ControllerType.RANDOM_BOT: "Random Bot",
        ControllerType.HEURISTIC_BOT: "Heuristic Bot",
    }
    return labels.get(controller_type, controller_type.value)


@dataclass(frozen=True)
class PlayerSlotConfig:
    player_id: int
    controller_type: ControllerType


@dataclass(frozen=True)
class GameLaunchConfig:
    player_slots: tuple[PlayerSlotConfig, ...]
    seed: int


@dataclass(frozen=True)
class GameSetupState:
    screen: AppScreen = AppScreen.MAIN_MENU
    configured_controllers: tuple[ControllerType, ...] = ()
    selected_controller: ControllerType | None = ControllerType.HUMAN
    use_random_seed: bool = True
    fixed_seed_text: str = ""
    max_players: int = 4
    min_players: int = 2

    def go_to_setup(self) -> GameSetupState:
        return GameSetupState(
            screen=AppScreen.GAME_SETUP,
            configured_controllers=self.configured_controllers,
            selected_controller=self.selected_controller,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def back_to_menu(self) -> GameSetupState:
        return GameSetupState(
            screen=AppScreen.MAIN_MENU,
            configured_controllers=self.configured_controllers,
            selected_controller=self.selected_controller,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def with_selected_controller(self, controller_type: ControllerType | None) -> GameSetupState:
        return GameSetupState(
            screen=self.screen,
            configured_controllers=self.configured_controllers,
            selected_controller=controller_type,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def add_selected_player(self) -> GameSetupState:
        if self.selected_controller is None or len(self.configured_controllers) >= self.max_players:
            return self
        return GameSetupState(
            screen=self.screen,
            configured_controllers=self.configured_controllers + (self.selected_controller,),
            selected_controller=self.selected_controller,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def remove_player_at(self, slot_index: int) -> GameSetupState:
        if slot_index < 0 or slot_index >= len(self.configured_controllers):
            return self
        slots = list(self.configured_controllers)
        slots.pop(slot_index)
        return GameSetupState(
            screen=self.screen,
            configured_controllers=tuple(slots),
            selected_controller=self.selected_controller,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def with_random_seed(self) -> GameSetupState:
        return GameSetupState(
            screen=self.screen,
            configured_controllers=self.configured_controllers,
            selected_controller=self.selected_controller,
            use_random_seed=True,
            fixed_seed_text="",
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def with_fixed_seed_text(self, seed_text: str) -> GameSetupState:
        return GameSetupState(
            screen=self.screen,
            configured_controllers=self.configured_controllers,
            selected_controller=self.selected_controller,
            use_random_seed=False,
            fixed_seed_text=seed_text,
            max_players=self.max_players,
            min_players=self.min_players,
        )

    def can_add_player(self) -> bool:
        return self.selected_controller is not None and len(self.configured_controllers) < self.max_players

    def configured_player_count(self) -> int:
        return len(self.configured_controllers)

    def slot_controller(self, slot_index: int) -> ControllerType | None:
        if slot_index < 0 or slot_index >= self.max_players:
            return None
        if slot_index >= len(self.configured_controllers):
            return None
        return self.configured_controllers[slot_index]

    def configured_player_slots(self) -> tuple[PlayerSlotConfig, ...]:
        return tuple(
            PlayerSlotConfig(player_id=index + 1, controller_type=controller_type)
            for index, controller_type in enumerate(self.configured_controllers)
        )

    def can_start_game(self) -> bool:
        if self.configured_player_count() < self.min_players:
            return False
        if self.use_random_seed:
            return True
        return self._parse_fixed_seed() is not None

    def to_launch_config(self) -> GameLaunchConfig | None:
        if not self.can_start_game():
            return None
        seed = self._parse_fixed_seed() if not self.use_random_seed else randint(1, 2**31 - 1)
        if seed is None:
            return None
        return GameLaunchConfig(player_slots=self.configured_player_slots(), seed=seed)

    def _parse_fixed_seed(self) -> int | None:
        text = self.fixed_seed_text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
