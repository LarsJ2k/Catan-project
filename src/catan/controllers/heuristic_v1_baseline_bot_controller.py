from __future__ import annotations

from collections import deque
import random
import time
from typing import Any, Sequence

from catan.controllers.heuristic_params import HeuristicScoringParams
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
from catan.core.models.enums import ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation

DEFAULT_BOT_ACTION_DELAY_SECONDS = 1.2
_TOKEN_PIP_SCORES = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
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
        heuristic_params: HeuristicScoringParams | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._delay_seconds = delay_seconds
        self._enable_delay = enable_delay
        self._params = heuristic_params or HeuristicScoringParams(
            grain_value=1.2,
            ore_value=1.3,
            immediate_win_score=50_000.0,
            roll_score=20_000.0,
            settlement_base_score=280.0,
            city_base_score=260.0,
            road_base_score=18.0,
            dev_buy_base_score=110.0,
            bank_trade_base_score=26.0,
            end_turn_base_score=5.0,
            diversity_weight=3.0,
            missing_resource_weight=2.5,
            expansion_weight=1.6,
            wood_brick_bonus=4.5,
            ore_wheat_bonus=4.5,
            pair_synergy_weight=4.0,
            road_to_target_weight=0.13,
            dead_road_penalty=16.0,
            dead_road_no_targets_penalty=24.0,
            save_for_settlement_penalty=20.0,
            save_for_settlement_mid_penalty=6.0,
            port_reach_weight=0.16,
            robber_leader_weight=1.2,
            trade_scarcity_penalty=0.6,
            dev_buy_weight=2.0,
            knight_play_weight=8.0,
            bank_trade_direct_build_bonus=34.0,
        )
        self._resource_values = self._params.resource_values()
        self._score_notes: dict[int, str] = {}
        self._bank_trades_this_turn = 0
        self._player_trade_proposals_this_turn = 0
        self._last_turn_player_id: int | None = None

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        candidates = list(legal_actions)
        if not candidates:
            if not legal_actions:
                raise ValueError("HeuristicV1BaselineBotController received no legal actions.")
            fallback = legal_actions[self._rng.randrange(len(legal_actions))]
            self._record_decision(chosen_action=fallback, scored_candidates=[(fallback, -5.0)], legal_action_count=len(legal_actions))
            return fallback

        state = observation.state if isinstance(observation, DebugObservation) else None
        self._prepare_turn_context(state)
        self._score_notes = {}
        if state is not None:
            candidates.extend(self._candidate_player_trades(state, legal_actions))
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
        if isinstance(chosen, BankTrade):
            self._bank_trades_this_turn += 1
        if isinstance(chosen, ProposePlayerTrade):
            self._player_trade_proposals_this_turn += 1
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
        notes = [{"action": action, "note": self._score_notes[id(action)]} for action, _ in ranked[:3] if id(action) in self._score_notes]
        if notes:
            self._last_decision["candidate_notes"] = notes

    def _score_action(self, action: Action, state: GameState | None) -> float:
        if self._is_immediate_win(action, state):
            return self._params.immediate_win_score
        if isinstance(action, RollDice):
            return self._params.roll_score
        if isinstance(action, PlaceSetupSettlement):
            return 320 + self._score_settlement_node(action.node_id, state, in_setup=True)
        if isinstance(action, BuildSettlement):
            return self._params.settlement_base_score + self._score_settlement_node(action.node_id, state, in_setup=False)
        if isinstance(action, BuildCity):
            return self._params.city_base_score + self._score_city_node(action.node_id, state)
        if isinstance(action, PlayKnightCard):
            return 140 + self._score_knight_play(state)
        if isinstance(action, BuyDevelopmentCard):
            return self._params.dev_buy_base_score + self._evaluate_dev_purchase(state)
        if isinstance(action, BuildRoad):
            return self._params.road_base_score + self._score_road(action, state)
        if isinstance(action, BankTrade):
            return self._score_bank_trade(action, state)
        if isinstance(action, ProposePlayerTrade):
            return self._score_player_trade_proposal(action, state)
        if isinstance(action, MoveRobber):
            return self._score_move_robber(action, state)
        if isinstance(action, RespondToTradeInterested):
            good, reason = self._trade_response_evaluation(state)
            self._score_notes[id(action)] = reason
            return 70 if good else -40
        if isinstance(action, RespondToTradePass):
            good, reason = self._trade_response_evaluation(state)
            self._score_notes[id(action)] = "pass: " + reason
            return 65 if not good else 15
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
            return self._params.end_turn_base_score
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
                weighted_total += pip * self._resource_values[resource]
                resources.add(resource)

        diversity_bonus = self._params.diversity_weight * len(resources)
        wb_bonus = self._params.wood_brick_bonus if {ResourceType.BRICK, ResourceType.LUMBER}.issubset(resources) else 0.0
        ow_bonus = self._params.ore_wheat_bonus if {ResourceType.ORE, ResourceType.GRAIN}.issubset(resources) else 0.0

        player_id = state.turn.current_player if state.turn is not None else None
        missing_bonus = 0.0
        pair_bonus = 0.0
        if player_id is not None:
            produced = self._player_production_resources(state, player_id)
            for resource in resources:
                if produced.get(resource, 0) == 0:
                    missing_bonus += self._params.missing_resource_weight
            if in_setup:
                existing_setup_nodes = [
                    nid for nid, owner in state.placed.settlements.items() if owner == player_id
                ]
                if existing_setup_nodes:
                    pair_bonus += self._score_setup_pair(existing_setup_nodes[0], node_id, state) * self._params.pair_synergy_weight

        port_bonus = self._score_port_value(node_id, state, resources) * self._params.port_weight
        expansion_bonus = self._score_future_expansion(node_id, state)
        return (pip_total * self._params.pip_weight) + weighted_total + diversity_bonus + wb_bonus + ow_bonus + missing_bonus + pair_bonus + port_bonus + expansion_bonus

    def _score_setup_pair(self, existing_node: NodeId, candidate_node: NodeId, state: GameState) -> float:
        existing_resources = self._node_resources(existing_node, state)
        candidate_resources = self._node_resources(candidate_node, state)
        combined = existing_resources | candidate_resources
        overlap_penalty = max(0, len(existing_resources) + len(candidate_resources) - len(combined)) * 1.0
        return (len(combined) * 1.0) - overlap_penalty

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
                endpoint_opening = max(endpoint_opening, self._score_settlement_node(node_id, state, in_setup=False) * self._params.port_reach_weight)

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
            best = max(
                best,
                (quality * self._params.road_to_target_weight)
                - (dist_after * self._params.road_distance_penalty)
                + (improvement * self._params.road_improvement_weight),
            )
        return best

    def _dead_road_penalty(self, before_distances: dict[NodeId, int], after_distances: dict[NodeId, int]) -> float:
        if not after_distances:
            return self._params.dead_road_no_targets_penalty
        improved = any(dist_after < before_distances.get(node_id, 99) for node_id, dist_after in after_distances.items())
        return 0.0 if improved else self._params.dead_road_penalty

    def _save_for_settlement_penalty(self, resources: dict[ResourceType, int]) -> float:
        missing_before = self._missing_resources(resources, _SETTLEMENT_COST)
        post_road = dict(resources)
        post_road[ResourceType.BRICK] = max(0, post_road.get(ResourceType.BRICK, 0) - 1)
        post_road[ResourceType.LUMBER] = max(0, post_road.get(ResourceType.LUMBER, 0) - 1)
        missing_after = self._missing_resources(post_road, _SETTLEMENT_COST)
        if missing_before <= 1:
            return self._params.save_for_settlement_penalty + max(0, missing_after - missing_before) * self._params.save_for_settlement_delta_penalty
        if missing_before == 2:
            return self._params.save_for_settlement_mid_penalty
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
        return min(6.0, connected * self._params.longest_road_weight)

    def _score_bank_trade(self, action: BankTrade, state: GameState | None) -> float:
        favorable_rate = max(0, 4 - action.trade_rate) * 4
        scarcity = 1.3 if action.request_resource in {ResourceType.ORE, ResourceType.GRAIN} else 1.0
        if state is None:
            return 20 + favorable_rate + scarcity

        player = state.players[action.player_id]
        resources_after = dict(player.resources)
        resources_after[action.offer_resource] = max(0, resources_after.get(action.offer_resource, 0) - action.trade_rate)
        resources_after[action.request_resource] = resources_after.get(action.request_resource, 0) + 1

        resources_before = dict(player.resources)
        enables_city = self._can_afford(resources_after, _CITY_COST)
        enables_settlement = self._can_afford(resources_after, _SETTLEMENT_COST)
        enables_dev = self._can_afford(resources_after, _DEV_COST)
        road_enabled = resources_after.get(ResourceType.BRICK, 0) >= 1 and resources_after.get(ResourceType.LUMBER, 0) >= 1
        road_progress = self._best_road_progress_gain(state, action.player_id)
        road_ok = road_enabled and (
            (not self._params.bank_trade_enable_road_requires_target) or road_progress >= self._params.bank_trade_progress_threshold
        )

        missing_before = (
            self._missing_resources(resources_before, _CITY_COST),
            self._missing_resources(resources_before, _SETTLEMENT_COST),
            self._missing_resources(resources_before, _DEV_COST),
        )
        missing_after = (
            self._missing_resources(resources_after, _CITY_COST),
            self._missing_resources(resources_after, _SETTLEMENT_COST),
            self._missing_resources(resources_after, _DEV_COST),
        )
        plan_progress = min(missing_after) < min(missing_before) and missing_after[0] <= missing_before[0]

        bonus = 0.0
        reasons: list[str] = []
        if enables_city:
            bonus += self._params.bank_trade_enable_city_bonus
            reasons.append("enables City")
        if enables_settlement:
            bonus += self._params.bank_trade_enable_settlement_bonus
            reasons.append("enables Settlement")
        if enables_dev:
            bonus += self._params.bank_trade_enable_dev_bonus
            reasons.append("enables Dev")
        if road_ok:
            bonus += self._params.bank_trade_direct_build_bonus
            reasons.append("enables Road target")
        if plan_progress and not reasons:
            bonus += self._params.bank_trade_progress_threshold * 3.0
            reasons.append("near-term plan improved")

        chain_penalty = 0.0
        if self._bank_trades_this_turn > 0 and not (enables_city or enables_settlement or enables_dev or road_ok):
            chain_penalty = self._params.bank_trade_chain_penalty
            reasons.append("chain penalty")
        if bonus <= 0:
            self._score_notes[id(action)] = "rejected: no progress" + ("; chain penalty" if chain_penalty else "")
            return self._params.bank_trade_no_progress_penalty + favorable_rate + scarcity + chain_penalty
        self._score_notes[id(action)] = "; ".join(reasons)
        return self._params.bank_trade_base_score + favorable_rate + scarcity + bonus + chain_penalty

    def _best_road_progress_gain(self, state: GameState, player_id: int) -> float:
        anchors = {node_id for node_id, owner in state.placed.settlements.items() if owner == player_id}
        anchors.update(node_id for node_id, owner in state.placed.cities.items() if owner == player_id)
        for edge_id, owner in state.placed.roads.items():
            if owner != player_id:
                continue
            a, b = state.board.edge_to_adjacent_nodes[edge_id]
            anchors.add(a)
            anchors.add(b)
        candidate_edges = [edge.id for edge in state.board.edges if edge.id not in state.placed.roads and (edge.node_a in anchors or edge.node_b in anchors)]
        before = self._roads_to_targets(state, player_id)
        best = 0.0
        for edge_id in candidate_edges[:8]:
            after = self._roads_to_targets(state, player_id, planned_edges={edge_id})
            best = max(best, self._score_road_progress(state, before, after))
        return best

    def _prepare_turn_context(self, state: GameState | None) -> None:
        if state is None or state.turn is None:
            self._bank_trades_this_turn = 0
            self._player_trade_proposals_this_turn = 0
            self._last_turn_player_id = None
            return
        if state.turn.step != TurnStep.ACTIONS:
            self._bank_trades_this_turn = 0
        if self._last_turn_player_id != state.turn.current_player:
            self._bank_trades_this_turn = 0
            self._player_trade_proposals_this_turn = 0
            self._last_turn_player_id = state.turn.current_player

    def _candidate_player_trades(self, state: GameState, legal_actions: Sequence[Action]) -> list[ProposePlayerTrade]:
        if state.turn is None or state.turn.step != TurnStep.ACTIONS or state.player_trade is not None:
            return []
        current_player = state.turn.current_player
        if not any(action.player_id == current_player for action in legal_actions):
            return []
        if self._player_trade_proposals_this_turn >= max(0, int(self._params.max_bot_trade_proposals_per_turn)):
            return []
        player = state.players[current_player]
        opponents = [p for p in state.players.values() if p.player_id != current_player]
        proposals: list[ProposePlayerTrade] = []
        for request in ResourceType:
            if not any(op.resources.get(request, 0) >= 1 for op in opponents):
                continue
            for offer in ResourceType:
                if offer == request:
                    continue
                if player.resources.get(offer, 0) >= 1:
                    proposals.append(
                        ProposePlayerTrade(player_id=current_player, offered_resources=((offer, 1),), requested_resources=((request, 1),))
                    )
                if player.resources.get(offer, 0) >= 2:
                    proposals.append(
                        ProposePlayerTrade(player_id=current_player, offered_resources=((offer, 2),), requested_resources=((request, 1),))
                    )
        return proposals

    def _score_player_trade_proposal(self, action: ProposePlayerTrade, state: GameState | None) -> float:
        if state is None:
            return -100.0
        offered = dict(action.offered_resources)
        requested = dict(action.requested_resources)
        if len(requested) != 1 or sum(requested.values()) != 1:
            return -100.0
        offer_count = sum(offered.values())
        if offer_count not in (1, 2) or any(amount <= 0 for amount in offered.values()):
            return -100.0
        player = state.players[action.player_id]
        if any(player.resources.get(resource, 0) < amount for resource, amount in offered.items()):
            return -100.0
        before = dict(player.resources)
        after = dict(before)
        for resource, amount in offered.items():
            after[resource] -= amount
        requested_resource = next(iter(requested.keys()))
        after[requested_resource] = after.get(requested_resource, 0) + 1
        enables_city = self._can_afford(after, _CITY_COST)
        enables_settlement = self._can_afford(after, _SETTLEMENT_COST)
        enables_dev = self._can_afford(after, _DEV_COST)
        missing_before = min(self._missing_resources(before, _CITY_COST), self._missing_resources(before, _SETTLEMENT_COST), self._missing_resources(before, _DEV_COST))
        missing_after = min(self._missing_resources(after, _CITY_COST), self._missing_resources(after, _SETTLEMENT_COST), self._missing_resources(after, _DEV_COST))
        production = self._player_production_resources(state, action.player_id)
        scarce_bonus = self._params.player_trade_scarce_resource_bonus if production.get(requested_resource, 0) <= 1 else 0.0
        score = (
            (self._params.player_trade_enable_city_bonus if enables_city else 0.0)
            + (self._params.player_trade_enable_settlement_bonus if enables_settlement else 0.0)
            + (self._params.player_trade_enable_dev_bonus if enables_dev else 0.0)
            + (4.0 if missing_after == 1 and missing_after < missing_before else 0.0)
            + scarce_bonus
            - self._critical_giveaway_penalty(before, after)
        )
        self._score_notes[id(action)] = f"propose: offer={offered} ask={requested}; score={score:.1f}"
        if score < self._params.player_trade_proposal_threshold:
            return -50.0 + score
        return score

    def _critical_giveaway_penalty(self, resources_before: dict[ResourceType, int], resources_after: dict[ResourceType, int]) -> float:
        for cost in (_CITY_COST, _SETTLEMENT_COST):
            if self._can_afford(resources_before, cost) and not self._can_afford(resources_after, cost):
                return self._params.player_trade_critical_giveaway_penalty
        return 0.0

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
                self_harm += self._params.robber_self_harm_penalty
                continue
            target_weight += self._params.robber_steal_value_weight + state.players[owner].victory_points * self._params.robber_leader_weight
        return 30 + token_score + target_weight - self_harm

    def _score_knight_play(self, state: GameState | None) -> float:
        if state is None or state.turn is None:
            return 0.0
        player_id = state.turn.current_player
        if state.largest_army_holder in (None, player_id):
            return self._params.knight_play_weight
        return self._params.knight_play_weight + 6.0

    def _evaluate_dev_purchase(self, state: GameState | None) -> float:
        if state is None or state.turn is None:
            return 0.0
        produced = self._player_production_resources(state, state.turn.current_player)
        ore_wheat = produced.get(ResourceType.ORE, 0) + produced.get(ResourceType.GRAIN, 0)
        return min(18.0, ore_wheat * self._params.dev_buy_weight)

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

    def _trade_response_evaluation(self, state: GameState | None) -> tuple[bool, str]:
        if state is None or state.player_trade is None or state.turn is None:
            return False, "reject: no trade context"
        responder_id = state.turn.priority_player
        if responder_id is None:
            return False, "reject: no responder"
        responder = state.players[responder_id]
        offered = dict(state.player_trade.offered_resources)
        requested = dict(state.player_trade.requested_resources)
        proposer = state.players[state.player_trade.proposer_player_id]
        if proposer.victory_points >= 9:
            return False, "reject: proposer near win"
        for resource, amount in requested.items():
            if responder.resources.get(resource, 0) < amount:
                return False, "reject: cannot pay requested"
        before = dict(responder.resources)
        after = dict(before)
        for resource, amount in requested.items():
            after[resource] -= amount
        for resource, amount in offered.items():
            after[resource] = after.get(resource, 0) + amount
        if self._critical_giveaway_penalty(before, after) > 0:
            return False, "reject: gives critical resource"
        production = self._player_production_resources(state, responder_id)
        scarce_gain = any(production.get(resource, 0) <= 1 and before.get(resource, 0) == 0 for resource in offered)
        score = (
            (self._params.player_trade_enable_city_bonus if self._can_afford(after, _CITY_COST) else 0.0)
            + (self._params.player_trade_enable_settlement_bonus if self._can_afford(after, _SETTLEMENT_COST) else 0.0)
            + (self._params.player_trade_enable_dev_bonus if self._can_afford(after, _DEV_COST) else 0.0)
            + (self._params.player_trade_scarce_resource_bonus if scarce_gain else 0.0)
        )
        if proposer.victory_points >= 8:
            score -= self._params.player_trade_leader_penalty
        if score >= self._params.player_trade_accept_threshold:
            return True, f"accept: score {score:.1f}"
        return False, f"reject: low benefit {score:.1f}"

    def _choose_discard_action(self, state: GameState, player_id: int) -> DiscardResources:
        required = state.discard_requirements.get(player_id, 0)
        hand = dict(state.players[player_id].resources)
        prioritized = sorted(
            (resource for resource in ResourceType if hand.get(resource, 0) > 0),
            key=lambda resource: (self._resource_values[resource], -hand[resource]),
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
