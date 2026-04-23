from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Callable

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.enums import DevelopmentCardType
from catan.core.models.state import InitialGameConfig
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


@dataclass(frozen=True)
class MatchConfig:
    lineup: tuple[str, ...]
    seed: int
    seat_order: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    lineup: tuple[str, ...]
    seat_order: tuple[str, ...]
    seed: int
    winner: str | None
    final_vp_by_seat: tuple[int, int, int, int]
    turn_count: int
    rank_by_seat: tuple[int, int, int, int]
    largest_army_holder: str | None
    longest_road_holder: str | None


@dataclass(frozen=True)
class BotAggregate:
    bot_id: str
    games_played: int
    wins: int
    win_rate: float
    average_final_vp: float
    average_rank: float
    average_turns_per_game: float
    performance_by_seat: dict[int, dict[str, float]]
    largest_army_wins: int
    longest_road_wins: int


@dataclass(frozen=True)
class TournamentResult:
    config: TournamentConfig
    matches: tuple[MatchResult, ...]
    aggregates: dict[str, BotAggregate]



def _rotated(order: tuple[str, ...], shift: int) -> tuple[str, ...]:
    return order[shift:] + order[:shift]


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
    for lineup in generate_lineups(config):
        for block_idx in range(config.seed_blocks):
            seed = config.base_seed + block_idx
            if config.seat_rotation_enabled:
                for rotation in range(4):
                    matches.append(MatchConfig(lineup=lineup, seed=seed, seat_order=_rotated(lineup, rotation)))
            else:
                matches.append(MatchConfig(lineup=lineup, seed=seed, seat_order=lineup))
    return tuple(matches)


class HeadlessTournamentRunner:
    def __init__(self) -> None:
        self._game_runner = HeadlessRunner()

    def run(
        self,
        config: TournamentConfig,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> TournamentResult:
        matches = generate_match_configs(config)
        if progress_callback is not None:
            progress_callback(0, len(matches))
        results: list[MatchResult] = []
        for idx, match in enumerate(matches, start=1):
            results.append(self._play_match(match))
            if progress_callback is not None:
                progress_callback(idx, len(matches))
        return TournamentResult(config=config, matches=tuple(results), aggregates=aggregate_results(tuple(results)))

    def _play_match(self, match: MatchConfig) -> MatchResult:
        board = build_classic_19_tile_board(seed=match.seed)
        state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3, 4), board=board, seed=match.seed))
        controllers = create_controllers(
            # map each seat's bot controller type into player slot config order
            _to_launch_config(match.seat_order, match.seed),
            enable_bot_delay=False,
        )
        final_state, step_count = self._game_runner.play_until_terminal_with_steps(state, controllers, max_steps=100_000)
        seat_vps = tuple(_total_victory_points(final_state, idx + 1) for idx in range(4))
        ranks = _ranks_from_vps(seat_vps)

        winner_bot: str | None = None
        if final_state.winner is not None:
            winner_bot = match.seat_order[final_state.winner - 1]

        largest_army_holder = (
            match.seat_order[final_state.largest_army_holder - 1] if final_state.largest_army_holder is not None else None
        )
        longest_road_holder = (
            match.seat_order[final_state.longest_road_holder - 1] if final_state.longest_road_holder is not None else None
        )
        return MatchResult(
            lineup=match.lineup,
            seat_order=match.seat_order,
            seed=match.seed,
            winner=winner_bot,
            final_vp_by_seat=seat_vps,
            turn_count=step_count,
            rank_by_seat=ranks,
            largest_army_holder=largest_army_holder,
            longest_road_holder=longest_road_holder,
        )

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
    by_bot: dict[str, list[tuple[MatchResult, int]]] = {}
    for match in matches:
        for seat_index, bot in enumerate(match.seat_order):
            by_bot.setdefault(bot, []).append((match, seat_index))

    aggregates: dict[str, BotAggregate] = {}
    for bot, entries in by_bot.items():
        games = len(entries)
        wins = sum(1 for match, _ in entries if match.winner == bot)
        avg_vp = mean(match.final_vp_by_seat[seat] for match, seat in entries)
        avg_rank = mean(match.rank_by_seat[seat] for match, seat in entries)
        avg_turns = mean(match.turn_count for match, _ in entries) if entries else 0.0
        by_seat: dict[int, dict[str, float]] = {}
        for seat in range(4):
            seat_entries = [(m, s) for m, s in entries if s == seat]
            if not seat_entries:
                continue
            seat_games = len(seat_entries)
            by_seat[seat + 1] = {
                "games": float(seat_games),
                "wins": float(sum(1 for m, _ in seat_entries if m.winner == bot)),
                "win_rate": float(sum(1 for m, _ in seat_entries if m.winner == bot) / seat_games),
                "average_vp": float(mean(m.final_vp_by_seat[s] for m, s in seat_entries)),
                "average_rank": float(mean(m.rank_by_seat[s] for m, s in seat_entries)),
            }

        aggregates[bot] = BotAggregate(
            bot_id=bot,
            games_played=games,
            wins=wins,
            win_rate=(wins / games) if games else 0.0,
            average_final_vp=float(avg_vp),
            average_rank=float(avg_rank),
            average_turns_per_game=float(avg_turns),
            performance_by_seat=by_seat,
            largest_army_wins=sum(1 for match, _ in entries if match.largest_army_holder == bot),
            longest_road_wins=sum(1 for match, _ in entries if match.longest_road_holder == bot),
        )
    return aggregates


def export_tournament_result(result: TournamentResult) -> tuple[Path | None, Path | None]:
    opts = result.config.output_options
    out_dir = Path(opts.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{opts.output_prefix}_{result.config.format.value}_{result.config.base_seed}_{result.config.seed_blocks}"
    json_path = out_dir / f"{stem}.json" if opts.write_json else None
    csv_path = out_dir / f"{stem}.csv" if opts.write_csv else None

    if json_path is not None:
        payload = {
            "config": {
                "selected_bots": list(result.config.selected_bots),
                "format": result.config.format.value,
                "seed_blocks": result.config.seed_blocks,
                "seat_rotation_enabled": result.config.seat_rotation_enabled,
                "base_seed": result.config.base_seed,
            },
            "matches": [
                {
                    "lineup": list(m.lineup),
                    "seat_order": list(m.seat_order),
                    "seed": m.seed,
                    "winner": m.winner,
                    "final_vp_by_seat": list(m.final_vp_by_seat),
                    "rank_by_seat": list(m.rank_by_seat),
                    "turn_count": m.turn_count,
                }
                for m in result.matches
            ],
            "aggregates": {
                bot: {
                    "games_played": agg.games_played,
                    "wins": agg.wins,
                    "win_rate": agg.win_rate,
                    "average_final_vp": agg.average_final_vp,
                    "average_rank": agg.average_rank,
                    "average_turns_per_game": agg.average_turns_per_game,
                    "largest_army_wins": agg.largest_army_wins,
                    "longest_road_wins": agg.longest_road_wins,
                    "performance_by_seat": agg.performance_by_seat,
                }
                for bot, agg in result.aggregates.items()
            },
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if csv_path is not None:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["seed", "lineup", "seat_order", "winner", "seat1_vp", "seat2_vp", "seat3_vp", "seat4_vp"])
            for match in result.matches:
                writer.writerow(
                    [
                        match.seed,
                        ";".join(match.lineup),
                        ";".join(match.seat_order),
                        "" if match.winner is None else match.winner,
                        *match.final_vp_by_seat,
                    ]
                )
    return json_path, csv_path

def _to_launch_config(seat_order: tuple[str, ...], seed: int) -> GameLaunchConfig:
    return GameLaunchConfig(
        player_slots=tuple(PlayerSlotConfig(player_id=idx + 1, controller_key=controller) for idx, controller in enumerate(seat_order)),
        seed=seed,
    )


def _total_victory_points(state, player_id: int) -> int:
    total = state.players[player_id].victory_points
    if state.largest_army_holder == player_id:
        total += 2
    if state.longest_road_holder == player_id:
        total += 2
    # Hidden VP dev cards count toward win condition and tournament ranking.
    total += state.players[player_id].dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
    return total
