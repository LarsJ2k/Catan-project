from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import randint


class AppScreen(str, Enum):
    MAIN_MENU = "main_menu"
    GAME_SETUP = "game_setup"
    TOURNAMENT_SETUP = "tournament_setup"
    BOT_LAB = "bot_lab"
    TRAINING = "training"


class ControllerType(str, Enum):
    HUMAN = "human"
    RANDOM_BOT = "random_bot"
    SIMPLE_GOAL_BOT = "simple_goal_bot"
    HEURISTIC_BOT = "heuristic_bot"
    HEURISTIC_V1_BASELINE = "heuristic_v1_baseline"
    HEURISTIC_V1_FIXED = "heuristic_v1_fixed"
    HEURISTIC_V1_1 = "heuristic_v1_1"
    HEURISTIC_V2_POSITIONAL = "heuristic_v2_positional"


def available_controller_types() -> tuple[str, ...]:
    from catan.controllers.bot_catalog import list_bot_definitions

    return (ControllerType.HUMAN.value,) + tuple(definition.bot_id for definition in list_bot_definitions())


def controller_label(controller_key: str | None) -> str:
    from catan.controllers.bot_catalog import get_bot_definition

    if controller_key is None:
        return "(none)"
    if controller_key == ControllerType.HUMAN.value:
        return "Human"
    definition = get_bot_definition(controller_key)
    return definition.display_name if definition is not None else controller_key


@dataclass(frozen=True)
class PlayerSlotConfig:
    player_id: int
    controller_key: str


@dataclass(frozen=True)
class GameLaunchConfig:
    player_slots: tuple[PlayerSlotConfig, ...]
    seed: int
    bot_delay_seconds: float = 1.2
    enable_v2_profiling: bool = False


@dataclass(frozen=True)
class GameSetupState:
    screen: AppScreen = AppScreen.MAIN_MENU
    configured_controllers: tuple[str, ...] = ()
    selected_controller: str | None = ControllerType.HUMAN.value
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

    def with_selected_controller(self, controller_type: str | None) -> GameSetupState:
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

    def slot_controller(self, slot_index: int) -> str | None:
        if slot_index < 0 or slot_index >= self.max_players:
            return None
        if slot_index >= len(self.configured_controllers):
            return None
        return self.configured_controllers[slot_index]

    def configured_player_slots(self) -> tuple[PlayerSlotConfig, ...]:
        return tuple(
            PlayerSlotConfig(player_id=index + 1, controller_key=controller_type)
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


@dataclass(frozen=True)
class TournamentSetupState:
    selected_bots: tuple[str, ...] = ()
    selected_bot: str | None = None
    format: str = "fixed_lineup_batch"
    seed_blocks_text: str = "10"
    base_seed_text: str = "1"
    seat_rotation_enabled: bool = True
    export_json: bool = True
    export_csv: bool = True
    export_stalled_games_debug: bool = False
    enable_v2_profiling: bool = False

    def toggle_bot(self, controller_type: str) -> TournamentSetupState:
        if controller_type == ControllerType.HUMAN.value:
            return self
        if controller_type in self.selected_bots:
            return TournamentSetupState(
                selected_bots=tuple(bot for bot in self.selected_bots if bot != controller_type),
                selected_bot=self.selected_bot,
                format=self.format,
                seed_blocks_text=self.seed_blocks_text,
                base_seed_text=self.base_seed_text,
                seat_rotation_enabled=self.seat_rotation_enabled,
                export_json=self.export_json,
                export_csv=self.export_csv,
                export_stalled_games_debug=self.export_stalled_games_debug,
                enable_v2_profiling=self.enable_v2_profiling,
            )
        return TournamentSetupState(
            selected_bots=self.selected_bots + (controller_type,),
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_format(self, format_value: str) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=format_value,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_seed_blocks_text(self, value: str) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=value,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_base_seed_text(self, value: str) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=value,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_seat_rotation_enabled(self, enabled: bool) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_export_json(self, enabled: bool) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=enabled,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_export_csv(self, enabled: bool) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=enabled,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_export_stalled_games_debug(self, enabled: bool) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=enabled,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def with_v2_profiling_enabled(self, enabled: bool) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=enabled,
        )

    def with_selected_bot(self, controller_type: str | None) -> TournamentSetupState:
        return TournamentSetupState(
            selected_bots=self.selected_bots,
            selected_bot=controller_type,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def add_selected_bot(self) -> TournamentSetupState:
        if (
            self.selected_bot is None
            or self.selected_bot == ControllerType.HUMAN.value
            or self.selected_bot in self.selected_bots
        ):
            return self
        return TournamentSetupState(
            selected_bots=self.selected_bots + (self.selected_bot,),
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def remove_selected_bot_at(self, slot_index: int) -> TournamentSetupState:
        if slot_index < 0 or slot_index >= len(self.selected_bots):
            return self
        bots = list(self.selected_bots)
        bots.pop(slot_index)
        return TournamentSetupState(
            selected_bots=tuple(bots),
            selected_bot=self.selected_bot,
            format=self.format,
            seed_blocks_text=self.seed_blocks_text,
            base_seed_text=self.base_seed_text,
            seat_rotation_enabled=self.seat_rotation_enabled,
            export_json=self.export_json,
            export_csv=self.export_csv,
            export_stalled_games_debug=self.export_stalled_games_debug,
            enable_v2_profiling=self.enable_v2_profiling,
        )

    def preview_match_count(self) -> int | None:
        from catan.runners.tournament import generate_lineups

        config = self.to_tournament_config()
        if config is None:
            return None
        lineup_count = len(generate_lineups(config))
        matches_per_lineup = 4 if config.seat_rotation_enabled else 1
        return lineup_count * config.seed_blocks * matches_per_lineup

    def to_tournament_config(self):
        from catan.runners.tournament import TournamentConfig, TournamentFormat, TournamentOutputOptions

        if self.format == TournamentFormat.FIXED_LINEUP_BATCH.value and len(self.selected_bots) < 1:
            return None
        if self.format == TournamentFormat.ROUND_ROBIN.value and len(self.selected_bots) < 4:
            return None
        try:
            seed_blocks = int(self.seed_blocks_text)
            base_seed = int(self.base_seed_text)
        except ValueError:
            return None
        if seed_blocks <= 0:
            return None
        format_enum = TournamentFormat(self.format)
        fixed_lineup: tuple[str, ...] | None = None
        if format_enum == TournamentFormat.FIXED_LINEUP_BATCH:
            repeated = [self.selected_bots[idx % len(self.selected_bots)] for idx in range(4)]
            fixed_lineup = tuple(repeated)
        return TournamentConfig(
            selected_bots=tuple(self.selected_bots),
            format=format_enum,
            seed_blocks=seed_blocks,
            seat_rotation_enabled=self.seat_rotation_enabled,
            base_seed=base_seed,
            fixed_lineup=fixed_lineup,
            output_options=TournamentOutputOptions(
                write_json=self.export_json,
                write_csv=self.export_csv,
                write_stalled_games_debug=self.export_stalled_games_debug,
            ),
            enable_v2_profiling=self.enable_v2_profiling,
        )


@dataclass(frozen=True)
class TrainingSetupState:
    selected_parent_bots: tuple[str, ...] = ()
    population_per_parent_text: str = "8"
    mutation_modifier_text: str = "0.7"
    mutation_seed_text: str = "123"
    candidate_prefix: str = "mut"
    games_per_bot_text: str = "40"
    tournament_seed_text: str = "1"

    def toggle_parent_bot(self, bot_id: str) -> TrainingSetupState:
        if bot_id in self.selected_parent_bots:
            return TrainingSetupState(
                selected_parent_bots=tuple(value for value in self.selected_parent_bots if value != bot_id),
                population_per_parent_text=self.population_per_parent_text,
                mutation_modifier_text=self.mutation_modifier_text,
                mutation_seed_text=self.mutation_seed_text,
                candidate_prefix=self.candidate_prefix,
                games_per_bot_text=self.games_per_bot_text,
                tournament_seed_text=self.tournament_seed_text,
            )
        return TrainingSetupState(
            selected_parent_bots=self.selected_parent_bots + (bot_id,),
            population_per_parent_text=self.population_per_parent_text,
            mutation_modifier_text=self.mutation_modifier_text,
            mutation_seed_text=self.mutation_seed_text,
            candidate_prefix=self.candidate_prefix,
            games_per_bot_text=self.games_per_bot_text,
            tournament_seed_text=self.tournament_seed_text,
        )

    def to_training_config(self):
        from catan.runners.training import TrainingConfig

        if not self.selected_parent_bots:
            return None
        try:
            population = int(self.population_per_parent_text)
            modifier = float(self.mutation_modifier_text)
            mutation_seed = int(self.mutation_seed_text)
            games_per_bot = int(self.games_per_bot_text)
            tournament_seed = int(self.tournament_seed_text)
        except ValueError:
            return None
        if population <= 0 or games_per_bot <= 0:
            return None
        if modifier <= 0 or modifier > 1:
            return None
        return TrainingConfig(
            parent_bot_ids=self.selected_parent_bots,
            population_per_parent=population,
            mutation_modifier=modifier,
            mutation_seed=mutation_seed,
            candidate_prefix=self.candidate_prefix.strip() or "mut",
            games_per_bot=games_per_bot,
            tournament_seed=tournament_seed,
        )

    def preview_match_count(self) -> int | None:
        from catan.runners.training import generate_balanced_screening_matches, generate_temporary_candidates

        config = self.to_training_config()
        if config is None:
            return None
        candidates = generate_temporary_candidates(config)
        if len(candidates) < 4:
            return None
        matches = generate_balanced_screening_matches(
            tuple(candidate.temporary_id for candidate in candidates),
            games_per_bot=config.games_per_bot,
            base_seed=config.tournament_seed,
        )
        return len(matches)
