from __future__ import annotations

from dataclasses import dataclass
from random import Random
from time import perf_counter
from catan.controllers.bot_catalog import (
    BotDefinition,
    build_bot_controller_from_bot_definition,
    create_custom_bot_definition,
    get_bot_definition,
    list_bot_definitions,
)
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.state import InitialGameConfig
from catan.runners.headless_runner import HeadlessRunner
from catan.runners.tournament import (
    MatchConfig,
    MatchResult,
    TournamentConfig,
    TournamentFormat,
    _total_victory_points,
    TournamentResult,
    _build_seat_result,
    _ranks_from_vps,
    aggregate_results,
)

_NON_MUTABLE_PARAM_KEYS = frozenset({"seed", "delay_seconds", "candidate_count"})


@dataclass(frozen=True)
class TrainingConfig:
    parent_bot_ids: tuple[str, ...]
    population_per_parent: int
    mutation_modifier: float
    mutation_seed: int
    candidate_prefix: str
    games_per_bot: int
    tournament_seed: int


@dataclass(frozen=True)
class TemporaryBotDefinition:
    temporary_id: str
    display_name: str
    parent_bot_id: str
    parent_display_name: str
    mutation_modifier: float
    mutation_seed: int
    candidate_index: int
    parameters: dict[str, float | int | str | bool]
    metadata: dict[str, float | int | str | bool]


@dataclass(frozen=True)
class TrainingResult:
    config: TrainingConfig
    candidate_definitions: tuple[TemporaryBotDefinition, ...]
    screening_result: TournamentResult


def mutable_numeric_parameter_keys(definition: BotDefinition) -> tuple[str, ...]:
    keys: list[str] = []
    for key, value in definition.parameters.items():
        if key in _NON_MUTABLE_PARAM_KEYS or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            keys.append(key)
    return tuple(keys)


def generate_temporary_candidates(config: TrainingConfig) -> tuple[TemporaryBotDefinition, ...]:
    rng = Random(config.mutation_seed)
    candidates: list[TemporaryBotDefinition] = []
    for parent_id in config.parent_bot_ids:
        parent = get_bot_definition(parent_id)
        if parent is None:
            continue
        mutable_keys = mutable_numeric_parameter_keys(parent)
        if not mutable_keys:
            continue
        for idx in range(config.population_per_parent):
            candidate_params = dict(parent.parameters)
            for key in mutable_keys:
                source_value = parent.parameters[key]
                if not isinstance(source_value, (int, float)) or isinstance(source_value, bool):
                    continue
                if source_value == 0:
                    candidate_params[key] = source_value
                    continue
                multiplier = rng.uniform(config.mutation_modifier, 2.0 - config.mutation_modifier)
                mutated_value = float(source_value) * multiplier
                if isinstance(source_value, int):
                    candidate_params[key] = int(round(mutated_value))
                else:
                    candidate_params[key] = mutated_value
            candidate_id = f"tmp_{parent.bot_id}_{idx + 1:03d}_{config.mutation_seed}"
            display_name = f"{parent.bot_id}_{config.candidate_prefix}_{idx + 1:03d}"
            candidates.append(
                TemporaryBotDefinition(
                    temporary_id=candidate_id,
                    display_name=display_name,
                    parent_bot_id=parent.bot_id,
                    parent_display_name=parent.display_name,
                    mutation_modifier=config.mutation_modifier,
                    mutation_seed=config.mutation_seed,
                    candidate_index=idx + 1,
                    parameters=candidate_params,
                    metadata={
                        "temporary": True,
                        "parent_bot_id": parent.bot_id,
                        "parent_display_name": parent.display_name,
                        "mutation_modifier": config.mutation_modifier,
                        "mutation_seed": config.mutation_seed,
                        "candidate_index": idx + 1,
                    },
                )
            )
    return tuple(candidates)


def generate_balanced_screening_matches(
    candidate_ids: tuple[str, ...],
    *,
    games_per_bot: int,
    base_seed: int,
) -> tuple[MatchConfig, ...]:
    if len(candidate_ids) < 4:
        raise ValueError("Training screening requires at least 4 candidates.")
    if games_per_bot <= 0:
        raise ValueError("games_per_bot must be positive.")

    rng = Random(base_seed)
    bots = list(candidate_ids)
    matches: list[MatchConfig] = []
    seat_counts: dict[str, list[int]] = {bot_id: [0, 0, 0, 0] for bot_id in bots}
    games_played: dict[str, int] = {bot_id: 0 for bot_id in bots}
    target_games = games_per_bot
    match_idx = 0

    while min(games_played.values()) < target_games:
        sorted_bots = sorted(bots, key=lambda bot_id: (games_played[bot_id], seat_counts[bot_id][0], bot_id))
        lineup = sorted_bots[:4]
        rng.shuffle(lineup)
        seat_order: list[str] = []
        for seat in range(4):
            selected = min(lineup, key=lambda bot_id: (seat_counts[bot_id][seat], games_played[bot_id], bot_id))
            seat_order.append(selected)
            lineup.remove(selected)
        for seat, bot_id in enumerate(seat_order):
            seat_counts[bot_id][seat] += 1
            games_played[bot_id] += 1
        matches.append(
            MatchConfig(
                lineup=tuple(sorted(seat_order)),
                seed=base_seed + match_idx,
                seat_order=tuple(seat_order),
                game_index_within_seed_block=match_idx,
                seat_rotation_block_id=match_idx,
            )
        )
        match_idx += 1
        if match_idx > max(20000, len(bots) * target_games * 2):
            break

    return tuple(matches)


class TrainingRunner:
    def __init__(self) -> None:
        self._game_runner = HeadlessRunner()

    def run(self, config: TrainingConfig) -> TrainingResult:
        candidates = generate_temporary_candidates(config)
        id_to_candidate = {candidate.temporary_id: candidate for candidate in candidates}
        matches = generate_balanced_screening_matches(
            tuple(id_to_candidate.keys()),
            games_per_bot=config.games_per_bot,
            base_seed=config.tournament_seed,
        )
        results: list[MatchResult] = []
        for idx, match in enumerate(matches, start=1):
            results.append(self._play_match(match, idx, id_to_candidate))
        screening = TournamentResult(
            config=TournamentConfig(
                selected_bots=tuple(id_to_candidate.keys()),
                format=TournamentFormat.FIXED_LINEUP_BATCH,
                seed_blocks=1,
                seat_rotation_enabled=True,
                base_seed=config.tournament_seed,
            ),
            tournament_id=f"training_{config.tournament_seed}_{config.mutation_seed}",
            matches=tuple(results),
            aggregates=aggregate_results(tuple(results)),
        )
        return TrainingResult(config=config, candidate_definitions=candidates, screening_result=screening)

    def _play_match(
        self,
        match: MatchConfig,
        match_index: int,
        id_to_candidate: dict[str, TemporaryBotDefinition],
    ) -> MatchResult:
        board = build_classic_19_tile_board(seed=match.seed)
        state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=match.seed))
        controllers = {}
        for player_id, bot_id in enumerate(match.seat_order, start=1):
            candidate = id_to_candidate[bot_id]
            parent = get_bot_definition(candidate.parent_bot_id)
            if parent is None:
                raise ValueError(f"Unknown parent bot for candidate: {candidate.parent_bot_id}")
            definition = BotDefinition(
                bot_id=candidate.temporary_id,
                display_name=candidate.display_name,
                base_controller_type=parent.base_controller_type,
                description=f"Temporary training candidate from {parent.display_name}",
                parameters=candidate.parameters,
                metadata=candidate.metadata,
                is_builtin=False,
            )
            controllers[player_id] = build_bot_controller_from_bot_definition(
                definition,
                enable_bot_delay=False,
                seed=match.seed + player_id,
                delay_seconds=0.0,
            )
        started_at = perf_counter()
        run_result = self._game_runner.play_until_terminal_with_result(
            state,
            controllers,
            max_steps=100_000,
        )
        final_state = run_result.final_state
        step_count = run_result.steps
        full_turn_count = run_result.full_turn_count
        match_duration_seconds = perf_counter() - started_at
        seat_vps = tuple(_total_victory_points(final_state, pid + 1) for pid in range(4))
        ranks = _ranks_from_vps(seat_vps)

        winner_bot_id: str | None = None
        winner_seat: int | None = final_state.winner if run_result.termination_reason == "win" else None
        if winner_seat is not None:
            winner_bot_id = match.seat_order[final_state.winner - 1]

        seat_results = tuple(_build_seat_result(final_state, match.seat_order, seat_index, ranks[seat_index]) for seat_index in range(4))
        return MatchResult(
            match_id=f"training_match_{match_index:05d}",
            tournament_id="training",
            lineup=match.lineup,
            seat_order=match.seat_order,
            seed=match.seed,
            game_index_within_seed_block=match.game_index_within_seed_block,
            seat_rotation_block_id=match.seat_rotation_block_id,
            winner_bot_id=winner_bot_id,
            winner_seat=winner_seat,
            termination_reason=run_result.termination_reason,
            match_duration_seconds=match_duration_seconds,
            turn_count=step_count,
            full_turn_count=full_turn_count,
            seat_results=seat_results,
            debug_snapshot=run_result.stalled_debug_snapshot,
        )


def rank_candidates(result: TrainingResult) -> list[tuple[TemporaryBotDefinition, float, float, float, int]]:
    ranked: list[tuple[TemporaryBotDefinition, float, float, float, int]] = []
    for candidate in result.candidate_definitions:
        agg = result.screening_result.aggregates.get(candidate.temporary_id)
        if agg is None:
            continue
        ranked.append((candidate, agg.win_rate, agg.average_rank, agg.average_final_vp, agg.games_played))
    ranked.sort(key=lambda item: (-item[1], item[2], -item[3], item[0].display_name))
    return ranked


def promote_training_candidates(
    *,
    candidates: tuple[TemporaryBotDefinition, ...],
    promoted_names_by_id: dict[str, str],
) -> tuple[BotDefinition, ...]:
    existing_names = {definition.display_name for definition in list_bot_definitions()}
    normalized_new_names: dict[str, str] = {}
    for candidate_id, name in promoted_names_by_id.items():
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("Promoted bot name cannot be empty.")
        if trimmed in existing_names:
            raise ValueError(f"A bot named '{trimmed}' already exists.")
        if trimmed in normalized_new_names.values():
            raise ValueError(f"Duplicate promoted name '{trimmed}' is not allowed.")
        normalized_new_names[candidate_id] = trimmed

    by_id = {candidate.temporary_id: candidate for candidate in candidates}
    created: list[BotDefinition] = []
    for candidate_id, name in normalized_new_names.items():
        candidate = by_id.get(candidate_id)
        if candidate is None:
            continue
        created.append(
            create_custom_bot_definition(
                name=name,
                base_bot_id=candidate.parent_bot_id,
                description=f"Promoted from training candidate {candidate.display_name}",
                parameters=candidate.parameters,
                metadata={
                    "parent_bot_id": candidate.parent_bot_id,
                    "parent_display_name": candidate.parent_display_name,
                    "mutation_modifier": candidate.mutation_modifier,
                    "mutation_seed": candidate.mutation_seed,
                    "candidate_index": candidate.candidate_index,
                    "source_temporary_id": candidate.temporary_id,
                    "source": "training",
                },
            )
        )
    return tuple(created)
