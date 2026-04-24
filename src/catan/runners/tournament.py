from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
import json
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.enums import DevelopmentCardType
from catan.core.models.state import GameState, InitialGameConfig
from catan.controllers.heuristic_v2_profiling import GLOBAL_V2_PROFILING_STATS
from catan.runners.game_setup import GameLaunchConfig, PlayerSlotConfig
from catan.runners.headless_runner import HeadlessRunner
from catan.runners.launcher import create_controllers


class TournamentFormat(str, Enum):
    FIXED_LINEUP_BATCH = "fixed_lineup_batch"
    ROUND_ROBIN = "round_robin"


@dataclass(frozen=True)
class TournamentOutputOptions:
    write_json: bool = True
    write_csv: bool = True
    output_dir: str = "tournament_results"
    output_prefix: str = "tournament"


@dataclass(frozen=True)
class TournamentConfig:
    selected_bots: tuple[str, ...]
    format: TournamentFormat
    seed_blocks: int
    seat_rotation_enabled: bool = True
    base_seed: int = 1
    fixed_lineup: tuple[str, ...] | None = None
    output_options: TournamentOutputOptions = TournamentOutputOptions()
    enable_v2_profiling: bool = False


@dataclass(frozen=True)
class MatchConfig:
    lineup: tuple[str, ...]
    seed: int
    seat_order: tuple[str, ...]
    game_index_within_seed_block: int
    seat_rotation_block_id: int


@dataclass(frozen=True)
class MatchSeatResult:
    bot_id: str
    vp_visible: int
    vp_total: int
    hidden_vp_count: int
    final_rank: int
    knights_played: int
    longest_road_length: int
    has_largest_army: bool
    has_longest_road: bool
    roads_built: int
    settlements_built: int
    cities_built: int
    dev_cards_bought: int
    dev_cards_played: int
    bank_trades_count: int
    player_trades_proposed: int
    player_trades_completed: int
    total_resources_in_hand: int
    total_dev_cards_in_hand: int


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    tournament_id: str
    lineup: tuple[str, ...]
    seat_order: tuple[str, ...]
    seed: int
    game_index_within_seed_block: int
    seat_rotation_block_id: int
    winner_bot_id: str | None
    winner_seat: int | None
    turn_count: int
    full_turn_count: int
    seat_results: tuple[MatchSeatResult, MatchSeatResult, MatchSeatResult, MatchSeatResult]

    @property
    def winner(self) -> str | None:
        return self.winner_bot_id

    @property
    def final_vp_by_seat(self) -> tuple[int, int, int, int]:
        return tuple(seat.vp_total for seat in self.seat_results)

    @property
    def rank_by_seat(self) -> tuple[int, int, int, int]:
        return tuple(seat.final_rank for seat in self.seat_results)

    @property
    def largest_army_holder(self) -> str | None:
        holders = [seat.bot_id for seat in self.seat_results if seat.has_largest_army]
        return holders[0] if holders else None

    @property
    def longest_road_holder(self) -> str | None:
        holders = [seat.bot_id for seat in self.seat_results if seat.has_longest_road]
        return holders[0] if holders else None


@dataclass(frozen=True)
class BotAggregate:
    bot_id: str
    games_played: int
    wins: int
    win_rate: float
    average_final_vp_total: float
    average_final_vp_visible: float
    average_rank: float
    average_turn_count: float
    average_knights_played: float
    average_longest_road_length: float
    largest_army_claim_count: int
    longest_road_claim_count: int
    average_dev_cards_bought: float
    average_dev_cards_played: float
    average_bank_trades_count: float
    average_player_trades_completed: float
    performance_by_seat: dict[int, dict[str, float]]

    @property
    def average_final_vp(self) -> float:
        return self.average_final_vp_total

    @property
    def average_turns_per_game(self) -> float:
        return self.average_turn_count

    @property
    def largest_army_wins(self) -> int:
        return self.largest_army_claim_count

    @property
    def longest_road_wins(self) -> int:
        return self.longest_road_claim_count


@dataclass(frozen=True)
class TournamentResult:
    config: TournamentConfig
    tournament_id: str
    matches: tuple[MatchResult, ...]
    aggregates: dict[str, BotAggregate]



def _rotated(order: tuple[str, ...], shift: int) -> tuple[str, ...]:
    return order[shift:] + order[:shift]


def _next_tournament_sequence(config: TournamentConfig) -> int:
    out_dir = Path(config.output_options.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counter_path = out_dir / ".tournament_counter"
    if counter_path.exists():
        try:
            last_sequence = int(counter_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            last_sequence = 0
    else:
        last_sequence = 0
    next_sequence = last_sequence + 1
    counter_path.write_text(str(next_sequence), encoding="utf-8")
    return next_sequence


def _build_tournament_id(config: TournamentConfig, sequence: int) -> str:
    return (
        f"{config.output_options.output_prefix}_"
        f"{config.format.value}_{config.base_seed}_{config.seed_blocks}_{sequence}"
    )


def generate_lineups(config: TournamentConfig) -> tuple[tuple[str, ...], ...]:
    if config.format == TournamentFormat.FIXED_LINEUP_BATCH:
        lineup = config.fixed_lineup if config.fixed_lineup is not None else config.selected_bots
        if len(lineup) != 4:
            raise ValueError("Fixed Lineup Batch requires exactly 4 bots.")
        return (tuple(lineup),)
    if len(config.selected_bots) < 4:
        raise ValueError("Round robin requires at least 4 bots.")
    return tuple(combinations(config.selected_bots, 4))


def generate_match_configs(config: TournamentConfig) -> tuple[MatchConfig, ...]:
    matches: list[MatchConfig] = []
    seat_rotation_block_id = 0
    for lineup in generate_lineups(config):
        for block_idx in range(config.seed_blocks):
            seed = config.base_seed + block_idx
            if config.seat_rotation_enabled:
                for rotation in range(4):
                    matches.append(
                        MatchConfig(
                            lineup=lineup,
                            seed=seed,
                            seat_order=_rotated(lineup, rotation),
                            game_index_within_seed_block=rotation,
                            seat_rotation_block_id=seat_rotation_block_id,
                        )
                    )
                seat_rotation_block_id += 1
            else:
                matches.append(
                    MatchConfig(
                        lineup=lineup,
                        seed=seed,
                        seat_order=lineup,
                        game_index_within_seed_block=0,
                        seat_rotation_block_id=seat_rotation_block_id,
                    )
                )
                seat_rotation_block_id += 1
    return tuple(matches)


class HeadlessTournamentRunner:
    def __init__(self) -> None:
        self._game_runner = HeadlessRunner()

    def run(
        self,
        config: TournamentConfig,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> TournamentResult:
        tournament_sequence = _next_tournament_sequence(config)
        tournament_id = _build_tournament_id(config, tournament_sequence)
        if config.enable_v2_profiling:
            GLOBAL_V2_PROFILING_STATS.reset()
        matches = generate_match_configs(config)
        if progress_callback is not None:
            progress_callback(0, len(matches))
        results: list[MatchResult] = []
        for idx, match in enumerate(matches, start=1):
            results.append(self._play_match(match, match_index=idx, tournament_id=tournament_id, config=config))
            if progress_callback is not None:
                progress_callback(idx, len(matches))
        result = TournamentResult(
            config=config,
            tournament_id=tournament_id,
            matches=tuple(results),
            aggregates=aggregate_results(tuple(results)),
        )
        if config.enable_v2_profiling:
            profile_path = Path(config.output_options.output_dir) / f"{result.tournament_id}_v2_profile.json"
            GLOBAL_V2_PROFILING_STATS.write_json(profile_path)
            print(GLOBAL_V2_PROFILING_STATS.formatted_summary())
            print(f"V2 profiling JSON: {profile_path}")
        return result

    def _play_match(self, match: MatchConfig, match_index: int, tournament_id: str, config: TournamentConfig) -> MatchResult:
        board = build_classic_19_tile_board(seed=match.seed)
        state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=match.seed))
        controllers = create_controllers(
            _to_launch_config(match.seat_order, match.seed),
            enable_bot_delay=False,
            enable_v2_profiling=config.enable_v2_profiling,
        )
        final_state, step_count, full_turn_count = self._game_runner.play_until_terminal_with_steps(
            state,
            controllers,
            max_steps=100_000,
        )
        seat_vps = tuple(_total_victory_points(final_state, idx + 1) for idx in range(4))
        ranks = _ranks_from_vps(seat_vps)

        winner_bot_id: str | None = None
        winner_seat: int | None = final_state.winner
        if final_state.winner is not None:
            winner_bot_id = match.seat_order[final_state.winner - 1]

        seat_results = tuple(
            _build_seat_result(final_state, match.seat_order, seat_index, ranks[seat_index]) for seat_index in range(4)
        )
        return MatchResult(
            match_id=f"match_{match_index:05d}",
            tournament_id=tournament_id,
            lineup=match.lineup,
            seat_order=match.seat_order,
            seed=match.seed,
            game_index_within_seed_block=match.game_index_within_seed_block,
            seat_rotation_block_id=match.seat_rotation_block_id,
            winner_bot_id=winner_bot_id,
            winner_seat=winner_seat,
            turn_count=step_count,
            full_turn_count=full_turn_count,
            seat_results=seat_results,
        )


def _build_seat_result(state: GameState, seat_order: tuple[str, ...], seat_index: int, final_rank: int) -> MatchSeatResult:
    player_id = seat_index + 1
    player = state.players[player_id]
    hidden_vp = player.dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
    return MatchSeatResult(
        bot_id=seat_order[seat_index],
        vp_visible=_visible_victory_points(state, player_id),
        vp_total=_total_victory_points(state, player_id),
        hidden_vp_count=hidden_vp,
        final_rank=final_rank,
        knights_played=player.knights_played,
        longest_road_length=player.longest_road_length,
        has_largest_army=state.largest_army_holder == player_id,
        has_longest_road=state.longest_road_holder == player_id,
        roads_built=15 - player.roads_left,
        settlements_built=_settlements_built_count(state, player_id),
        cities_built=4 - player.cities_left,
        dev_cards_bought=player.dev_cards_bought,
        dev_cards_played=player.dev_cards_played,
        bank_trades_count=player.bank_trades_count,
        player_trades_proposed=player.player_trades_proposed,
        player_trades_completed=player.player_trades_completed,
        total_resources_in_hand=sum(player.resources.values()),
        total_dev_cards_in_hand=sum(player.dev_cards.values()),
    )


def _settlements_built_count(state: GameState, player_id: int) -> int:
    active_settlements = sum(1 for owner in state.placed.settlements.values() if owner == player_id)
    owned_cities = sum(1 for owner in state.placed.cities.values() if owner == player_id)
    return active_settlements + owned_cities


def _ranks_from_vps(vps: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    ordered = sorted(((vp, idx) for idx, vp in enumerate(vps)), key=lambda item: (-item[0], item[1]))
    ranks = [0, 0, 0, 0]
    current_rank = 1
    for pos, (_, idx) in enumerate(ordered):
        if pos > 0 and ordered[pos][0] < ordered[pos - 1][0]:
            current_rank = pos + 1
        ranks[idx] = current_rank
    return tuple(ranks)


def aggregate_results(matches: tuple[MatchResult, ...]) -> dict[str, BotAggregate]:
    by_bot: dict[str, list[tuple[MatchResult, int, MatchSeatResult]]] = {}
    for match in matches:
        for seat_index, seat_result in enumerate(match.seat_results):
            by_bot.setdefault(seat_result.bot_id, []).append((match, seat_index, seat_result))

    aggregates: dict[str, BotAggregate] = {}
    for bot, entries in by_bot.items():
        games = len(entries)
        wins = sum(1 for match, _, _ in entries if match.winner_bot_id == bot)
        by_seat: dict[int, dict[str, float]] = {}
        for seat in range(4):
            seat_entries = [(m, sr) for m, seat_index, sr in entries if seat_index == seat]
            seat_games = len(seat_entries)
            if seat_games == 0:
                by_seat[seat + 1] = {"games": 0.0, "wins": 0.0, "win_rate": 0.0}
                continue
            seat_wins = sum(1 for match, _ in seat_entries if match.winner_bot_id == bot)
            by_seat[seat + 1] = {
                "games": float(seat_games),
                "wins": float(seat_wins),
                "win_rate": float(seat_wins / seat_games),
            }

        aggregates[bot] = BotAggregate(
            bot_id=bot,
            games_played=games,
            wins=wins,
            win_rate=(wins / games) if games else 0.0,
            average_final_vp_total=float(mean(seat.vp_total for _, _, seat in entries)) if games else 0.0,
            average_final_vp_visible=float(mean(seat.vp_visible for _, _, seat in entries)) if games else 0.0,
            average_rank=float(mean(seat.final_rank for _, _, seat in entries)) if games else 0.0,
            average_turn_count=float(mean(match.turn_count for match, _, _ in entries)) if games else 0.0,
            average_knights_played=float(mean(seat.knights_played for _, _, seat in entries)) if games else 0.0,
            average_longest_road_length=float(mean(seat.longest_road_length for _, _, seat in entries)) if games else 0.0,
            largest_army_claim_count=sum(1 for _, _, seat in entries if seat.has_largest_army),
            longest_road_claim_count=sum(1 for _, _, seat in entries if seat.has_longest_road),
            average_dev_cards_bought=float(mean(seat.dev_cards_bought for _, _, seat in entries)) if games else 0.0,
            average_dev_cards_played=float(mean(seat.dev_cards_played for _, _, seat in entries)) if games else 0.0,
            average_bank_trades_count=float(mean(seat.bank_trades_count for _, _, seat in entries)) if games else 0.0,
            average_player_trades_completed=float(mean(seat.player_trades_completed for _, _, seat in entries)) if games else 0.0,
            performance_by_seat=by_seat,
        )
    return aggregates


def export_tournament_result(result: TournamentResult) -> tuple[Path | None, Path | None]:
    opts = result.config.output_options
    out_dir = Path(opts.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = result.tournament_id
    json_path = out_dir / f"{stem}.json" if opts.write_json else None
    match_excel_path = out_dir / f"{stem}_match_results.xlsx" if opts.write_csv else None
    summary_excel_path = out_dir / f"{stem}_tournament_summary.xlsx" if opts.write_csv else None

    if json_path is not None:
        payload = {
            "tournament_id": result.tournament_id,
            "config": {
                "selected_bots": list(result.config.selected_bots),
                "format": result.config.format.value,
                "seed_blocks": result.config.seed_blocks,
                "seat_rotation_enabled": result.config.seat_rotation_enabled,
                "base_seed": result.config.base_seed,
            },
            "matches": [
                {
                    "match_id": match.match_id,
                    "tournament_id": match.tournament_id,
                    "lineup": list(match.lineup),
                    "seat_order": list(match.seat_order),
                    "seed": match.seed,
                    "game_index_within_seed_block": match.game_index_within_seed_block,
                    "seat_rotation_block_id": match.seat_rotation_block_id,
                    "winner_bot_id": match.winner_bot_id,
                    "winner_seat": match.winner_seat,
                    "turn_count": match.turn_count,
                    "full_turn_count": match.full_turn_count,
                    "seat_results": [
                        {
                            "seat": seat_idx,
                            "bot_id": seat_result.bot_id,
                            "vp_visible": seat_result.vp_visible,
                            "vp_total": seat_result.vp_total,
                            "hidden_vp_count": seat_result.hidden_vp_count,
                            "final_rank": seat_result.final_rank,
                            "knights_played": seat_result.knights_played,
                            "longest_road_length": seat_result.longest_road_length,
                            "has_largest_army": seat_result.has_largest_army,
                            "has_longest_road": seat_result.has_longest_road,
                            "roads_built": seat_result.roads_built,
                            "settlements_built": seat_result.settlements_built,
                            "cities_built": seat_result.cities_built,
                            "dev_cards_bought": seat_result.dev_cards_bought,
                            "dev_cards_played": seat_result.dev_cards_played,
                            "bank_trades_count": seat_result.bank_trades_count,
                            "player_trades_proposed": seat_result.player_trades_proposed,
                            "player_trades_completed": seat_result.player_trades_completed,
                            "total_resources_in_hand": seat_result.total_resources_in_hand,
                            "total_dev_cards_in_hand": seat_result.total_dev_cards_in_hand,
                        }
                        for seat_idx, seat_result in enumerate(match.seat_results, start=1)
                    ],
                }
                for match in result.matches
            ],
            "aggregates": {
                bot: {
                    "games_played": agg.games_played,
                    "wins": agg.wins,
                    "win_rate": agg.win_rate,
                    "average_final_vp_total": agg.average_final_vp_total,
                    "average_final_vp_visible": agg.average_final_vp_visible,
                    "average_rank": agg.average_rank,
                    "average_turn_count": agg.average_turn_count,
                    "average_knights_played": agg.average_knights_played,
                    "average_longest_road_length": agg.average_longest_road_length,
                    "largest_army_claim_count": agg.largest_army_claim_count,
                    "longest_road_claim_count": agg.longest_road_claim_count,
                    "average_dev_cards_bought": agg.average_dev_cards_bought,
                    "average_dev_cards_played": agg.average_dev_cards_played,
                    "average_bank_trades_count": agg.average_bank_trades_count,
                    "average_player_trades_completed": agg.average_player_trades_completed,
                    "performance_by_seat": agg.performance_by_seat,
                }
                for bot, agg in result.aggregates.items()
            },
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if match_excel_path is not None:
        _write_single_sheet_xlsx(
            match_excel_path,
            "match_results",
            _match_csv_headers(),
            (_match_csv_row(match) for match in result.matches),
        )

    if summary_excel_path is not None:
        _write_single_sheet_xlsx(
            summary_excel_path,
            "tournament_summary",
            _summary_csv_headers(),
            (_summary_csv_row(result.aggregates[bot_id]) for bot_id in sorted(result.aggregates)),
        )

    return json_path, match_excel_path


def _match_csv_headers() -> list[str]:
    headers = [
        "match_id",
        "tournament_id",
        "seed",
        "lineup",
        "seat_order",
        "game_index_within_seed_block",
        "seat_rotation_block_id",
        "winner_bot_id",
        "winner_seat",
        "turn_count",
        "full_turn_count",
    ]
    for seat in range(1, 5):
        prefix = f"seat{seat}"
        headers.extend(
            [
                f"{prefix}_bot_id",
                f"{prefix}_vp_visible",
                f"{prefix}_vp_total",
                f"{prefix}_hidden_vp_count",
                f"{prefix}_final_rank",
                f"{prefix}_knights_played",
                f"{prefix}_longest_road_length",
                f"{prefix}_has_largest_army",
                f"{prefix}_has_longest_road",
                f"{prefix}_roads_built",
                f"{prefix}_settlements_built",
                f"{prefix}_cities_built",
                f"{prefix}_dev_cards_bought",
                f"{prefix}_dev_cards_played",
                f"{prefix}_bank_trades_count",
                f"{prefix}_player_trades_proposed",
                f"{prefix}_player_trades_completed",
                f"{prefix}_total_resources_in_hand",
                f"{prefix}_total_dev_cards_in_hand",
            ]
        )
    return headers


def _match_csv_row(match: MatchResult) -> list[str | int | bool]:
    row: list[str | int | bool] = [
        match.match_id,
        match.tournament_id,
        match.seed,
        ";".join(match.lineup),
        ";".join(match.seat_order),
        match.game_index_within_seed_block,
        match.seat_rotation_block_id,
        "" if match.winner_bot_id is None else match.winner_bot_id,
        "" if match.winner_seat is None else match.winner_seat,
        match.turn_count,
        match.full_turn_count,
    ]
    for seat_result in match.seat_results:
        row.extend(
            [
                seat_result.bot_id,
                seat_result.vp_visible,
                seat_result.vp_total,
                seat_result.hidden_vp_count,
                seat_result.final_rank,
                seat_result.knights_played,
                seat_result.longest_road_length,
                seat_result.has_largest_army,
                seat_result.has_longest_road,
                seat_result.roads_built,
                seat_result.settlements_built,
                seat_result.cities_built,
                seat_result.dev_cards_bought,
                seat_result.dev_cards_played,
                seat_result.bank_trades_count,
                seat_result.player_trades_proposed,
                seat_result.player_trades_completed,
                seat_result.total_resources_in_hand,
                seat_result.total_dev_cards_in_hand,
            ]
        )
    return row


def _summary_csv_headers() -> list[str]:
    return [
        "bot_id",
        "games_played",
        "wins",
        "win_rate",
        "average_final_vp_total",
        "average_final_vp_visible",
        "average_rank",
        "average_turn_count",
        "average_knights_played",
        "average_longest_road_length",
        "largest_army_claim_count",
        "longest_road_claim_count",
        "average_dev_cards_bought",
        "average_dev_cards_played",
        "average_bank_trades_count",
        "average_player_trades_completed",
        "seat1_games",
        "seat1_wins",
        "seat1_win_rate",
        "seat2_games",
        "seat2_wins",
        "seat2_win_rate",
        "seat3_games",
        "seat3_wins",
        "seat3_win_rate",
        "seat4_games",
        "seat4_wins",
        "seat4_win_rate",
    ]


def _summary_csv_row(aggregate: BotAggregate) -> list[str | int | float]:
    row: list[str | int | float] = [
        aggregate.bot_id,
        aggregate.games_played,
        aggregate.wins,
        aggregate.win_rate,
        aggregate.average_final_vp_total,
        aggregate.average_final_vp_visible,
        aggregate.average_rank,
        aggregate.average_turn_count,
        aggregate.average_knights_played,
        aggregate.average_longest_road_length,
        aggregate.largest_army_claim_count,
        aggregate.longest_road_claim_count,
        aggregate.average_dev_cards_bought,
        aggregate.average_dev_cards_played,
        aggregate.average_bank_trades_count,
        aggregate.average_player_trades_completed,
    ]
    for seat in range(1, 5):
        seat_data = aggregate.performance_by_seat.get(seat, {"games": 0.0, "wins": 0.0, "win_rate": 0.0})
        row.extend([seat_data["games"], seat_data["wins"], seat_data["win_rate"]])
    return row


def _write_single_sheet_xlsx(
    path: Path,
    sheet_name: str,
    headers: list[str],
    rows: Iterable[list[str | int | float | bool]],
) -> None:
    all_rows = [headers, *list(rows)]
    sheet_xml = _sheet_xml(all_rows)
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _sheet_xml(rows: list[list[str | int | float | bool]]) -> str:
    body_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{_excel_column_name(col_index)}{row_index}"
            if isinstance(value, bool):
                cell = f'<c r="{cell_ref}" t="b"><v>{1 if value else 0}</v></c>'
            elif isinstance(value, (int, float)):
                cell = f'<c r="{cell_ref}"><v>{value}</v></c>'
            else:
                text = escape(str(value))
                cell = f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'
            cells.append(cell)
        body_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(body_rows)}</sheetData>"
        "</worksheet>"
    )


def _excel_column_name(index: int) -> str:
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _to_launch_config(seat_order: tuple[str, ...], seed: int) -> GameLaunchConfig:
    return GameLaunchConfig(
        player_slots=tuple(PlayerSlotConfig(player_id=idx + 1, controller_key=controller) for idx, controller in enumerate(seat_order)),
        seed=seed,
    )


def _visible_victory_points(state: GameState, player_id: int) -> int:
    visible = state.players[player_id].victory_points
    if state.largest_army_holder == player_id:
        visible += 2
    if state.longest_road_holder == player_id:
        visible += 2
    return visible


def _total_victory_points(state: GameState, player_id: int) -> int:
    total = _visible_victory_points(state, player_id)
    total += state.players[player_id].dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
    return total
