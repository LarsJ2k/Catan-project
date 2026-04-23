from __future__ import annotations

import random
import time
from typing import Sequence

from catan.core.models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    ChooseTradePartner,
    DiscardResources,
    EndTurn,
    MoveRobber,
    PlaceSetupSettlement,
    PlayKnightCard,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RespondToTradePass,
    RollDice,
)
from catan.core.models.board import NodeId
from catan.core.models.enums import ResourceType, TerrainType
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation

DEFAULT_BOT_ACTION_DELAY_SECONDS = 1.2
_TOKEN_PIP_SCORES = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
_RESOURCE_VALUE = {
    ResourceType.BRICK: 1.0,
    ResourceType.LUMBER: 1.0,
    ResourceType.WOOL: 0.9,
    ResourceType.GRAIN: 1.1,
    ResourceType.ORE: 1.2,
}
_TERRAIN_TO_RESOURCE = {
    TerrainType.HILLS: ResourceType.BRICK,
    TerrainType.FOREST: ResourceType.LUMBER,
    TerrainType.PASTURE: ResourceType.WOOL,
    TerrainType.FIELDS: ResourceType.GRAIN,
    TerrainType.MOUNTAINS: ResourceType.ORE,
}


class HeuristicBotController:
    """Greedy heuristic bot that scores each legal action and picks the best."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        delay_seconds: float = DEFAULT_BOT_ACTION_DELAY_SECONDS,
        enable_delay: bool = True,
    ) -> None:
        self._rng = random.Random(seed)
        self._delay_seconds = delay_seconds
        self._enable_delay = enable_delay

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        candidates = [action for action in legal_actions if not isinstance(action, ProposePlayerTrade)]
        if not candidates:
            raise ValueError("HeuristicBotController received no selectable legal actions.")

        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        state = observation.state if isinstance(observation, DebugObservation) else None
        best_score: float | None = None
        best_actions: list[Action] = []
        for action in candidates:
            score = self._score_action(action, state)
            if best_score is None or score > best_score:
                best_score = score
                best_actions = [action]
            elif score == best_score:
                best_actions.append(action)

        return best_actions[self._rng.randrange(len(best_actions))]

    def _score_action(self, action: Action, state: GameState | None) -> float:
        if isinstance(action, RollDice):
            return 10_000
        if isinstance(action, (PlaceSetupSettlement, BuildSettlement)):
            return 200 + self._score_settlement_node(action.node_id, state)
        if isinstance(action, BuildCity):
            return 180 + self._score_city_node(action.node_id, state)
        if isinstance(action, PlayKnightCard):
            return 135
        if isinstance(action, BuyDevelopmentCard):
            return 105
        if isinstance(action, BuildRoad):
            return 90 + self._score_road(action, state)
        if isinstance(action, BankTrade):
            return self._score_bank_trade(action, state)
        if isinstance(action, MoveRobber):
            return self._score_move_robber(action, state)
        if isinstance(action, RespondToTradeInterested):
            return 75 if self._trade_response_is_good(state) else -20
        if isinstance(action, RespondToTradePass):
            return 30 if self._trade_response_is_good(state) else 70
        if isinstance(action, ChooseTradePartner):
            return 40
        if isinstance(action, DiscardResources):
            return 25
        if isinstance(action, EndTurn):
            return -5
        return 0

    def _score_settlement_node(self, node_id: NodeId, state: GameState | None) -> float:
        if state is None:
            return 0
        board = state.board
        adjacent_tiles = board.node_to_adjacent_tiles.get(node_id, ())
        pip_total = 0
        resources: set[ResourceType] = set()
        weighted_total = 0.0
        for tile_id in adjacent_tiles:
            tile = self._tile_by_id(state, tile_id)
            if tile.number_token is not None:
                pip = _TOKEN_PIP_SCORES.get(tile.number_token, 0)
                pip_total += pip
                resource = _TERRAIN_TO_RESOURCE.get(tile.terrain)
                if resource is not None:
                    resources.add(resource)
                    weighted_total += pip * _RESOURCE_VALUE[resource]

        diversity_bonus = 2.5 * len(resources)
        missing_bonus = 0.0
        player = state.players.get(state.turn.current_player) if state.turn is not None else None
        if player is not None:
            produced = self._player_production_resources(state, player.player_id)
            for resource in resources:
                if produced.get(resource, 0) == 0:
                    missing_bonus += 2.0
        port_bonus = 1.5 * len(board.node_to_ports.get(node_id, ()))

        return pip_total + weighted_total + diversity_bonus + missing_bonus + port_bonus

    def _score_city_node(self, node_id: NodeId, state: GameState | None) -> float:
        if state is None:
            return 15
        return 30 + self._score_settlement_node(node_id, state)

    def _score_road(self, action: BuildRoad, state: GameState | None) -> float:
        if state is None:
            return 0
        board = state.board
        node_a, node_b = board.edge_to_adjacent_nodes[action.edge_id]
        best_adjacent = max(self._score_settlement_node(node_a, state), self._score_settlement_node(node_b, state))
        open_spot_bonus = 8 if (node_a not in state.placed.settlements and node_b not in state.placed.settlements) else 0
        return (best_adjacent * 0.2) + open_spot_bonus

    def _score_bank_trade(self, action: BankTrade, state: GameState | None) -> float:
        scarcity = 1.3 if action.request_resource in {ResourceType.ORE, ResourceType.GRAIN} else 1.0
        favorable_rate = max(0, 4 - action.trade_rate) * 4
        improvement = 0.0
        if state is not None:
            player = state.players[action.player_id]
            if player.resources.get(action.request_resource, 0) == 0:
                improvement += 10
            if player.resources.get(action.offer_resource, 0) >= action.trade_rate + 1:
                improvement += 3
        return 35 + favorable_rate + scarcity + improvement

    def _score_move_robber(self, action: MoveRobber, state: GameState | None) -> float:
        if state is None:
            return 20
        board = state.board
        tile = self._tile_by_id(state, action.tile_id)
        token_score = _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
        target_weight = 0.0
        for node_id in board.tile_to_nodes.get(action.tile_id, ()):  # type: ignore[arg-type]
            owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
            if owner is None or owner == action.player_id:
                continue
            target_weight += 8
            target_weight += state.players[owner].victory_points * 0.8
        return 20 + token_score + target_weight

    def _player_production_resources(self, state: GameState, player_id: int) -> dict[ResourceType, int]:
        board = state.board
        counts = {resource: 0 for resource in ResourceType}
        for node_id, owner in state.placed.settlements.items():
            if owner != player_id:
                continue
            for tile_id in board.node_to_adjacent_tiles.get(node_id, ()): 
                terrain = self._tile_by_id(state, tile_id).terrain
                resource = _TERRAIN_TO_RESOURCE.get(terrain)
                if resource is not None:
                    counts[resource] += 1
        for node_id, owner in state.placed.cities.items():
            if owner != player_id:
                continue
            for tile_id in board.node_to_adjacent_tiles.get(node_id, ()): 
                terrain = self._tile_by_id(state, tile_id).terrain
                resource = _TERRAIN_TO_RESOURCE.get(terrain)
                if resource is not None:
                    counts[resource] += 2
        return counts

    def _trade_response_is_good(self, state: GameState | None) -> bool:
        if state is None or state.player_trade is None or state.turn is None:
            return False
        responder_id = state.turn.priority_player
        if responder_id is None:
            return False
        responder = state.players[responder_id]
        offered = dict(state.player_trade.offered_resources)
        requested = dict(state.player_trade.requested_resources)

        give_value = 0.0
        receive_value = 0.0
        for resource, amount in offered.items():
            receive_value += _RESOURCE_VALUE[resource] * amount
        for resource, amount in requested.items():
            if responder.resources.get(resource, 0) < amount:
                return False
            scarcity_penalty = 0.5 if responder.resources.get(resource, 0) <= amount else 0.0
            give_value += (_RESOURCE_VALUE[resource] + scarcity_penalty) * amount

        return receive_value >= give_value

    def _tile_by_id(self, state: GameState, tile_id: int):
        for tile in state.board.tiles:
            if tile.id == tile_id:
                return tile
        raise KeyError(f"Unknown tile id: {tile_id}")
