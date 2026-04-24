from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Mapping

from catan.controllers.base import Controller
from catan.controllers.human_controller import HumanController
from catan.core.engine import apply_action, get_legal_actions, get_observation, is_terminal
from catan.core.models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    ChooseMonopolyResource,
    ChooseTradePartner,
    ChooseYearOfPlentyResources,
    EndTurn,
    FinishRoadBuildingCard,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
)
from catan.core.models.enums import DevelopmentCardType
from catan.core.models.state import GameState


@dataclass(frozen=True)
class StuckGameConfig:
    no_vp_change_step_limit: int = 2_000
    no_progress_step_limit: int = 1_200
    low_impact_cycle_window: int = 24


@dataclass(frozen=True)
class HeadlessRunResult:
    final_state: GameState
    steps: int
    full_turn_count: int
    termination_reason: str
    stalled_debug_snapshot: dict[str, object] | None = None


class HeadlessRunner:
    def play_until_terminal(self, state: GameState, controllers: Mapping[int, Controller], max_steps: int = 10_000) -> GameState:
        final_state, _, _ = self.play_until_terminal_with_steps(state, controllers, max_steps=max_steps)
        return final_state

    def play_until_terminal_with_steps(
        self,
        state: GameState,
        controllers: Mapping[int, Controller],
        max_steps: int = 10_000,
    ) -> tuple[GameState, int, int]:
        result = self.play_until_terminal_with_result(
            state,
            controllers,
            max_steps=max_steps,
        )
        return result.final_state, result.steps, result.full_turn_count

    def play_until_terminal_with_result(
        self,
        state: GameState,
        controllers: Mapping[int, Controller],
        max_steps: int = 10_000,
        stuck_config: StuckGameConfig = StuckGameConfig(),
    ) -> HeadlessRunResult:
        steps = 0
        completed_turn_actions = 0
        current = state
        steps_since_vp_change = 0
        steps_since_progress = 0
        last_actions: deque[str] = deque(maxlen=50)
        last_events: deque[str] = deque(maxlen=50)
        low_impact_signatures: deque[str] = deque(maxlen=max(2, stuck_config.low_impact_cycle_window))
        termination_reason = "max_steps"
        stalled_reason: str | None = None

        while not is_terminal(current) and steps < max_steps:
            if current.turn is None and current.phase.name.startswith("SETUP") is False:
                termination_reason = "stalled"
                stalled_reason = "no_turn_state"
                break
            player_id = self._active_player(current)
            if player_id is None:
                termination_reason = "stalled"
                stalled_reason = "no_active_player"
                break
            controller = controllers[player_id]
            legal = get_legal_actions(current, player_id)
            observation = get_observation(current, player_id, debug=not isinstance(controller, HumanController))
            if not legal:
                termination_reason = "stalled"
                stalled_reason = "no_legal_actions"
                break
            action = controller.choose_action(observation, legal)
            next_state = apply_action(current, action)
            if isinstance(action, EndTurn):
                completed_turn_actions += 1
            steps += 1
            steps_since_vp_change += 1
            steps_since_progress += 1

            action_name = type(action).__name__
            last_actions.append(f"step={steps} p{player_id} {action_name}")
            if action_name in _LOW_IMPACT_ACTION_NAMES:
                low_impact_signatures.append(f"p{player_id}:{action_name}")
            else:
                low_impact_signatures.clear()

            if _vp_totals(next_state) != _vp_totals(current):
                steps_since_vp_change = 0
                last_events.append(f"step={steps} vp_change")
            progress_events = _progress_events(current, next_state, action)
            if progress_events:
                steps_since_progress = 0
                for event in progress_events:
                    last_events.append(f"step={steps} {event}")

            current = next_state

            if steps_since_vp_change >= stuck_config.no_vp_change_step_limit:
                termination_reason = "stalled"
                stalled_reason = "no_vp_change_limit"
                break
            if steps_since_progress >= stuck_config.no_progress_step_limit:
                termination_reason = "stalled"
                stalled_reason = "no_progress_limit"
                break
            if _has_repeated_low_impact_cycle(low_impact_signatures):
                termination_reason = "stalled"
                stalled_reason = "repeated_low_impact_cycle"
                break

        if is_terminal(current):
            termination_reason = "win"
        elif termination_reason != "stalled":
            termination_reason = "max_steps"

        player_count = len(current.players)
        full_turn_count = completed_turn_actions // player_count if player_count else 0
        stalled_debug_snapshot: dict[str, object] | None = None
        if termination_reason in {"stalled", "max_steps"}:
            stalled_debug_snapshot = self._build_stalled_debug_snapshot(
                state=current,
                controllers=controllers,
                last_actions=list(last_actions),
                last_events=list(last_events),
                stalled_reason=stalled_reason,
                steps=steps,
            )
        return HeadlessRunResult(
            final_state=current,
            steps=steps,
            full_turn_count=full_turn_count,
            termination_reason=termination_reason,
            stalled_debug_snapshot=stalled_debug_snapshot,
        )

    def _active_player(self, state: GameState) -> int | None:
        if state.turn is not None and state.turn.priority_player is not None:
            return state.turn.priority_player
        if state.turn is not None:
            return state.turn.current_player
        return state.setup.pending_settlement_player or state.setup.pending_road_player

    def _build_stalled_debug_snapshot(
        self,
        *,
        state: GameState,
        controllers: Mapping[int, Controller],
        last_actions: list[str],
        last_events: list[str],
        stalled_reason: str | None,
        steps: int,
    ) -> dict[str, object]:
        active_player = self._active_player(state)
        legal_counts: dict[str, int] = {}
        if active_player is not None and active_player in controllers:
            legal = get_legal_actions(state, active_player)
            legal_counts = dict(Counter(type(action).__name__ for action in legal))

        players = []
        for pid in sorted(state.players):
            player = state.players[pid]
            players.append(
                {
                    "player_id": pid,
                    "vp_total": _player_total_vp(state, pid),
                    "resources_total": int(sum(player.resources.values())),
                    "dev_cards_total": int(sum(player.dev_cards.values()) + sum(player.new_dev_cards.values())),
                    "roads_built": 15 - player.roads_left,
                    "settlements_built": _settlements_built_count(state, pid),
                    "cities_built": 4 - player.cities_left,
                }
            )

        return {
            "reason_detail": stalled_reason,
            "phase": state.phase.name,
            "turn_step": state.turn.step.name if state.turn is not None else None,
            "step": steps,
            "current_player": state.turn.current_player if state.turn is not None else None,
            "priority_player": state.turn.priority_player if state.turn is not None else None,
            "legal_action_counts": legal_counts,
            "last_50_actions": last_actions[-50:],
            "last_50_events": last_events[-50:],
            "player_summaries": players,
        }


_LOW_IMPACT_ACTION_NAMES = {
    "EndTurn",
    "RollDice",
    "RespondToTradePass",
    "RespondToTradeInterested",
    "RejectTradeResponses",
    "SkipSteal",
}

_MEANINGFUL_ACTION_TYPES = (
    BuildRoad,
    BuildSettlement,
    BuildCity,
    BuyDevelopmentCard,
    PlayKnightCard,
    PlayRoadBuildingCard,
    FinishRoadBuildingCard,
    PlayYearOfPlentyCard,
    ChooseYearOfPlentyResources,
    PlayMonopolyCard,
    ChooseMonopolyResource,
    BankTrade,
    ChooseTradePartner,
)


def _has_repeated_low_impact_cycle(signatures: deque[str]) -> bool:
    values = list(signatures)
    if len(values) < 8 or len(values) % 2 != 0:
        return False
    half = len(values) // 2
    return values[:half] == values[half:]


def _vp_totals(state: GameState) -> tuple[int, ...]:
    return tuple(_player_total_vp(state, pid) for pid in sorted(state.players))


def _player_total_vp(state: GameState, player_id: int) -> int:
    player = state.players[player_id]
    total = player.victory_points
    if state.largest_army_holder == player_id:
        total += 2
    if state.longest_road_holder == player_id:
        total += 2
    total += player.dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
    return total


def _settlements_built_count(state: GameState, player_id: int) -> int:
    active_settlements = sum(1 for owner in state.placed.settlements.values() if owner == player_id)
    owned_cities = sum(1 for owner in state.placed.cities.values() if owner == player_id)
    return active_settlements + owned_cities


def _progress_events(before: GameState, after: GameState, action: Action) -> list[str]:
    events: list[str] = []
    if isinstance(action, _MEANINGFUL_ACTION_TYPES):
        events.append(f"meaningful_action:{type(action).__name__}")

    if before.largest_army_holder != after.largest_army_holder:
        events.append("largest_army_changed")
    if before.longest_road_holder != after.longest_road_holder:
        events.append("longest_road_changed")

    for pid in before.players:
        prev_player = before.players[pid]
        next_player = after.players[pid]
        if next_player.player_trades_completed > prev_player.player_trades_completed:
            events.append(f"successful_trade:p{pid}")
        if next_player.bank_trades_count > prev_player.bank_trades_count:
            events.append(f"bank_trade:p{pid}")
    return events
