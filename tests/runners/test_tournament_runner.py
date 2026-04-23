from __future__ import annotations

from pathlib import Path
import csv

from catan.runners.game_setup import ControllerType, TournamentSetupState
from catan.runners.tournament import (
    HeadlessTournamentRunner,
    MatchResult,
    MatchSeatResult,
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
    assert all(match.game_index_within_seed_block in (0, 1, 2, 3) for match in matches)
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


def test_winning_match_reports_total_vp_for_winner() -> None:
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

    winner = result.matches[0].winner
    assert winner is not None
    assert max(result.matches[0].final_vp_by_seat) >= 10
    assert result.matches[0].turn_count > 0
    assert result.matches[0].winner_seat in (1, 2, 3, 4)
    assert all(seat.bot_id for seat in result.matches[0].seat_results)
    assert all(seat.vp_total >= seat.vp_visible for seat in result.matches[0].seat_results)


def test_tournament_progress_callback_receives_match_progress_updates() -> None:
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
    updates: list[tuple[int, int]] = []

    HeadlessTournamentRunner().run(config, progress_callback=lambda complete, total: updates.append((complete, total)))

    assert updates == [(0, 1), (1, 1)]


def test_aggregation_correctness() -> None:
    matches = (
        MatchResult(
            match_id="match_00001",
            tournament_id="test",
            lineup=(ControllerType.RANDOM_BOT.value,) * 4,
            seat_order=(ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value, ControllerType.RANDOM_BOT.value, ControllerType.HEURISTIC_BOT.value),
            seed=1,
            game_index_within_seed_block=0,
            seat_rotation_block_id=0,
            winner_bot_id=ControllerType.RANDOM_BOT.value,
            winner_seat=1,
            turn_count=120,
            seat_results=(
                MatchSeatResult(
                    bot_id=ControllerType.RANDOM_BOT.value,
                    vp_visible=10,
                    vp_total=10,
                    hidden_vp_count=0,
                    final_rank=1,
                    knights_played=3,
                    longest_road_length=5,
                    has_largest_army=True,
                    has_longest_road=False,
                    roads_built=10,
                    settlements_built=4,
                    cities_built=2,
                    dev_cards_bought=4,
                    dev_cards_played=3,
                    bank_trades_count=2,
                    player_trades_proposed=1,
                    player_trades_completed=1,
                    total_resources_in_hand=3,
                    total_dev_cards_in_hand=1,
                ),
                MatchSeatResult(
                    bot_id=ControllerType.HEURISTIC_BOT.value,
                    vp_visible=8,
                    vp_total=8,
                    hidden_vp_count=0,
                    final_rank=3,
                    knights_played=1,
                    longest_road_length=6,
                    has_largest_army=False,
                    has_longest_road=True,
                    roads_built=9,
                    settlements_built=3,
                    cities_built=1,
                    dev_cards_bought=2,
                    dev_cards_played=1,
                    bank_trades_count=1,
                    player_trades_proposed=2,
                    player_trades_completed=0,
                    total_resources_in_hand=2,
                    total_dev_cards_in_hand=0,
                ),
                MatchSeatResult(
                    bot_id=ControllerType.RANDOM_BOT.value,
                    vp_visible=8,
                    vp_total=9,
                    hidden_vp_count=1,
                    final_rank=2,
                    knights_played=0,
                    longest_road_length=4,
                    has_largest_army=False,
                    has_longest_road=False,
                    roads_built=8,
                    settlements_built=4,
                    cities_built=1,
                    dev_cards_bought=3,
                    dev_cards_played=0,
                    bank_trades_count=0,
                    player_trades_proposed=0,
                    player_trades_completed=0,
                    total_resources_in_hand=1,
                    total_dev_cards_in_hand=2,
                ),
                MatchSeatResult(
                    bot_id=ControllerType.HEURISTIC_BOT.value,
                    vp_visible=7,
                    vp_total=7,
                    hidden_vp_count=0,
                    final_rank=4,
                    knights_played=0,
                    longest_road_length=3,
                    has_largest_army=False,
                    has_longest_road=False,
                    roads_built=7,
                    settlements_built=3,
                    cities_built=1,
                    dev_cards_bought=1,
                    dev_cards_played=0,
                    bank_trades_count=0,
                    player_trades_proposed=1,
                    player_trades_completed=0,
                    total_resources_in_hand=0,
                    total_dev_cards_in_hand=0,
                ),
            ),
        ),
    )

    aggregates = aggregate_results(matches)

    assert aggregates[ControllerType.RANDOM_BOT.value].wins == 2
    assert aggregates[ControllerType.RANDOM_BOT.value].games_played == 2
    assert aggregates[ControllerType.RANDOM_BOT.value].average_final_vp_total == 9.5
    assert aggregates[ControllerType.HEURISTIC_BOT.value].average_rank == 3.5
    assert aggregates[ControllerType.RANDOM_BOT.value].performance_by_seat[1]["wins"] == 1.0
    assert aggregates[ControllerType.RANDOM_BOT.value].performance_by_seat[3]["games"] == 1.0
    assert aggregates[ControllerType.RANDOM_BOT.value].average_dev_cards_bought == 3.5


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
    summary_csv = tmp_path / "test_fixed_lineup_batch_1_1_tournament_summary.csv"
    assert summary_csv.exists()
    with csv_path.open("r", encoding="utf-8", newline="") as match_file:
        reader = csv.DictReader(match_file)
        rows = list(reader)
    with summary_csv.open("r", encoding="utf-8", newline="") as summary_file:
        summary_rows = list(csv.DictReader(summary_file))
    assert len(rows) == len(result.matches)
    assert len(summary_rows) == len(result.aggregates)
    assert "match_id" in rows[0]
    assert "seat1_vp_total" in rows[0]
    assert "average_final_vp_total" in summary_rows[0]


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
