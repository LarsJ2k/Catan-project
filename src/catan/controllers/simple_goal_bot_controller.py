from __future__ import annotations

import random
import time
from collections import deque
from typing import Any, Sequence

from catan.controllers.heuristic_v1_baseline_bot_controller import (
    _CITY_COST,
    _DEV_COST,
    _SETTLEMENT_COST,
    _TOKEN_PIP_SCORES,
    _TERRAIN_TO_RESOURCE,
    HeuristicV1BaselineBotController,
)
from catan.core.models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    ChooseMonopolyResource,
    ChooseYearOfPlentyResources,
    DiscardResources,
    EndTurn,
    MoveRobber,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RespondToTradePass,
)
from catan.core.models.board import NodeId
from catan.core.models.enums import ResourceType, TurnStep
from catan.core.models.state import GameState
from catan.core.observer import DebugObservation, Observation

DEFAULT_BOT_ACTION_DELAY_SECONDS = 1.2


class SimpleGoalBotController(HeuristicV1BaselineBotController):
    """Simple deterministic goal bot: City -> Settlement -> Road -> Dev -> EndTurn."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        delay_seconds: float = DEFAULT_BOT_ACTION_DELAY_SECONDS,
        enable_delay: bool = True,
    ) -> None:
        super().__init__(seed=seed, delay_seconds=delay_seconds, enable_delay=enable_delay)
        self._rng = random.Random(seed)
        self._trade_proposed_this_turn = False
        self._last_turn_player_id: int | None = None
        self._stall_counter_by_player: dict[int, int] = {}
        self._snapshot_by_player: dict[int, tuple[int, int, int, int, int, int, int, int]] = {}

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        if not legal_actions:
            raise ValueError("SimpleGoalBotController received no legal actions.")
        state = observation.state if isinstance(observation, DebugObservation) else None
        if state is None:
            return self._pick_tie(list(legal_actions))
        self._prepare_turn_context(state)
        self._update_stall_counter(state)
        if self._enable_delay and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)

        discard_placeholder = next((a for a in legal_actions if isinstance(a, DiscardResources)), None)
        if discard_placeholder is not None:
            return self._choose_discard_action(state, discard_placeholder.player_id)
        if any(isinstance(a, MoveRobber) for a in legal_actions):
            return self._choose_move_robber(state, legal_actions)
        if any(isinstance(a, RespondToTradeInterested) for a in legal_actions):
            return self._choose_trade_response(state, legal_actions)
        if any(isinstance(a, ChooseYearOfPlentyResources) for a in legal_actions):
            return self._choose_year_of_plenty(state, legal_actions)
        if any(isinstance(a, ChooseMonopolyResource) for a in legal_actions):
            return self._choose_monopoly_resource(state, legal_actions)
        if any(isinstance(a, PlaceSetupSettlement) for a in legal_actions):
            return self._choose_setup_settlement(state, legal_actions)
        if any(isinstance(a, PlaceSetupRoad) for a in legal_actions):
            return self._choose_setup_road(state, legal_actions)
        if any(isinstance(a, PlayKnightCard) for a in legal_actions):
            return next(a for a in legal_actions if isinstance(a, PlayKnightCard))
        yop = self._playable_year_of_plenty(state, legal_actions)
        if yop is not None:
            return yop
        settlement_locations_available = self._has_immediate_settlement_location(state, legal_actions)
        rb = self._playable_road_building(state, legal_actions)
        if rb is not None:
            return rb
        monopoly = self._playable_monopoly(state, legal_actions)
        if monopoly is not None:
            return monopoly

        if settlement_locations_available:
            settlement_actions = [a for a in legal_actions if isinstance(a, BuildSettlement)]
            if settlement_actions:
                return self._best_settlement_action(state, settlement_actions)
            settlement_trade = self._trade_for_goal_if_almost_possible(state, legal_actions, _SETTLEMENT_COST)
            if settlement_trade is not None:
                return settlement_trade
            return next((a for a in legal_actions if isinstance(a, EndTurn)), self._pick_tie(list(legal_actions)))

        city_actions = [a for a in legal_actions if isinstance(a, BuildCity)]
        if city_actions:
            return self._best_city_action(state, city_actions)
        city_trade = self._trade_for_goal_if_almost_possible(state, legal_actions, _CITY_COST)
        if city_trade is not None:
            return city_trade

        settlement_actions = [a for a in legal_actions if isinstance(a, BuildSettlement)]
        if settlement_actions:
            return self._best_settlement_action(state, settlement_actions)
        settlement_trade = self._trade_for_goal_if_almost_possible(state, legal_actions, _SETTLEMENT_COST)
        if settlement_trade is not None:
            return settlement_trade

        road_action = self._road_toward_future_settlement(state, legal_actions)
        if road_action is not None:
            return road_action

        dev_action = next((a for a in legal_actions if isinstance(a, BuyDevelopmentCard)), None)
        if dev_action is not None and self._should_buy_dev_card(state):
            return dev_action

        return next((a for a in legal_actions if isinstance(a, EndTurn)), self._pick_tie(list(legal_actions)))

    def get_last_decision(self) -> dict[str, Any] | None:
        return getattr(self, "_last_decision", None)

    def _prepare_turn_context(self, state: GameState) -> None:
        if state.turn is None:
            self._trade_proposed_this_turn = False
            self._last_turn_player_id = None
            return
        if self._last_turn_player_id != state.turn.current_player:
            self._trade_proposed_this_turn = False
            self._last_turn_player_id = state.turn.current_player
        if state.turn.step != TurnStep.ACTIONS:
            self._trade_proposed_this_turn = False

    def _update_stall_counter(self, state: GameState) -> None:
        if state.turn is None:
            return
        player_id = state.turn.current_player
        player = state.players[player_id]
        snapshot = (
            player.victory_points,
            len([1 for owner in state.placed.settlements.values() if owner == player_id]),
            len([1 for owner in state.placed.cities.values() if owner == player_id]),
            len([1 for owner in state.placed.roads.values() if owner == player_id]),
            player.resources.get(ResourceType.BRICK, 0),
            player.resources.get(ResourceType.LUMBER, 0),
            player.resources.get(ResourceType.WOOL, 0),
            player.resources.get(ResourceType.GRAIN, 0) + player.resources.get(ResourceType.ORE, 0),
        )
        previous = self._snapshot_by_player.get(player_id)
        if previous is None or previous != snapshot:
            self._stall_counter_by_player[player_id] = 0
        else:
            self._stall_counter_by_player[player_id] = self._stall_counter_by_player.get(player_id, 0) + 1
        self._snapshot_by_player[player_id] = snapshot

    def _is_stalled(self, state: GameState) -> bool:
        if state.turn is None:
            return False
        return self._stall_counter_by_player.get(state.turn.current_player, 0) >= 3

    def _choose_setup_settlement(self, state: GameState, legal_actions: Sequence[Action]) -> Action:
        settlements = [a for a in legal_actions if isinstance(a, PlaceSetupSettlement)]
        ranked = sorted(
            settlements,
            key=lambda action: (
                self._node_pip_total(state, action.node_id),
                self._node_resource_diversity(state, action.node_id),
            ),
            reverse=True,
        )
        best = ranked[0]
        ties = [
            action
            for action in ranked
            if self._node_pip_total(state, action.node_id) == self._node_pip_total(state, best.node_id)
            and self._node_resource_diversity(state, action.node_id) == self._node_resource_diversity(state, best.node_id)
        ]
        return self._pick_tie(ties)

    def _choose_setup_road(self, state: GameState, legal_actions: Sequence[Action]) -> Action:
        roads = [a for a in legal_actions if isinstance(a, PlaceSetupRoad)]
        if not roads:
            return self._pick_tie(list(legal_actions))
        scored = sorted(roads, key=lambda action: self._road_progress_tuple(state, action.edge_id), reverse=True)
        best = scored[0]
        ties = [action for action in scored if self._road_progress_tuple(state, action.edge_id) == self._road_progress_tuple(state, best.edge_id)]
        return self._pick_tie(ties)

    def _best_city_action(self, state: GameState, actions: list[BuildCity]) -> BuildCity:
        ranked = sorted(actions, key=lambda action: self._node_pip_total(state, action.node_id), reverse=True)
        top = ranked[0]
        ties = [a for a in ranked if self._node_pip_total(state, a.node_id) == self._node_pip_total(state, top.node_id)]
        return self._pick_tie(ties)

    def _best_settlement_action(self, state: GameState, actions: list[BuildSettlement]) -> BuildSettlement:
        ranked = sorted(
            actions,
            key=lambda action: (self._node_pip_total(state, action.node_id), self._node_resource_diversity(state, action.node_id)),
            reverse=True,
        )
        top = ranked[0]
        ties = [
            action
            for action in ranked
            if (
                self._node_pip_total(state, action.node_id),
                self._node_resource_diversity(state, action.node_id),
            )
            == (
                self._node_pip_total(state, top.node_id),
                self._node_resource_diversity(state, top.node_id),
            )
        ]
        return self._pick_tie(ties)

    def _trade_for_goal_if_almost_possible(
        self,
        state: GameState,
        legal_actions: Sequence[Action],
        cost: dict[ResourceType, int],
    ) -> Action | None:
        if state.turn is None or state.turn.step != TurnStep.ACTIONS:
            return None
        player = state.players[state.turn.current_player]
        hand = dict(player.resources)
        missing = {resource: max(0, amount - hand.get(resource, 0)) for resource, amount in cost.items()}
        missing_types = [resource for resource, amount in missing.items() if amount > 0]
        if sum(missing.values()) != 1 or len(missing_types) != 1:
            return None
        missing_resource = missing_types[0]
        if not self._trade_proposed_this_turn:
            proposal = self._make_player_trade_for_goal(state, missing_resource, cost)
            if proposal is not None:
                self._trade_proposed_this_turn = True
                return proposal
        bank_trade = self._best_bank_trade_for_goal(legal_actions, cost)
        return bank_trade

    def _make_player_trade_for_goal(
        self,
        state: GameState,
        missing_resource: ResourceType,
        goal_cost: dict[ResourceType, int],
    ) -> ProposePlayerTrade | None:
        if state.turn is None or state.player_trade is not None:
            return None
        player_id = state.turn.current_player
        player = state.players[player_id]
        opponents = [p for p in state.players.values() if p.player_id != player_id]
        if not any(op.resources.get(missing_resource, 0) > 0 for op in opponents):
            return None
        candidates_2_for_1: list[ResourceType] = []
        candidates_1_for_1: list[ResourceType] = []
        for resource in ResourceType:
            if resource == missing_resource:
                continue
            if self._is_safe_trade_offer(player.resources, goal_cost, resource, 2):
                candidates_2_for_1.append(resource)
            if self._is_safe_trade_offer(player.resources, goal_cost, resource, 1):
                candidates_1_for_1.append(resource)
        if candidates_2_for_1:
            best_surplus = max(self._resource_surplus(player.resources, goal_cost, resource) for resource in candidates_2_for_1)
            ties = [resource for resource in candidates_2_for_1 if self._resource_surplus(player.resources, goal_cost, resource) == best_surplus]
            offered_amount = 2
            offered_resource = self._pick_tie(ties)
            goal_name = "City" if goal_cost == _CITY_COST else "Settlement"
            self._last_decision = {
                "type": "trade",
                "trade_shape": "2:1",
                "goal": goal_name,
                "missing_resource": missing_resource.name,
                "offered_resource": offered_resource.name,
                "offered_amount": offered_amount,
                "why_surplus": f"have {player.resources.get(offered_resource, 0)}, need {goal_cost.get(offered_resource, 0)} for goal",
                "explanation": f"Trade 2 {offered_resource.name.title()} -> 1 {missing_resource.name.title()} | enables {goal_name}",
            }
            return ProposePlayerTrade(
                player_id=player_id,
                offered_resources=((offered_resource, offered_amount),),
                requested_resources=((missing_resource, 1),),
            )
        if not candidates_1_for_1:
            return None
        best_surplus = max(self._resource_surplus(player.resources, goal_cost, resource) for resource in candidates_1_for_1)
        ties = [resource for resource in candidates_1_for_1 if self._resource_surplus(player.resources, goal_cost, resource) == best_surplus]
        offered_resource = self._pick_tie(ties)
        goal_name = "City" if goal_cost == _CITY_COST else "Settlement"
        self._last_decision = {
            "type": "trade",
            "trade_shape": "1:1",
            "goal": goal_name,
            "missing_resource": missing_resource.name,
            "offered_resource": offered_resource.name,
            "offered_amount": 1,
            "why_surplus": f"have {player.resources.get(offered_resource, 0)}, need {goal_cost.get(offered_resource, 0)} for goal",
            "explanation": f"Trade 1 {offered_resource.name.title()} -> 1 {missing_resource.name.title()} | fallback 1:1 enables {goal_name}",
        }
        return ProposePlayerTrade(
            player_id=player_id,
            offered_resources=((offered_resource, 1),),
            requested_resources=((missing_resource, 1),),
        )

    def _resource_surplus(
        self,
        hand: dict[ResourceType, int],
        goal_cost: dict[ResourceType, int],
        resource: ResourceType,
    ) -> int:
        return hand.get(resource, 0) - goal_cost.get(resource, 0)

    def _is_safe_trade_offer(
        self,
        hand: dict[ResourceType, int],
        goal_cost: dict[ResourceType, int],
        offer_resource: ResourceType,
        amount: int,
    ) -> bool:
        return hand.get(offer_resource, 0) - amount >= goal_cost.get(offer_resource, 0)

    def _best_bank_trade_for_goal(self, legal_actions: Sequence[Action], cost: dict[ResourceType, int]) -> BankTrade | None:
        candidates: list[BankTrade] = []
        for action in legal_actions:
            if not isinstance(action, BankTrade):
                continue
            if action.request_resource not in cost:
                continue
            if action.offer_resource in cost:
                continue
            candidates.append(action)
        if not candidates:
            return None
        ranked = sorted(candidates, key=lambda action: (action.trade_rate, action.offer_resource.name))
        return ranked[0]

    def _road_toward_future_settlement(self, state: GameState, legal_actions: Sequence[Action]) -> BuildRoad | None:
        if any(isinstance(action, BuildSettlement) for action in legal_actions):
            return None
        roads = [a for a in legal_actions if isinstance(a, BuildRoad)]
        if not roads:
            return None
        selected_target = self._select_future_settlement_target(state, legal_actions)
        if selected_target is None:
            return None
        target_node, target_distance = selected_target
        baseline = self._roads_to_node_distances(state)
        current_distance = baseline.get(target_node)
        if current_distance is None:
            return None
        candidates: list[BuildRoad] = []
        best_tuple: tuple[int, int, int] | None = None
        for action in roads:
            after_distance = self._distance_to_target_with_planned_roads(state, target_node, {action.edge_id})
            if after_distance is None:
                continue
            reduction = current_distance - after_distance
            if reduction <= 0:
                continue
            toward_score = self._edge_toward_target_score(state, action.edge_id, target_node)
            score = (reduction, toward_score[0], toward_score[1])
            if best_tuple is None or score > best_tuple:
                best_tuple = score
                candidates = [action]
            elif score == best_tuple:
                candidates.append(action)
        if candidates:
            chosen = self._pick_tie(candidates)
            self._last_decision = {
                "type": "road",
                "target_node": target_node,
                "target_distance": target_distance,
                "chosen_edge": chosen.edge_id,
                "explanation": f"Road toward node {target_node} | distance {target_distance}",
            }
            return chosen
        return None

    def _road_progress_tuple(self, state: GameState, edge_id: int) -> tuple[int, int, int]:
        target = self._select_future_settlement_target(state, ())
        if target is None:
            return (0, 0, 0)
        target_node, _ = target
        before_distance = self._distance_to_target_with_planned_roads(state, target_node, set())
        after_distance = self._distance_to_target_with_planned_roads(state, target_node, {edge_id})
        if before_distance is None or after_distance is None:
            return (0, 0, 0)
        reduction = max(0, before_distance - after_distance)
        toward = self._edge_toward_target_score(state, edge_id, target_node)
        return (reduction, toward[0], toward[1])

    def _road_anchors(self, state: GameState, player_id: int) -> set[NodeId]:
        anchors = {node_id for node_id, owner in state.placed.settlements.items() if owner == player_id}
        anchors.update(node_id for node_id, owner in state.placed.cities.items() if owner == player_id)
        for road_id, owner in state.placed.roads.items():
            if owner != player_id:
                continue
            node_a, node_b = state.board.edge_to_adjacent_nodes[road_id]
            anchors.add(node_a)
            anchors.add(node_b)
        return anchors

    def _select_future_settlement_target(self, state: GameState, legal_actions: Sequence[Action]) -> tuple[NodeId, int] | None:
        targets = self._valid_future_settlement_targets(state, legal_actions)
        if not targets:
            return None
        ranked = sorted(
            targets,
            key=lambda item: (
                item[1],
                -self._node_pip_total(state, item[0]),
                -self._node_resource_diversity(state, item[0]),
            ),
        )
        best = ranked[0]
        ties = [
            item
            for item in ranked
            if (
                item[1],
                self._node_pip_total(state, item[0]),
                self._node_resource_diversity(state, item[0]),
            )
            == (
                best[1],
                self._node_pip_total(state, best[0]),
                self._node_resource_diversity(state, best[0]),
            )
        ]
        return self._pick_tie(ties)

    def _valid_future_settlement_targets(self, state: GameState, legal_actions: Sequence[Action]) -> list[tuple[NodeId, int]]:
        currently_buildable = {action.node_id for action in legal_actions if isinstance(action, BuildSettlement)}
        distances = self._roads_to_node_distances(state)
        targets: list[tuple[NodeId, int]] = []
        for node_id in self._candidate_settlement_targets(state):
            if node_id in currently_buildable:
                continue
            distance = distances.get(node_id)
            if distance is None or distance <= 0:
                continue
            targets.append((node_id, distance))
        return targets

    def _roads_to_node_distances(self, state: GameState, planned_roads: set[int] | None = None) -> dict[NodeId, int]:
        if state.turn is None:
            return {}
        player_id = state.turn.current_player
        anchors = self._road_anchors(state, player_id)
        if not anchors:
            return {}
        traversable = {edge_id for edge_id, owner in state.placed.roads.items() if owner == player_id}
        traversable.update(edge_id for edge_id in state.board.edge_to_adjacent_nodes if edge_id not in state.placed.roads)
        if planned_roads:
            traversable.update(planned_roads)
        distances = {node_id: 0 for node_id in anchors}
        queue: deque[NodeId] = deque(anchors)
        while queue:
            node_id = queue.popleft()
            for edge_id in state.board.node_to_adjacent_edges.get(node_id, ()):
                if edge_id not in traversable:
                    continue
                node_a, node_b = state.board.edge_to_adjacent_nodes[edge_id]
                neighbor = node_b if node_a == node_id else node_a
                edge_cost = 0 if state.placed.roads.get(edge_id) == player_id or (planned_roads and edge_id in planned_roads) else 1
                cand = distances[node_id] + edge_cost
                if neighbor not in distances or cand < distances[neighbor]:
                    distances[neighbor] = cand
                    if edge_cost == 0:
                        queue.appendleft(neighbor)
                    else:
                        queue.append(neighbor)
        return distances

    def _distance_to_target_with_planned_roads(self, state: GameState, target: NodeId, planned_roads: set[int]) -> int | None:
        return self._roads_to_node_distances(state, planned_roads).get(target)

    def _edge_toward_target_score(self, state: GameState, edge_id: int, target: NodeId) -> tuple[int, int]:
        base = self._roads_to_node_distances(state)
        planned = self._roads_to_node_distances(state, {edge_id})
        node_a, node_b = state.board.edge_to_adjacent_nodes[edge_id]
        candidate_nodes = [node_id for node_id in (node_a, node_b) if planned.get(node_id, 99) < base.get(node_id, 99)]
        if not candidate_nodes:
            candidate_nodes = [node_a, node_b]
        best_node = min(candidate_nodes, key=lambda node_id: planned.get(node_id, 99) + (0 if node_id == target else 1))
        return (self._node_pip_total(state, best_node), self._node_resource_diversity(state, best_node))

    def _road_stall_tuple(self, state: GameState, edge_id: int) -> tuple[int, int]:
        node_a, node_b = state.board.edge_to_adjacent_nodes[edge_id]
        return (
            max(self._node_pip_total(state, node_a), self._node_pip_total(state, node_b)),
            max(self._node_resource_diversity(state, node_a), self._node_resource_diversity(state, node_b)),
        )

    def _should_buy_dev_card(self, state: GameState) -> bool:
        player = state.players[state.turn.current_player] if state.turn is not None else None
        if player is None:
            return False
        hand = dict(player.resources)
        if self._can_afford(hand, _CITY_COST) or self._can_afford(hand, _SETTLEMENT_COST):
            return False
        if self._missing_resources(hand, _CITY_COST) == 1 or self._missing_resources(hand, _SETTLEMENT_COST) == 1:
            return False
        return self._can_afford(hand, _DEV_COST) or self._is_stalled(state)

    def _choose_trade_response(self, state: GameState, legal_actions: Sequence[Action]) -> Action:
        accept = next((a for a in legal_actions if isinstance(a, RespondToTradeInterested)), None)
        reject = next((a for a in legal_actions if isinstance(a, RespondToTradePass)), None)
        if accept is None or reject is None:
            return self._pick_tie(list(legal_actions))
        if state.turn is None or state.player_trade is None or state.turn.priority_player is None:
            return reject
        responder = state.players[state.turn.priority_player]
        after = dict(responder.resources)
        for resource, amount in state.player_trade.requested_resources:
            after[resource] = after.get(resource, 0) - amount
        for resource, amount in state.player_trade.offered_resources:
            after[resource] = after.get(resource, 0) + amount
        if self._can_afford(after, _CITY_COST) or self._can_afford(after, _SETTLEMENT_COST):
            return accept
        return reject

    def _choose_discard_action(self, state: GameState, player_id: int) -> DiscardResources:
        required = state.discard_requirements.get(player_id, 0)
        hand = dict(state.players[player_id].resources)
        discards: dict[ResourceType, int] = {resource: 0 for resource in ResourceType}
        for _ in range(required):
            available = [resource for resource, amount in hand.items() if amount > 0]
            choice = max(available, key=lambda resource: hand[resource])
            ties = [resource for resource in available if hand[resource] == hand[choice]]
            pick = self._pick_tie(ties)
            hand[pick] -= 1
            discards[pick] += 1
        return DiscardResources(player_id=player_id, resources=tuple((resource, amount) for resource, amount in discards.items() if amount > 0))

    def _choose_move_robber(self, state: GameState, legal_actions: Sequence[Action]) -> MoveRobber:
        candidates = [a for a in legal_actions if isinstance(a, MoveRobber)]
        if state.turn is None:
            return self._pick_tie(candidates)
        own_nodes = {node_id for node_id, owner in state.placed.settlements.items() if owner == state.turn.current_player}
        own_nodes.update(node_id for node_id, owner in state.placed.cities.items() if owner == state.turn.current_player)
        filtered = [action for action in candidates if not any(node in own_nodes for node in state.board.tile_to_nodes.get(action.tile_id, ()))]
        if not filtered:
            filtered = candidates
        ranked = sorted(filtered, key=lambda action: self._robber_tile_score(state, action.tile_id), reverse=True)
        top = ranked[0]
        ties = [a for a in ranked if self._robber_tile_score(state, a.tile_id) == self._robber_tile_score(state, top.tile_id)]
        return self._pick_tie(ties)

    def _robber_tile_score(self, state: GameState, tile_id: int) -> int:
        tile = self._tile_by_id(state, tile_id)
        pip = _TOKEN_PIP_SCORES.get(tile.number_token or 0, 0)
        opp_structures = 0
        if state.turn is not None:
            for node_id in state.board.tile_to_nodes.get(tile_id, ()):
                owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
                if owner is not None and owner != state.turn.current_player:
                    opp_structures += 1
        return pip + opp_structures

    def _playable_year_of_plenty(self, state: GameState, legal_actions: Sequence[Action]) -> PlayYearOfPlentyCard | None:
        action = next((a for a in legal_actions if isinstance(a, PlayYearOfPlentyCard)), None)
        if action is None or state.turn is None:
            return None
        hand = dict(state.players[state.turn.current_player].resources)
        can_city = any(self._can_afford(self._with_added_two(hand, r1, r2), _CITY_COST) for r1 in ResourceType for r2 in ResourceType)
        can_settlement = any(self._can_afford(self._with_added_two(hand, r1, r2), _SETTLEMENT_COST) for r1 in ResourceType for r2 in ResourceType)
        return action if (can_city or can_settlement) else None

    def _choose_year_of_plenty(self, state: GameState, legal_actions: Sequence[Action]) -> ChooseYearOfPlentyResources:
        actions = [a for a in legal_actions if isinstance(a, ChooseYearOfPlentyResources)]
        player = state.players[state.turn.current_player] if state.turn is not None else None
        if player is None:
            return self._pick_tie(actions)
        hand = dict(player.resources)
        best: list[ChooseYearOfPlentyResources] = []
        best_score = -1
        for action in actions:
            after = self._with_added_two(hand, action.first_resource, action.second_resource)
            score = 2 if self._can_afford(after, _CITY_COST) else 1 if self._can_afford(after, _SETTLEMENT_COST) else 0
            if score > best_score:
                best_score = score
                best = [action]
            elif score == best_score:
                best.append(action)
        return self._pick_tie(best)

    def _playable_road_building(self, state: GameState, legal_actions: Sequence[Action]) -> PlayRoadBuildingCard | None:
        action = next((a for a in legal_actions if isinstance(a, PlayRoadBuildingCard)), None)
        if action is None:
            return None
        if self._has_immediate_settlement_location(state, legal_actions):
            return None
        if not any(isinstance(a, BuildRoad) for a in legal_actions):
            return None
        return action if self._select_future_settlement_target(state, legal_actions) is not None else None

    def _has_immediate_settlement_location(self, state: GameState, legal_actions: Sequence[Action]) -> bool:
        if state.turn is None:
            return False
        player = state.players[state.turn.current_player]
        if player.settlements_left <= 0:
            return False
        if any(isinstance(action, BuildSettlement) for action in legal_actions):
            return True
        distances = self._roads_to_node_distances(state)
        return any(
            distances.get(node_id) == 0
            for node_id in self._candidate_settlement_targets(state)
        )

    def _playable_monopoly(self, state: GameState, legal_actions: Sequence[Action]) -> PlayMonopolyCard | None:
        action = next((a for a in legal_actions if isinstance(a, PlayMonopolyCard)), None)
        if action is None:
            return None
        useful = self._best_monopoly_take(state)
        return action if useful >= 2 else None

    def _choose_monopoly_resource(self, state: GameState, legal_actions: Sequence[Action]) -> ChooseMonopolyResource:
        actions = [a for a in legal_actions if isinstance(a, ChooseMonopolyResource)]
        if state.turn is None:
            return self._pick_tie(actions)
        player = state.players[state.turn.current_player]
        missing_city = {r for r, needed in _CITY_COST.items() if player.resources.get(r, 0) < needed}
        missing_settlement = {r for r, needed in _SETTLEMENT_COST.items() if player.resources.get(r, 0) < needed}
        target_missing = missing_city or missing_settlement
        ranked = sorted(
            actions,
            key=lambda action: (
                self._monopoly_total_on_table(state, action.resource),
                1 if action.resource in target_missing else 0,
            ),
            reverse=True,
        )
        top = ranked[0]
        ties = [a for a in ranked if self._monopoly_total_on_table(state, a.resource) == self._monopoly_total_on_table(state, top.resource)]
        return self._pick_tie(ties)

    def _best_monopoly_take(self, state: GameState) -> int:
        return max((self._monopoly_total_on_table(state, resource) for resource in ResourceType), default=0)

    def _monopoly_total_on_table(self, state: GameState, resource: ResourceType) -> int:
        if state.turn is None:
            return 0
        return sum(
            player.resources.get(resource, 0)
            for player_id, player in state.players.items()
            if player_id != state.turn.current_player
        )

    def _node_pip_total(self, state: GameState, node_id: NodeId) -> int:
        total = 0
        for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()):
            total += _TOKEN_PIP_SCORES.get(self._tile_by_id(state, tile_id).number_token or 0, 0)
        return total

    def _node_resource_diversity(self, state: GameState, node_id: NodeId) -> int:
        resources = set()
        for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()):
            resource = _TERRAIN_TO_RESOURCE.get(self._tile_by_id(state, tile_id).terrain)
            if resource is not None:
                resources.add(resource)
        return len(resources)

    def _with_added_two(
        self,
        hand: dict[ResourceType, int],
        first: ResourceType,
        second: ResourceType,
    ) -> dict[ResourceType, int]:
        after = dict(hand)
        after[first] = after.get(first, 0) + 1
        after[second] = after.get(second, 0) + 1
        return after

    def _pick_tie(self, candidates: Sequence[Any]) -> Any:
        if len(candidates) == 1:
            return candidates[0]
        return candidates[self._rng.randrange(len(candidates))]
