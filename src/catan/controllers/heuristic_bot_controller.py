from __future__ import annotations

from collections import deque
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

        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is not None:
            discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
            if discard_placeholder is not None:
                return self._choose_discard_action(state, discard_placeholder.player_id)

        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

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

    def set_delay_seconds(self, delay_seconds: float) -> None:
        self._delay_seconds = max(0.0, delay_seconds)

    def _choose_discard_action(self, state: GameState, player_id: int) -> DiscardResources:
        required = state.discard_requirements.get(player_id, 0)
        hand = dict(state.players[player_id].resources)
        prioritized = sorted(
            (resource for resource in ResourceType if hand.get(resource, 0) > 0),
            key=lambda resource: (_RESOURCE_VALUE[resource], -hand[resource]),
        )
        discards: dict[ResourceType, int] = {resource: 0 for resource in ResourceType}
        remaining = required
        while remaining > 0:
            for resource in prioritized:
                if hand[resource] <= 0:
                    continue
                hand[resource] -= 1
                discards[resource] += 1
                remaining -= 1
                break
        return DiscardResources(
            player_id=player_id,
            resources=tuple((resource, amount) for resource, amount in discards.items() if amount > 0),
        )

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
            return 20 + self._score_road(action, state)
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
            return 0
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
        port_bonus = self._score_port_value(node_id, state, resources)
        expansion_bonus = self._score_future_expansion(node_id, state)

        return pip_total + weighted_total + diversity_bonus + missing_bonus + port_bonus + expansion_bonus

    def _score_city_node(self, node_id: NodeId, state: GameState | None) -> float:
        if state is None:
            return 15
        return 30 + self._score_settlement_node(node_id, state)

    def _score_road(self, action: BuildRoad, state: GameState | None) -> float:
        if state is None:
            return 0
        board = state.board
        player_id = action.player_id
        player = state.players[player_id]
        node_a, node_b = board.edge_to_adjacent_nodes[action.edge_id]
        before_distances = self._roads_to_targets(state, player_id)
        after_distances = self._roads_to_targets(state, player_id, planned_edges={action.edge_id})
        target_score = self._score_road_progress(state, before_distances, after_distances)

        endpoint_opening = 0.0
        for node_id in (node_a, node_b):
            if node_id in state.placed.settlements or node_id in state.placed.cities:
                continue
            if self._is_open_settlement_node(state, node_id):
                endpoint_opening = max(endpoint_opening, self._score_settlement_node(node_id, state) * 0.15)

        dead_road_penalty = self._dead_road_penalty(before_distances, after_distances)
        save_penalty = self._save_for_settlement_penalty(player.resources)
        longest_road_bonus = self._longest_road_bonus(state, player_id, node_a, node_b)

        return target_score + endpoint_opening + longest_road_bonus - dead_road_penalty - save_penalty

    def _score_port_value(self, node_id: NodeId, state: GameState, produced_here: set[ResourceType]) -> float:
        ports = state.board.node_to_ports.get(node_id, ())
        if not ports:
            return 0.0
        player = state.players[state.turn.current_player] if state.turn is not None else None
        if player is None:
            return 1.5 * len(ports)
        produced = self._player_production_resources(state, player.player_id)
        total = 0.0
        for port_id in ports:
            port = state.board.ports[port_id]
            if port.trade_resource is None:
                total += 1.5
                continue
            if produced.get(port.trade_resource, 0) > 0 or port.trade_resource in produced_here:
                total += 2.5
            else:
                total += 0.5
        return total

    def _score_future_expansion(self, node_id: NodeId, state: GameState) -> float:
        open_neighbors = 0
        for neighbor in state.board.node_neighbors(node_id):
            if self._is_open_settlement_node(state, neighbor):
                open_neighbors += 1
        return 1.5 * open_neighbors

    def _is_open_settlement_node(self, state: GameState, node_id: NodeId) -> bool:
        if node_id in state.placed.settlements or node_id in state.placed.cities:
            return False
        for neighbor in state.board.node_neighbors(node_id):
            if neighbor in state.placed.settlements or neighbor in state.placed.cities:
                return False
        return True

    def _candidate_settlement_targets(self, state: GameState) -> list[NodeId]:
        return [node_id for node_id in state.board.nodes if self._is_open_settlement_node(state, node_id)]

    def _roads_to_targets(
        self,
        state: GameState,
        player_id: int,
        *,
        planned_edges: set[int] | None = None,
    ) -> dict[NodeId, int]:
        anchors = set()
        for edge_id, owner in state.placed.roads.items():
            if owner != player_id:
                continue
            a, b = state.board.edge_to_adjacent_nodes[edge_id]
            anchors.update((a, b))
        for node_id, owner in state.placed.settlements.items():
            if owner == player_id:
                anchors.add(node_id)
        for node_id, owner in state.placed.cities.items():
            if owner == player_id:
                anchors.add(node_id)
        if not anchors:
            return {}

        traversable = set(edge_id for edge_id, owner in state.placed.roads.items() if owner == player_id)
        traversable.update(edge_id for edge_id in state.board.edge_to_adjacent_nodes if edge_id not in state.placed.roads)
        if planned_edges:
            traversable.update(planned_edges)

        distances = {node_id: 0 for node_id in anchors}
        queue: deque[NodeId] = deque(anchors)
        while queue:
            node_id = queue.popleft()
            for edge_id in state.board.node_to_adjacent_edges.get(node_id, ()):
                if edge_id not in traversable:
                    continue
                a, b = state.board.edge_to_adjacent_nodes[edge_id]
                nxt = b if a == node_id else a
                edge_cost = 0 if state.placed.roads.get(edge_id) == player_id else 1
                candidate = distances[node_id] + edge_cost
                if nxt not in distances or candidate < distances[nxt]:
                    distances[nxt] = candidate
                    if edge_cost == 0:
                        queue.appendleft(nxt)
                    else:
                        queue.append(nxt)

        target_distances: dict[NodeId, int] = {}
        for node_id in self._candidate_settlement_targets(state):
            if node_id in distances:
                target_distances[node_id] = distances[node_id]
        return target_distances

    def _score_road_progress(
        self,
        state: GameState,
        before_distances: dict[NodeId, int],
        after_distances: dict[NodeId, int],
    ) -> float:
        progress_score = 0.0
        for node_id, dist_after in after_distances.items():
            dist_before = before_distances.get(node_id, 99)
            if dist_after > dist_before:
                continue
            node_quality = self._score_settlement_node(node_id, state)
            improvement = dist_before - dist_after
            progress_score = max(progress_score, (node_quality * 0.12) - (dist_after * 3.0) + (improvement * 14.0))
        return progress_score

    def _dead_road_penalty(self, before_distances: dict[NodeId, int], after_distances: dict[NodeId, int]) -> float:
        if not after_distances:
            return 22.0
        improved = False
        for node_id, dist_after in after_distances.items():
            if dist_after < before_distances.get(node_id, 99):
                improved = True
                break
        return 0.0 if improved else 14.0

    def _save_for_settlement_penalty(self, resources: dict[ResourceType, int]) -> float:
        cost = {
            ResourceType.BRICK: 1,
            ResourceType.LUMBER: 1,
            ResourceType.WOOL: 1,
            ResourceType.GRAIN: 1,
        }
        missing_before = 0
        missing_after = 0
        for resource, amount in cost.items():
            have = resources.get(resource, 0)
            have_after = have - 1 if resource in {ResourceType.BRICK, ResourceType.LUMBER} else have
            missing_before += max(0, amount - have)
            missing_after += max(0, amount - have_after)
        if missing_before <= 1:
            return 18.0 + (missing_after - missing_before) * 8.0
        if missing_before == 2:
            return 5.0
        return 0.0

    def _longest_road_bonus(self, state: GameState, player_id: int, node_a: NodeId, node_b: NodeId) -> float:
        if state.longest_road_holder not in (None, player_id):
            return 0.0
        connected_edges = 0
        for edge_id in state.board.node_to_adjacent_edges.get(node_a, ()):
            if state.placed.roads.get(edge_id) == player_id:
                connected_edges += 1
        for edge_id in state.board.node_to_adjacent_edges.get(node_b, ()):
            if state.placed.roads.get(edge_id) == player_id:
                connected_edges += 1
        return min(6.0, connected_edges * 1.5)

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
