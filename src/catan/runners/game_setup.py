from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import randint


class AppScreen(str, Enum):
    MAIN_MENU = "main_menu"
    GAME_SETUP = "game_setup"


class ControllerType(str, Enum):
    HUMAN = "human"
    BOT_PLACEHOLDER = "bot_placeholder"


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
    player_slots: tuple[PlayerSlotConfig, ...] = (
        PlayerSlotConfig(player_id=1, controller_type=ControllerType.HUMAN),
        PlayerSlotConfig(player_id=2, controller_type=ControllerType.HUMAN),
        PlayerSlotConfig(player_id=3, controller_type=ControllerType.HUMAN),
        PlayerSlotConfig(player_id=4, controller_type=ControllerType.HUMAN),
    )
    use_random_seed: bool = True
    fixed_seed_text: str = ""

    def go_to_setup(self) -> GameSetupState:
        return GameSetupState(
            screen=AppScreen.GAME_SETUP,
            player_slots=self.player_slots,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
        )

    def back_to_menu(self) -> GameSetupState:
        return GameSetupState(
            screen=AppScreen.MAIN_MENU,
            player_slots=self.player_slots,
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
        )

    def with_player_controller(self, slot_index: int, controller_type: ControllerType) -> GameSetupState:
        slots = list(self.player_slots)
        current = slots[slot_index]
        slots[slot_index] = PlayerSlotConfig(player_id=current.player_id, controller_type=controller_type)
        return GameSetupState(
            screen=self.screen,
            player_slots=tuple(slots),
            use_random_seed=self.use_random_seed,
            fixed_seed_text=self.fixed_seed_text,
        )

    def with_random_seed(self) -> GameSetupState:
        return GameSetupState(
            screen=self.screen,
            player_slots=self.player_slots,
            use_random_seed=True,
            fixed_seed_text="",
        )

    def with_fixed_seed_text(self, seed_text: str) -> GameSetupState:
        return GameSetupState(
            screen=self.screen,
            player_slots=self.player_slots,
            use_random_seed=False,
            fixed_seed_text=seed_text,
        )

    def can_start_game(self) -> bool:
        if self.use_random_seed:
            return True
        return self._parse_fixed_seed() is not None

    def to_launch_config(self) -> GameLaunchConfig | None:
        if not self.can_start_game():
            return None
        seed = self._parse_fixed_seed() if not self.use_random_seed else randint(1, 2**31 - 1)
        if seed is None:
            return None
        return GameLaunchConfig(player_slots=self.player_slots, seed=seed)

    def _parse_fixed_seed(self) -> int | None:
        text = self.fixed_seed_text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
