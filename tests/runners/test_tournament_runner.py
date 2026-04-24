from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import EndTurn
from catan.core.models.state import InitialGameConfig
from catan.runners.headless_runner import HeadlessRunner, StuckGameConfig
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
        enable_v2_profiling=True,
    )

    config = state.to_tournament_config()

    assert config is not None
    assert config.seed_blocks == 3
    assert config.base_seed == 10
    assert config.enable_v2_profiling is True
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
    assert result.matches[0].termination_reason in {"win", "stalled", "max_steps"}
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
    if result.matches[0].termination_reason == "win":
        assert winner is not None
        assert max(result.matches[0].final_vp_by_seat) >= 10
    assert result.matches[0].turn_count > 0
    assert result.matches[0].full_turn_count >= 0
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


def test_headless_tournament_runner_writes_v2_profile_summary_when_enabled(tmp_path: Path) -> None:
    config = TournamentConfig(
        selected_bots=(ControllerType.HEURISTIC_V2_POSITIONAL.value, ControllerType.RANDOM_BOT.value),
        fixed_lineup=(
            ControllerType.HEURISTIC_V2_POSITIONAL.value,
            ControllerType.RANDOM_BOT.value,
            ControllerType.HEURISTIC_V2_POSITIONAL.value,
            ControllerType.RANDOM_BOT.value,
        ),
        format=TournamentFormat.FIXED_LINEUP_BATCH,
        seed_blocks=1,
        seat_rotation_enabled=False,
        output_options=TournamentOutputOptions(write_json=False, write_csv=False, output_dir=str(tmp_path), output_prefix="profile_test"),
        enable_v2_profiling=True,
    )

    result = HeadlessTournamentRunner().run(config)

    profile_path = tmp_path / f"{result.tournament_id}_v2_profile.json"
    assert profile_path.exists()
    assert "\"decisions\"" in profile_path.read_text(encoding="utf-8")


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
            termination_reason="win",
            match_duration_seconds=12.5,
            turn_count=120,
            full_turn_count=30,
            debug_snapshot=None,
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
                    total_resources_earned=14,
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
                    total_resources_earned=11,
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
                    total_resources_earned=9,
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
                    total_resources_earned=6,
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


def test_export_json_and_excel(tmp_path: Path) -> None:
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

    json_path, excel_path = export_tournament_result(result)

    assert json_path is not None and json_path.exists()
    assert excel_path is not None and excel_path.exists()
    summary_excel = tmp_path / "test_fixed_lineup_batch_1_1_1_tournament_summary.xlsx"
    assert summary_excel.exists()

    match_rows = _read_xlsx_rows(excel_path)
    summary_rows = _read_xlsx_rows(summary_excel)

    assert len(match_rows) - 1 == len(result.matches)
    assert len(summary_rows) - 1 == len(result.aggregates)
    assert "match_id" in match_rows[0]
    assert "full_turn_count" in match_rows[0]
    assert "termination_reason" in match_rows[0]
    assert "match_duration_seconds" in match_rows[0]
    assert "seat1_vp_total" in match_rows[0]
    assert "seat1_total_resources_earned" in match_rows[0]
    assert "seat1_total_resources_in_hand" not in match_rows[0]
    assert "average_final_vp_total" in summary_rows[0]
    payload = json_path.read_text(encoding="utf-8")
    assert "\"completed_games\"" in payload
    assert "\"stalled_games\"" in payload
    assert "\"max_step_games\"" in payload


def test_tournament_id_increments_between_runs(tmp_path: Path) -> None:
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

    first = HeadlessTournamentRunner().run(config)
    second = HeadlessTournamentRunner().run(config)

    assert first.tournament_id == "test_fixed_lineup_batch_1_1_1"
    assert second.tournament_id == "test_fixed_lineup_batch_1_1_2"


def _read_xlsx_rows(path: Path) -> list[list[str]]:
    with ZipFile(path, "r") as workbook_zip:
        xml_bytes = workbook_zip.read("xl/worksheets/sheet1.xml")
    root = ElementTree.fromstring(xml_bytes)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []
    for row in root.findall(".//m:row", ns):
        values: list[str] = []
        for cell in row.findall("m:c", ns):
            value_node = cell.find("m:v", ns)
            inline_node = cell.find("m:is/m:t", ns)
            if inline_node is not None and inline_node.text is not None:
                values.append(inline_node.text)
            elif value_node is not None and value_node.text is not None:
                values.append(value_node.text)
            else:
                values.append("")
        rows.append(values)
    return rows


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


def test_max_steps_game_sets_termination_reason_max_steps(monkeypatch) -> None:
    board = build_classic_19_tile_board(seed=1)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=1))
    runner = HeadlessRunner()

    monkeypatch.setattr("catan.runners.headless_runner.is_terminal", lambda _state: False)
    monkeypatch.setattr("catan.runners.headless_runner.get_legal_actions", lambda _state, pid: (EndTurn(player_id=pid),))
    monkeypatch.setattr("catan.runners.headless_runner.apply_action", lambda game_state, _action: game_state)

    controllers = {pid: _DeterministicController() for pid in range(1, 5)}
    result = runner.play_until_terminal_with_result(state, controllers, max_steps=5, stuck_config=StuckGameConfig(no_vp_change_step_limit=999, no_progress_step_limit=999))

    assert result.termination_reason == "max_steps"
    assert result.stalled_debug_snapshot is not None


def test_no_progress_loop_sets_termination_reason_stalled(monkeypatch) -> None:
    board = build_classic_19_tile_board(seed=2)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=2))
    runner = HeadlessRunner()

    monkeypatch.setattr("catan.runners.headless_runner.is_terminal", lambda _state: False)
    monkeypatch.setattr("catan.runners.headless_runner.get_legal_actions", lambda _state, pid: (EndTurn(player_id=pid),))
    monkeypatch.setattr("catan.runners.headless_runner.apply_action", lambda game_state, _action: game_state)

    controllers = {pid: _DeterministicController() for pid in range(1, 5)}
    result = runner.play_until_terminal_with_result(
        state,
        controllers,
        max_steps=100,
        stuck_config=StuckGameConfig(no_vp_change_step_limit=999, no_progress_step_limit=8, low_impact_cycle_window=8),
    )

    assert result.termination_reason == "stalled"
    assert result.stalled_debug_snapshot is not None


def test_completed_game_sets_termination_reason_win() -> None:
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
    assert result.matches[0].termination_reason == "win"


def test_tournament_summary_counts_include_stalled_and_max_step() -> None:
    matches = (
        MatchResult(
            match_id="match_00001",
            tournament_id="test",
            lineup=(ControllerType.RANDOM_BOT.value,) * 4,
            seat_order=(ControllerType.RANDOM_BOT.value,) * 4,
            seed=1,
            game_index_within_seed_block=0,
            seat_rotation_block_id=0,
            winner_bot_id=ControllerType.RANDOM_BOT.value,
            winner_seat=1,
            termination_reason="win",
            match_duration_seconds=1.0,
            turn_count=100,
            full_turn_count=25,
            seat_results=(_seat_result(), _seat_result(), _seat_result(), _seat_result()),
            debug_snapshot=None,
        ),
        MatchResult(
            match_id="match_00002",
            tournament_id="test",
            lineup=(ControllerType.RANDOM_BOT.value,) * 4,
            seat_order=(ControllerType.RANDOM_BOT.value,) * 4,
            seed=2,
            game_index_within_seed_block=0,
            seat_rotation_block_id=0,
            winner_bot_id=None,
            winner_seat=None,
            termination_reason="stalled",
            match_duration_seconds=1.0,
            turn_count=3000,
            full_turn_count=750,
            seat_results=(_seat_result(), _seat_result(), _seat_result(), _seat_result()),
            debug_snapshot={"phase": "MAIN"},
        ),
        MatchResult(
            match_id="match_00003",
            tournament_id="test",
            lineup=(ControllerType.RANDOM_BOT.value,) * 4,
            seat_order=(ControllerType.RANDOM_BOT.value,) * 4,
            seed=3,
            game_index_within_seed_block=0,
            seat_rotation_block_id=0,
            winner_bot_id=None,
            winner_seat=None,
            termination_reason="max_steps",
            match_duration_seconds=1.0,
            turn_count=100_000,
            full_turn_count=25000,
            seat_results=(_seat_result(), _seat_result(), _seat_result(), _seat_result()),
            debug_snapshot={"phase": "MAIN"},
        ),
    )
    summary = aggregate_results(matches)
    tournament_result = HeadlessTournamentRunner().run(
        TournamentConfig(
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
    )
    synthetic = tournament_result.__class__(
        config=tournament_result.config,
        tournament_id="test",
        matches=matches,
        aggregates=summary,
    )
    assert synthetic.completed_games == 1
    assert synthetic.stalled_games == 1
    assert synthetic.max_step_games == 1
    assert synthetic.average_turn_count_completed == 100.0


class _DeterministicController:
    def choose_action(self, _observation, legal_actions):
        return legal_actions[0]


def _seat_result() -> MatchSeatResult:
    return MatchSeatResult(
        bot_id=ControllerType.RANDOM_BOT.value,
        vp_visible=0,
        vp_total=0,
        hidden_vp_count=0,
        final_rank=1,
        knights_played=0,
        longest_road_length=0,
        has_largest_army=False,
        has_longest_road=False,
        roads_built=0,
        settlements_built=0,
        cities_built=0,
        dev_cards_bought=0,
        dev_cards_played=0,
        bank_trades_count=0,
        player_trades_proposed=0,
        player_trades_completed=0,
        total_resources_earned=0,
    )
