from __future__ import annotations

from pathlib import Path

from catan.runners.game_setup import ControllerType, TournamentSetupState
from catan.runners.tournament import (
    HeadlessTournamentRunner,
    MatchResult,
    TournamentConfig,
    TournamentFormat,
    TournamentOutputOptions,
    aggregate_results,
    export_tournament_result,
    generate_match_configs,
)


def test_tournament_setup_state_builds_config() -> None:
    state = TournamentSetupState(
        selected_bots=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
        format=TournamentFormat.FIXED_LINEUP_BATCH.value,
        seed_blocks_text="3",
        base_seed_text="10",
        seat_rotation_enabled=True,
    )

    config = state.to_tournament_config()

    assert config is not None
    assert config.seed_blocks == 3
    assert config.base_seed == 10
    assert config.fixed_lineup == (
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
    )


def test_seat_rotation_block_generation_uses_shared_seed() -> None:
    config = TournamentConfig(
        selected_bots=(
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
        ),
        fixed_lineup=(
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
        ),
        format=TournamentFormat.FIXED_LINEUP_BATCH,
        seed_blocks=1,
        base_seed=42,
        seat_rotation_enabled=True,
    )

    matches = generate_match_configs(config)

    assert len(matches) == 4
    assert all(match.seed == 42 for match in matches)
    assert matches[0].seat_order == (
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
    )
    assert matches[1].seat_order == (
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
    )


def test_round_robin_lineup_generation_is_deterministic() -> None:
    selected = (
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
        ControllerType.HEURISTIC_BOT.value,
        ControllerType.RANDOM_BOT.value,
    )
    config = TournamentConfig(
        selected_bots=selected,
        format=TournamentFormat.ROUND_ROBIN,
        seed_blocks=1,
    )

    first = generate_match_configs(config)
    second = generate_match_configs(config)

    assert first == second


def test_headless_tournament_runner_executes_without_ui() -> None:
    config = TournamentConfig(
        selected_bots=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
        fixed_lineup=(
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
        ),
        format=TournamentFormat.FIXED_LINEUP_BATCH,
        seed_blocks=1,
        seat_rotation_enabled=False,
    )

    result = HeadlessTournamentRunner().run(config)

    assert len(result.matches) == 1
    assert result.matches[0].winner in (ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value, None)
    assert result.aggregates[ControllerType.RANDOM_BOT.value].games_played == 2
    assert result.aggregates[ControllerType.HEURISTIC_BOT.value].games_played == 2


def test_aggregation_correctness() -> None:
    matches = (
        MatchResult(
            lineup=(ControllerType.RANDOM_BOT.value,) * 4,
            seat_order=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value, ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
            seed=1,
            winner=ControllerType.RANDOM_BOT.value,
            final_vp_by_seat=(10, 8, 9, 7),
            turn_count=120,
            rank_by_seat=(1, 3, 2, 4),
            largest_army_holder=ControllerType.RANDOM_BOT.value,
            longest_road_holder=ControllerType.HEURISTIC_BOT.value,
        ),
    )

    aggregates = aggregate_results(matches)

    assert aggregates[ControllerType.RANDOM_BOT.value].wins == 2
    assert aggregates[ControllerType.RANDOM_BOT.value].games_played == 2
    assert aggregates[ControllerType.RANDOM_BOT.value].average_final_vp == 9.5
    assert aggregates[ControllerType.HEURISTIC_BOT.value].average_rank == 3.5


def test_export_json_and_csv(tmp_path: Path) -> None:
    config = TournamentConfig(
        selected_bots=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
        fixed_lineup=(
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
        ),
        format=TournamentFormat.FIXED_LINEUP_BATCH,
        seed_blocks=1,
        output_options=TournamentOutputOptions(output_dir=str(tmp_path), output_prefix="test"),
    )
    result = HeadlessTournamentRunner().run(config)

    json_path, csv_path = export_tournament_result(result)

    assert json_path is not None and json_path.exists()
    assert csv_path is not None and csv_path.exists()


def test_tournament_runner_disables_bot_delay(monkeypatch) -> None:
    slept = {"count": 0}

    def _fake_sleep(_: float) -> None:
        slept["count"] += 1

    monkeypatch.setattr("time.sleep", _fake_sleep)
    config = TournamentConfig(
        selected_bots=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
        fixed_lineup=(
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_BOT.value,
        ),
        format=TournamentFormat.FIXED_LINEUP_BATCH,
        seed_blocks=1,
        seat_rotation_enabled=False,
    )

    HeadlessTournamentRunner().run(config)

    assert slept["count"] == 0
