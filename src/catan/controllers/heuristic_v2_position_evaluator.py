from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from catan.controllers.heuristic_v1_baseline_bot_controller import _TOKEN_PIP_SCORES, _TERRAIN_TO_RESOURCE
from catan.controllers.heuristic_params import HeuristicScoringParams
from catan.core.models.enums import ResourceType, TerrainType
from catan.core.models.state import GameState


@dataclass(frozen=True)
class PositionEvaluation:
    total_score: float
    components: dict[str, float]
    timings: dict[str, float]


class HeuristicV2PositionEvaluator:
    def evaluate(self, state: GameState, player_id: int, params: HeuristicScoringParams) -> PositionEvaluation:
        timings: dict[str, float] = {}
        t0 = perf_counter()
        player = state.players[player_id]
        total_vp = player.victory_points
        if state.longest_road_holder == player_id:
            total_vp += 2
        if state.largest_army_holder == player_id:
            total_vp += 2
        timings["vp"] = perf_counter() - t0

        t0 = perf_counter()
        production_by_resource: dict[ResourceType, float] = {resource: 0.0 for resource in ResourceType}
        city_targets = 0.0
        blocked_pips = 0.0
        for node_id, owner in state.placed.settlements.items():
            if owner != player_id:
                continue
            for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()): 
                tile = self._tile_by_id(state, tile_id)
                resource = _TERRAIN_TO_RESOURCE.get(tile.terrain)
                if resource is None:
                    continue
                pip = _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
                if state.robber_tile_id == tile_id:
                    blocked_pips += pip
                    continue
                production_by_resource[resource] += pip
                city_targets += pip * 0.5

        for node_id, owner in state.placed.cities.items():
            if owner != player_id:
                continue
            for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()): 
                tile = self._tile_by_id(state, tile_id)
                resource = _TERRAIN_TO_RESOURCE.get(tile.terrain)
                if resource is None:
                    continue
                pip = _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
                if state.robber_tile_id == tile_id:
                    blocked_pips += pip * 2
                    continue
                production_by_resource[resource] += pip * 2
        timings["production"] = perf_counter() - t0

        t0 = perf_counter()
        production_score = sum(production_by_resource.values())

        expansion_profile = {ResourceType.LUMBER, ResourceType.BRICK, ResourceType.GRAIN, ResourceType.WOOL}
        city_dev_profile = {ResourceType.ORE, ResourceType.GRAIN, ResourceType.WOOL}
        resource_balance_score = (
            self._profile_score(production_by_resource, expansion_profile)
            + self._profile_score(production_by_resource, city_dev_profile)
            + len({resource for resource, amount in production_by_resource.items() if amount > 0})
        )
        timings["resource_balance"] = perf_counter() - t0

        t0 = perf_counter()
        expansion_potential = self._expansion_potential(state, player_id)
        timings["expansion"] = perf_counter() - t0

        t0 = perf_counter()
        road_potential = float(player.longest_road_length)
        if state.longest_road_holder == player_id:
            road_potential += 2.0
        elif state.longest_road_holder is None:
            road_potential += min(2.0, player.longest_road_length / 2.0)
        timings["road_potential"] = perf_counter() - t0

        t0 = perf_counter()
        dev_potential = (
            production_by_resource[ResourceType.ORE]
            + production_by_resource[ResourceType.GRAIN]
            + production_by_resource[ResourceType.WOOL]
            + (player.knights_played * 1.5)
            + sum(player.dev_cards.values())
        )
        timings["dev_potential"] = perf_counter() - t0

        t0 = perf_counter()
        port_value = self._port_value(state, player_id, production_by_resource)
        timings["port_value"] = perf_counter() - t0

        t0 = perf_counter()
        hand_total = sum(player.resources.values())
        hand_resource_score = hand_total + self._close_to_cost_bonus(player.resources)
        timings["hand_resources"] = perf_counter() - t0

        t0 = perf_counter()
        road_count = sum(1 for owner in state.placed.roads.values() if owner == player_id)
        settlement_like_count = sum(1 for owner in state.placed.settlements.values() if owner == player_id) + sum(
            1 for owner in state.placed.cities.values() if owner == player_id
        )
        road_overbuild = max(0.0, road_count - (settlement_like_count * 3))
        timings["penalties"] = perf_counter() - t0

        components = {
            "vp": total_vp * params.vp_weight,
            "production": production_score * params.production_weight,
            "resource_balance": resource_balance_score * params.resource_balance_weight,
            "expansion": expansion_potential * params.expansion_potential_weight,
            "city_potential": city_targets * params.city_potential_weight,
            "dev_potential": dev_potential * params.dev_potential_weight,
            "road_potential": road_potential * params.road_potential_weight,
            "port_value": port_value * params.port_value_weight,
            "hand_resources": hand_resource_score * params.hand_resource_weight,
            "robber_block_penalty": -(blocked_pips * params.robber_block_penalty),
            "large_hand_penalty": -(max(0, hand_total - 7) * params.large_hand_penalty),
            "road_overbuild_penalty": -(road_overbuild * params.road_overbuild_penalty),
            "no_expansion_penalty": -(
                params.no_expansion_penalty
                if expansion_potential <= 0.01
                else 0.0
            ),
        }
        return PositionEvaluation(total_score=sum(components.values()), components=components, timings=timings)

    def _profile_score(self, production: dict[ResourceType, float], profile: set[ResourceType]) -> float:
        present = sum(1 for resource in profile if production.get(resource, 0.0) > 0)
        return present + (sum(production.get(resource, 0.0) for resource in profile) * 0.08)

    def _expansion_potential(self, state: GameState, player_id: int) -> float:
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
            return 0.0

        open_nodes: list[tuple[int, float]] = []
        for node_id in state.board.nodes:
            if not self._is_open_node(state, node_id):
                continue
            distance = self._distance_from_anchors(state, anchors, node_id, player_id)
            if distance is None:
                continue
            quality = self._node_quality(state, node_id)
            open_nodes.append((distance, quality))

        if not open_nodes:
            return 0.0
        open_nodes.sort(key=lambda item: item[0] - (item[1] * 0.02))
        best = open_nodes[0][1] - open_nodes[0][0] * 2.0
        second = 0.0
        if len(open_nodes) > 1:
            second = open_nodes[1][1] - open_nodes[1][0] * 1.2
        return max(0.0, best + (second * 0.55))

    def _port_value(self, state: GameState, player_id: int, production: dict[ResourceType, float]) -> float:
        value = 0.0
        for node_id, owner in state.placed.settlements.items():
            if owner != player_id:
                continue
            value += self._node_port_value(state, node_id, production)
        for node_id, owner in state.placed.cities.items():
            if owner != player_id:
                continue
            value += self._node_port_value(state, node_id, production) * 1.25
        return value

    def _node_port_value(self, state: GameState, node_id: int, production: dict[ResourceType, float]) -> float:
        ports = state.board.node_to_ports.get(node_id, ())
        if not ports:
            return 0.0
        total = 0.0
        for port_id in ports:
            port = state.board.ports[port_id]
            if port.trade_resource is None:
                total += 1.5
                continue
            produced = production.get(port.trade_resource, 0.0)
            total += 0.25 if produced <= 0 else min(3.5, 0.4 + produced * 0.15)
        return total

    def _close_to_cost_bonus(self, resources: dict[ResourceType, int]) -> float:
        settlement_need = max(0, 1 - resources.get(ResourceType.BRICK, 0)) + max(0, 1 - resources.get(ResourceType.LUMBER, 0))
        settlement_need += max(0, 1 - resources.get(ResourceType.WOOL, 0)) + max(0, 1 - resources.get(ResourceType.GRAIN, 0))
        city_need = max(0, 2 - resources.get(ResourceType.GRAIN, 0)) + max(0, 3 - resources.get(ResourceType.ORE, 0))
        dev_need = max(0, 1 - resources.get(ResourceType.WOOL, 0)) + max(0, 1 - resources.get(ResourceType.GRAIN, 0))
        dev_need += max(0, 1 - resources.get(ResourceType.ORE, 0))
        return max(0.0, 5.0 - settlement_need) + max(0.0, 4.0 - city_need * 0.8) + max(0.0, 3.0 - dev_need * 0.7)

    def _distance_from_anchors(self, state: GameState, anchors: set[int], target_node: int, player_id: int) -> int | None:
        frontier = [(anchor, 0) for anchor in anchors]
        seen = set(anchors)
        idx = 0
        while idx < len(frontier):
            node_id, distance = frontier[idx]
            idx += 1
            if node_id == target_node:
                return distance
            for edge_id in state.board.node_to_adjacent_edges.get(node_id, ()): 
                a, b = state.board.edge_to_adjacent_nodes[edge_id]
                nxt = b if a == node_id else a
                if nxt in seen:
                    continue
                seen.add(nxt)
                edge_owner = state.placed.roads.get(edge_id)
                if edge_owner is None:
                    edge_cost = 1
                elif edge_owner == player_id:
                    edge_cost = 0
                else:
                    continue
                frontier.append((nxt, distance + edge_cost))
        return None

    def _node_quality(self, state: GameState, node_id: int) -> float:
        quality = 0.0
        for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()): 
            tile = self._tile_by_id(state, tile_id)
            if tile.terrain == TerrainType.DESERT:
                continue
            quality += _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
        return quality

    def _is_open_node(self, state: GameState, node_id: int) -> bool:
        if node_id in state.placed.settlements or node_id in state.placed.cities:
            return False
        return all(neighbor not in state.placed.settlements and neighbor not in state.placed.cities for neighbor in state.board.node_neighbors(node_id))

    def _tile_by_id(self, state: GameState, tile_id: int):
        for tile in state.board.tiles:
            if tile.id == tile_id:
                return tile
        raise KeyError(f"Unknown tile id: {tile_id}")
