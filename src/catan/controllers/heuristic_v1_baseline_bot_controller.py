from __future__ import annotations

from collections import deque
import random
import time
from typing import Any, Sequence

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
    DiscardResources,
    EndTurn,
    MoveRobber,
    PlaceSetupSettlement,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
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
    ResourceType.GRAIN: 1.2,
    ResourceType.ORE: 1.3,
}
_TERRAIN_TO_RESOURCE = {
    TerrainType.HILLS: ResourceType.BRICK,
    TerrainType.FOREST: ResourceType.LUMBER,
    TerrainType.PASTURE: ResourceType.WOOL,
    TerrainType.FIELDS: ResourceType.GRAIN,
    TerrainType.MOUNTAINS: ResourceType.ORE,
}
_SETTLEMENT_COST = {
    ResourceType.BRICK: 1,
    ResourceType.LUMBER: 1,
    ResourceType.WOOL: 1,
    ResourceType.GRAIN: 1,
}
_CITY_COST = {ResourceType.GRAIN: 2, ResourceType.ORE: 3}
_DEV_COST = {ResourceType.WOOL: 1, ResourceType.GRAIN: 1, ResourceType.ORE: 1}


class HeuristicV1BaselineBotController:
    """First-generation explainable heuristic bot with stronger baseline choices."""

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
            if not legal_actions:
                raise ValueError("HeuristicV1BaselineBotController received no legal actions.")
            fallback = legal_actions[self._rng.randrange(len(legal_actions))]
            self._record_decision(chosen_action=fallback, scored_candidates=[(fallback, -5.0)], legal_action_count=len(legal_actions))
            return fallback

        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is not None:
            discard_placeholder = next((action for action in candidates if isinstance(action, DiscardResources)), None)
            if discard_placeholder is not None:
                chosen = self._choose_discard_action(state, discard_placeholder.player_id)
                self._record_decision(chosen_action=chosen, scored_candidates=[(chosen, 25.0)], legal_action_count=len(candidates))
                return chosen

        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        scored_candidates: list[tuple[Action, float]] = []
        best_score: float | None = None
        for action in candidates:
            score = self._score_action(action, state)
            scored_candidates.append((action, score))
            if best_score is None or score > best_score:
                best_score = score

        assert best_score is not None
        near_best = [action for action, score in scored_candidates if (best_score - score) <= 0.25]
        chosen = near_best[self._rng.randrange(len(near_best))]
        self._record_decision(chosen_action=chosen, scored_candidates=scored_candidates, legal_action_count=len(candidates))
        return chosen

    def set_delay_seconds(self, delay_seconds: float) -> None:
        self._delay_seconds = max(0.0, delay_seconds)

    def get_last_decision(self) -> dict[str, Any] | None:
        return getattr(self, "_last_decision", None)

    def _record_decision(self, *, chosen_action: Action, scored_candidates: list[tuple[Action, float]], legal_action_count: int) -> None:
        ranked = sorted(scored_candidates, key=lambda item: item[1], reverse=True)
        self._last_decision = {
            "kind": "heuristic_v1_baseline",
            "chosen_action": chosen_action,
            "top_candidates": ranked[:3],
            "legal_action_count": legal_action_count,
        }

    def _score_action(self, action: Action, state: GameState | None) -> float:
        if self._is_immediate_win(action, state):
            return 50_000
        if isinstance(action, RollDice):
            return 20_000
        if isinstance(action, PlaceSetupSettlement):
            return 320 + self._score_settlement_node(action.node_id, state, in_setup=True)
        if isinstance(action, BuildSettlement):
            return 280 + self._score_settlement_node(action.node_id, state, in_setup=False)
        if isinstance(action, BuildCity):
            return 260 + self._score_city_node(action.node_id, state)
        if isinstance(action, PlayKnightCard):
            return 140 + self._score_knight_play(state)
        if isinstance(action, BuyDevelopmentCard):
            return 110 + self._evaluate_dev_purchase(state)
        if isinstance(action, BuildRoad):
            return 18 + self._score_road(action, state)
        if isinstance(action, BankTrade):
            return self._score_bank_trade(action, state)
        if isinstance(action, MoveRobber):
            return self._score_move_robber(action, state)
        if isinstance(action, RespondToTradeInterested):
            return 70 if self._trade_response_is_good(state) else -40
        if isinstance(action, RespondToTradePass):
            return 65 if not self._trade_response_is_good(state) else 15
        if isinstance(action, ChooseTradePartner):
            return self._score_trade_partner(action, state)
        if isinstance(action, PlayRoadBuildingCard):
            return 95
        if isinstance(action, PlayYearOfPlentyCard):
            return 100
        if isinstance(action, ChooseYearOfPlentyResources):
            return 105 + self._score_yop_choice(action, state)
        if isinstance(action, PlayMonopolyCard):
            return 90
        if isinstance(action, ChooseMonopolyResource):
            return 95 + self._score_monopoly_resource(action, state)
        if isinstance(action, DiscardResources):
            return 25
        if isinstance(action, EndTurn):
            return 5
        return 0

    def _is_immediate_win(self, action: Action, state: GameState | None) -> bool:
        if state is None:
            return False
        vp_gain = 0
        if isinstance(action, BuildSettlement):
            vp_gain = 1
        if isinstance(action, BuildCity):
            vp_gain = 1
        return state.players[action.player_id].victory_points + vp_gain >= 10

    def _score_settlement_node(self, node_id: NodeId, state: GameState | None, *, in_setup: bool) -> float:
        if state is None:
            return 0
        adjacent_tiles = state.board.node_to_adjacent_tiles.get(node_id, ())
        pip_total = 0
        weighted_total = 0.0
        resources: set[ResourceType] = set()
        for tile_id in adjacent_tiles:
            tile = self._tile_by_id(state, tile_id)
            if tile.number_token is None:
                continue
            pip = _TOKEN_PIP_SCORES.get(tile.number_token, 0)
            pip_total += pip
            resource = _TERRAIN_TO_RESOURCE.get(tile.terrain)
            if resource is not None:
                weighted_total += pip * _RESOURCE_VALUE[resource]
                resources.add(resource)

        diversity_bonus = 3.0 * len(resources)
        wb_bonus = 4.5 if {ResourceType.BRICK, ResourceType.LUMBER}.issubset(resources) else 0.0
        ow_bonus = 4.5 if {ResourceType.ORE, ResourceType.GRAIN}.issubset(resources) else 0.0

        player_id = state.turn.current_player if state.turn is not None else None
        missing_bonus = 0.0
        pair_bonus = 0.0
        if player_id is not None:
            produced = self._player_production_resources(state, player_id)
            for resource in resources:
                if produced.get(resource, 0) == 0:
                    missing_bonus += 2.5
            if in_setup:
                existing_setup_nodes = [
                    nid for nid, owner in state.placed.settlements.items() if owner == player_id
                ]
                if existing_setup_nodes:
                    pair_bonus += self._score_setup_pair(existing_setup_nodes[0], node_id, state)

        port_bonus = self._score_port_value(node_id, state, resources)
        expansion_bonus = self._score_future_expansion(node_id, state)
        return pip_total + weighted_total + diversity_bonus + wb_bonus + ow_bonus + missing_bonus + pair_bonus + port_bonus + expansion_bonus

    def _score_setup_pair(self, existing_node: NodeId, candidate_node: NodeId, state: GameState) -> float:
        existing_resources = self._node_resources(existing_node, state)
        candidate_resources = self._node_resources(candidate_node, state)
        combined = existing_resources | candidate_resources
        overlap_penalty = max(0, len(existing_resources) + len(candidate_resources) - len(combined)) * 1.0
        return (len(combined) * 4.0) - overlap_penalty

    def _node_resources(self, node_id: NodeId, state: GameState) -> set[ResourceType]:
        resources: set[ResourceType] = set()
        for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()):            
            terrain = self._tile_by_id(state, tile_id).terrain
            resource = _TERRAIN_TO_RESOURCE.get(terrain)
            if resource is not None:
                resources.add(resource)
        return resources

    def _score_city_node(self, node_id: NodeId, state: GameState | None) -> float:
        if state is None:
            return 20
        return 45 + self._score_settlement_node(node_id, state, in_setup=False)

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
            if self._is_open_settlement_node(state, node_id):
                endpoint_opening = max(endpoint_opening, self._score_settlement_node(node_id, state, in_setup=False) * 0.16)

        dead_road_penalty = self._dead_road_penalty(before_distances, after_distances)
        save_penalty = self._save_for_settlement_penalty(player.resources)
        longest_road_bonus = self._longest_road_bonus(state, player_id, node_a, node_b)
        return target_score + endpoint_opening + longest_road_bonus - dead_road_penalty - save_penalty

    def _roads_to_targets(self, state: GameState, player_id: int, *, planned_edges: set[int] | None = None) -> dict[NodeId, int]:
        anchors = set()
        for edge_id, owner in state.placed.roads.items():
            if owner == player_id:
                anchors.update(state.board.edge_to_adjacent_nodes[edge_id])
        for node_id, owner in state.placed.settlements.items():
            if owner == player_id:
                anchors.add(node_id)
        for node_id, owner in state.placed.cities.items():
            if owner == player_id:
                anchors.add(node_id)
        if not anchors:
            return {}

        traversable = {edge_id for edge_id, owner in state.placed.roads.items() if owner == player_id}
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
                cand = distances[node_id] + edge_cost
                if nxt not in distances or cand < distances[nxt]:
                    distances[nxt] = cand
                    if edge_cost == 0:
                        queue.appendleft(nxt)
                    else:
                        queue.append(nxt)

        targets: dict[NodeId, int] = {}
        for node_id in self._candidate_settlement_targets(state):
            if node_id in distances:
                targets[node_id] = distances[node_id]
        return targets

    def _score_road_progress(self, state: GameState, before_distances: dict[NodeId, int], after_distances: dict[NodeId, int]) -> float:
        best = 0.0
        for node_id, dist_after in after_distances.items():
            dist_before = before_distances.get(node_id, 99)
            if dist_after > dist_before:
                continue
            quality = self._score_settlement_node(node_id, state, in_setup=False)
            improvement = dist_before - dist_after
            best = max(best, (quality * 0.13) - (dist_after * 3.0) + (improvement * 14.0))
        return best

    def _dead_road_penalty(self, before_distances: dict[NodeId, int], after_distances: dict[NodeId, int]) -> float:
        if not after_distances:
            return 24.0
        improved = any(dist_after < before_distances.get(node_id, 99) for node_id, dist_after in after_distances.items())
        return 0.0 if improved else 16.0

    def _save_for_settlement_penalty(self, resources: dict[ResourceType, int]) -> float:
        missing_before = self._missing_resources(resources, _SETTLEMENT_COST)
        post_road = dict(resources)
        post_road[ResourceType.BRICK] = max(0, post_road.get(ResourceType.BRICK, 0) - 1)
        post_road[ResourceType.LUMBER] = max(0, post_road.get(ResourceType.LUMBER, 0) - 1)
        missing_after = self._missing_resources(post_road, _SETTLEMENT_COST)
        if missing_before <= 1:
            return 20.0 + max(0, missing_after - missing_before) * 8.0
        if missing_before == 2:
            return 6.0
        return 0.0

    def _longest_road_bonus(self, state: GameState, player_id: int, node_a: NodeId, node_b: NodeId) -> float:
        if state.longest_road_holder not in (None, player_id):
            return 0.0
        connected = 0
        for edge_id in state.board.node_to_adjacent_edges.get(node_a, ()):
            if state.placed.roads.get(edge_id) == player_id:
                connected += 1
        for edge_id in state.board.node_to_adjacent_edges.get(node_b, ()):
            if state.placed.roads.get(edge_id) == player_id:
                connected += 1
        return min(6.0, connected * 1.5)

    def _score_bank_trade(self, action: BankTrade, state: GameState | None) -> float:
        favorable_rate = max(0, 4 - action.trade_rate) * 4
        scarcity = 1.3 if action.request_resource in {ResourceType.ORE, ResourceType.GRAIN} else 1.0
        if state is None:
            return 20 + favorable_rate + scarcity

        player = state.players[action.player_id]
        resources_after = dict(player.resources)
        resources_after[action.offer_resource] = max(0, resources_after.get(action.offer_resource, 0) - action.trade_rate)
        resources_after[action.request_resource] = resources_after.get(action.request_resource, 0) + 1

        enable_bonus = 0.0
        if self._can_afford(resources_after, _SETTLEMENT_COST):
            enable_bonus = 34.0
        elif self._can_afford(resources_after, _CITY_COST):
            enable_bonus = 32.0
        elif self._can_afford(resources_after, _DEV_COST):
            enable_bonus = 18.0

        if enable_bonus == 0.0:
            return -6.0 + favorable_rate + scarcity
        return 26.0 + favorable_rate + scarcity + enable_bonus

    def _score_move_robber(self, action: MoveRobber, state: GameState | None) -> float:
        if state is None:
            return 20
        tile = self._tile_by_id(state, action.tile_id)
        token_score = _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
        self_harm = 0.0
        target_weight = 0.0
        for node_id in state.board.tile_to_nodes.get(action.tile_id, ()):            
            owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
            if owner is None:
                continue
            if owner == action.player_id:
                self_harm += 18.0
                continue
            target_weight += 8.0 + state.players[owner].victory_points * 1.2
        return 30 + token_score + target_weight - self_harm

    def _score_knight_play(self, state: GameState | None) -> float:
        if state is None or state.turn is None:
            return 0.0
        player_id = state.turn.current_player
        if state.largest_army_holder in (None, player_id):
            return 8.0
        return 14.0

    def _evaluate_dev_purchase(self, state: GameState | None) -> float:
        if state is None or state.turn is None:
            return 0.0
        produced = self._player_production_resources(state, state.turn.current_player)
        ore_wheat = produced.get(ResourceType.ORE, 0) + produced.get(ResourceType.GRAIN, 0)
        return min(18.0, ore_wheat * 2.0)

    def _score_trade_partner(self, action: ChooseTradePartner, state: GameState | None) -> float:
        if state is None:
            return 35
        vp = state.players[action.partner_player_id].victory_points
        return 40 - vp * 1.2

    def _score_yop_choice(self, action: ChooseYearOfPlentyResources, state: GameState | None) -> float:
        if state is None or state.turn is None:
            return 0.0
        player = state.players[state.turn.current_player]
        resources = dict(player.resources)
        resources[action.first_resource] = resources.get(action.first_resource, 0) + 1
        resources[action.second_resource] = resources.get(action.second_resource, 0) + 1
        if self._can_afford(resources, _CITY_COST):
            return 14.0
        if self._can_afford(resources, _SETTLEMENT_COST):
            return 12.0
        return 4.0

    def _score_monopoly_resource(self, action: ChooseMonopolyResource, state: GameState | None) -> float:
        if state is None:
            return 0.0
        total = 0
        for player_id, player in state.players.items():
            if state.turn is not None and player_id == state.turn.current_player:
                continue
            total += player.resources.get(action.resource, 0)
        return total * 2.0

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
                total += 2.6
            else:
                total += 0.5
        return total

    def _score_future_expansion(self, node_id: NodeId, state: GameState) -> float:
        open_neighbors = 0
        for neighbor in state.board.node_neighbors(node_id):
            if self._is_open_settlement_node(state, neighbor):
                open_neighbors += 1
        return 1.6 * open_neighbors

    def _is_open_settlement_node(self, state: GameState, node_id: NodeId) -> bool:
        if node_id in state.placed.settlements or node_id in state.placed.cities:
            return False
        return all(neighbor not in state.placed.settlements and neighbor not in state.placed.cities for neighbor in state.board.node_neighbors(node_id))

    def _candidate_settlement_targets(self, state: GameState) -> list[NodeId]:
        return [node_id for node_id in state.board.nodes if self._is_open_settlement_node(state, node_id)]

    def _player_production_resources(self, state: GameState, player_id: int) -> dict[ResourceType, int]:
        counts = {resource: 0 for resource in ResourceType}
        for node_id, owner in state.placed.settlements.items():
            if owner != player_id:
                continue
            for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()):
                resource = _TERRAIN_TO_RESOURCE.get(self._tile_by_id(state, tile_id).terrain)
                if resource is not None:
                    counts[resource] += 1
        for node_id, owner in state.placed.cities.items():
            if owner != player_id:
                continue
            for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()):
                resource = _TERRAIN_TO_RESOURCE.get(self._tile_by_id(state, tile_id).terrain)
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
            scarcity_penalty = 0.6 if responder.resources.get(resource, 0) <= amount else 0.0
            give_value += (_RESOURCE_VALUE[resource] + scarcity_penalty) * amount
        return receive_value >= give_value

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
        return DiscardResources(player_id=player_id, resources=tuple((resource, amount) for resource, amount in discards.items() if amount > 0))

    def _missing_resources(self, resources: dict[ResourceType, int], cost: dict[ResourceType, int]) -> int:
        return sum(max(0, amount - resources.get(resource, 0)) for resource, amount in cost.items())

    def _can_afford(self, resources: dict[ResourceType, int], cost: dict[ResourceType, int]) -> bool:
        return self._missing_resources(resources, cost) == 0

    def _tile_by_id(self, state: GameState, tile_id: int):
        for tile in state.board.tiles:
            if tile.id == tile_id:
                return tile
        raise KeyError(f"Unknown tile id: {tile_id}")
