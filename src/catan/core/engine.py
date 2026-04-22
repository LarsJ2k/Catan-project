from __future__ import annotations

from dataclasses import replace

from .models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    DiscardResources,
    EndTurn,
    MoveRobber,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    RollDice,
    SkipSteal,
    StealResource,
)
from .models.board import EdgeId, NodeId, PlayerId, TileId
from .models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from .models.state import GameState, InitialGameConfig, PlacedPieces, PlayerState, SetupState, TurnState
from .observer import DebugObservation, Observation, PlayerObservation, PublicPlayerView
from .rng import next_u32, roll_two_d6

ROAD_COST = {ResourceType.BRICK: 1, ResourceType.LUMBER: 1}
SETTLEMENT_COST = {
    ResourceType.BRICK: 1,
    ResourceType.LUMBER: 1,
    ResourceType.WOOL: 1,
    ResourceType.GRAIN: 1,
}
CITY_COST = {ResourceType.ORE: 3, ResourceType.GRAIN: 2}
BANK_TRADE_RATE = 4

TERRAIN_TO_RESOURCE = {
    TerrainType.HILLS: ResourceType.BRICK,
    TerrainType.FOREST: ResourceType.LUMBER,
    TerrainType.PASTURE: ResourceType.WOOL,
    TerrainType.FIELDS: ResourceType.GRAIN,
    TerrainType.MOUNTAINS: ResourceType.ORE,
}


def create_initial_state(config: InitialGameConfig) -> GameState:
    players: dict[PlayerId, PlayerState] = {}
    for player_id in config.player_ids:
        players[player_id] = PlayerState(
            player_id=player_id,
            resources={resource: 0 for resource in ResourceType},
        )

    robber_tile_id = next((tile.id for tile in config.board.tiles if tile.terrain == TerrainType.DESERT), None)

    return GameState(
        board=config.board,
        players=players,
        phase=GamePhase.SETUP_FORWARD,
        setup=SetupState(
            pending_settlement_player=config.player_ids[0],
            order=list(config.player_ids),
            index=0,
        ),
        turn=None,
        placed=PlacedPieces(),
        rng_state=config.seed,
        robber_tile_id=robber_tile_id,
    )


def get_legal_actions(state: GameState, player_id: PlayerId) -> list[Action]:
    if state.phase == GamePhase.GAME_OVER:
        return []
    if state.phase in (GamePhase.SETUP_FORWARD, GamePhase.SETUP_REVERSE):
        return _get_setup_legal_actions(state, player_id)
    if state.turn is None:
        return []

    if state.turn.step == TurnStep.DISCARD:
        if state.turn.priority_player != player_id:
            return []
        return [DiscardResources(player_id=player_id, resources=tuple())]

    acting_player = state.turn.priority_player if state.turn.priority_player is not None else state.turn.current_player
    if acting_player != player_id:
        return []

    if state.turn.step == TurnStep.ROLL:
        return [RollDice(player_id=player_id)]
    if state.turn.step == TurnStep.ROBBER_MOVE:
        return [MoveRobber(player_id=player_id, tile_id=tile.id) for tile in state.board.tiles if tile.id != state.robber_tile_id]
    if state.turn.step == TurnStep.ROBBER_STEAL:
        return [StealResource(player_id=player_id, target_player_id=target) for target in _eligible_robber_targets(state, player_id)]

    legal_actions: list[Action] = [EndTurn(player_id=player_id)]
    legal_actions.extend(BuildRoad(player_id=player_id, edge_id=edge_id) for edge_id in _legal_road_edges(state, player_id))
    legal_actions.extend(
        BuildSettlement(player_id=player_id, node_id=node_id) for node_id in _legal_settlement_nodes_main(state, player_id)
    )
    legal_actions.extend(BuildCity(player_id=player_id, node_id=node_id) for node_id in _legal_city_nodes(state, player_id))
    legal_actions.extend(_legal_bank_trades(state, player_id))
    return legal_actions


def apply_action(state: GameState, action: Action) -> GameState:
    if not _is_legal_action(state, action):
        raise ValueError(f"Illegal action: {action}")

    if isinstance(action, PlaceSetupSettlement):
        return _apply_setup_settlement(state, action)
    if isinstance(action, PlaceSetupRoad):
        return _apply_setup_road(state, action)
    if isinstance(action, RollDice):
        return _apply_roll_dice(state)
    if isinstance(action, DiscardResources):
        return _apply_discard_resources(state, action)
    if isinstance(action, MoveRobber):
        return _apply_move_robber(state, action)
    if isinstance(action, StealResource):
        return _apply_steal_resource(state, action)
    if isinstance(action, SkipSteal):
        return replace(state, turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None))
    if isinstance(action, BuildRoad):
        return _apply_build_road(state, action)
    if isinstance(action, BuildSettlement):
        return _apply_build_settlement(state, action)
    if isinstance(action, BuildCity):
        return _apply_build_city(state, action)
    if isinstance(action, BankTrade):
        return _apply_bank_trade(state, action)
    if isinstance(action, EndTurn):
        return _apply_end_turn(state)

    raise ValueError(f"Unhandled action type: {type(action).__name__}")


def is_terminal(state: GameState) -> bool:
    return state.phase == GamePhase.GAME_OVER or state.winner is not None


def get_observation(state: GameState, player_id: PlayerId, *, debug: bool = False) -> Observation:
    if debug:
        return DebugObservation(state=state)

    own = state.players[player_id]
    own_resources = {resource.name: count for resource, count in own.resources.items()}
    players_public = tuple(
        PublicPlayerView(
            player_id=pid,
            victory_points=pstate.victory_points,
            resource_count=sum(pstate.resources.values()),
        )
        for pid, pstate in state.players.items()
    )

    return PlayerObservation(
        requesting_player_id=player_id,
        current_player_id=state.turn.current_player if state.turn else None,
        phase=state.phase.name,
        own_resources=own_resources,
        players_public=players_public,
    )


def _is_legal_action(state: GameState, action: Action) -> bool:
    if isinstance(action, DiscardResources):
        return _is_legal_discard_action(state, action)
    if isinstance(action, MoveRobber):
        return state.turn is not None and state.turn.step == TurnStep.ROBBER_MOVE and action.tile_id != state.robber_tile_id and action.player_id == state.turn.current_player
    if isinstance(action, StealResource):
        return state.turn is not None and state.turn.step == TurnStep.ROBBER_STEAL and action.player_id == state.turn.current_player and action.target_player_id in _eligible_robber_targets(state, action.player_id)
    return action in get_legal_actions(state, action.player_id)


def _is_legal_discard_action(state: GameState, action: DiscardResources) -> bool:
    if state.turn is None or state.turn.step != TurnStep.DISCARD:
        return False
    if state.turn.priority_player != action.player_id:
        return False
    required = state.discard_requirements.get(action.player_id, 0)
    if required <= 0:
        return False
    counts = dict(action.resources)
    total = sum(counts.values())
    if total != required:
        return False
    player_resources = state.players[action.player_id].resources
    for resource, amount in counts.items():
        if amount < 0 or amount > player_resources.get(resource, 0):
            return False
    return True


def _get_setup_legal_actions(state: GameState, player_id: PlayerId) -> list[Action]:
    if state.setup.pending_settlement_player == player_id:
        return [PlaceSetupSettlement(player_id=player_id, node_id=node_id) for node_id in _legal_setup_settlement_nodes(state)]
    if state.setup.pending_road_player == player_id:
        return [PlaceSetupRoad(player_id=player_id, edge_id=edge_id) for edge_id in _legal_setup_road_edges(state, player_id)]
    return []


def _legal_setup_settlement_nodes(state: GameState) -> list[NodeId]:
    return [node_id for node_id in state.board.nodes if _can_place_settlement_at_node(state, node_id)]


def _legal_setup_road_edges(state: GameState, player_id: PlayerId) -> list[EdgeId]:
    origin = state.setup.pending_road_origin_node
    if origin is None:
        return []
    return [edge_id for edge_id in state.board.node_to_adjacent_edges.get(origin, ()) if edge_id not in state.placed.roads]


def _legal_road_edges(state: GameState, player_id: PlayerId) -> list[EdgeId]:
    player = state.players[player_id]
    if player.roads_left <= 0 or not _has_resources(player, ROAD_COST):
        return []
    anchors = set(_player_anchor_nodes(state, player_id))
    return [edge.id for edge in state.board.edges if edge.id not in state.placed.roads and (edge.node_a in anchors or edge.node_b in anchors)]


def _legal_settlement_nodes_main(state: GameState, player_id: PlayerId) -> list[NodeId]:
    player = state.players[player_id]
    if player.settlements_left <= 0 or not _has_resources(player, SETTLEMENT_COST):
        return []
    connected_nodes = set(_nodes_connected_to_player_roads(state, player_id))
    return [node_id for node_id in connected_nodes if _can_place_settlement_at_node(state, node_id)]


def _legal_city_nodes(state: GameState, player_id: PlayerId) -> list[NodeId]:
    player = state.players[player_id]
    if player.cities_left <= 0 or not _has_resources(player, CITY_COST):
        return []
    return [node_id for node_id, owner in state.placed.settlements.items() if owner == player_id]


def _legal_bank_trades(state: GameState, player_id: PlayerId) -> list[BankTrade]:
    player = state.players[player_id]
    actions: list[BankTrade] = []
    for offer_resource, amount in player.resources.items():
        if amount < BANK_TRADE_RATE:
            continue
        for request_resource in ResourceType:
            if request_resource == offer_resource:
                continue
            actions.append(
                BankTrade(
                    player_id=player_id,
                    offer_resource=offer_resource,
                    request_resource=request_resource,
                )
            )
    return actions


def _can_place_settlement_at_node(state: GameState, node_id: NodeId) -> bool:
    if node_id in state.placed.settlements or node_id in state.placed.cities:
        return False
    return all(neighbor not in state.placed.settlements and neighbor not in state.placed.cities for neighbor in state.board.node_neighbors(node_id))


def _nodes_connected_to_player_roads(state: GameState, player_id: PlayerId) -> tuple[NodeId, ...]:
    connected: set[NodeId] = set()
    for edge_id, owner in state.placed.roads.items():
        if owner == player_id:
            a, b = state.board.edge_to_adjacent_nodes[edge_id]
            connected.update((a, b))
    return tuple(connected)


def _player_anchor_nodes(state: GameState, player_id: PlayerId) -> tuple[NodeId, ...]:
    anchors = set(_nodes_connected_to_player_roads(state, player_id))
    anchors.update(node_id for node_id, owner in state.placed.settlements.items() if owner == player_id)
    anchors.update(node_id for node_id, owner in state.placed.cities.items() if owner == player_id)
    return tuple(anchors)


def _apply_setup_settlement(state: GameState, action: PlaceSetupSettlement) -> GameState:
    player = state.players[action.player_id]
    settlements = {**state.placed.settlements, action.node_id: action.player_id}
    updated_player = replace(
        player,
        settlements_left=player.settlements_left - 1,
        victory_points=player.victory_points + 1,
        setup_settlements_placed=player.setup_settlements_placed + 1,
    )
    next_state = replace(
        state,
        players={**state.players, action.player_id: updated_player},
        placed=replace(state.placed, settlements=settlements),
        setup=replace(state.setup, pending_settlement_player=None, pending_road_player=action.player_id, pending_road_origin_node=action.node_id),
    )
    if updated_player.setup_settlements_placed == 2:
        next_state = _grant_setup_starting_resources(next_state, action.player_id, action.node_id)
    return _update_winner(next_state, action.player_id)


def _apply_setup_road(state: GameState, action: PlaceSetupRoad) -> GameState:
    roads = {**state.placed.roads, action.edge_id: action.player_id}
    updated_player = replace(state.players[action.player_id], roads_left=state.players[action.player_id].roads_left - 1)
    setup = replace(state.setup, pending_road_player=None, pending_road_origin_node=None)

    if state.phase == GamePhase.SETUP_FORWARD:
        if state.setup.index < len(state.setup.order) - 1:
            next_index = state.setup.index + 1
            setup = replace(setup, index=next_index, pending_settlement_player=state.setup.order[next_index])
            phase = GamePhase.SETUP_FORWARD
        else:
            setup = replace(setup, index=len(state.setup.order) - 1, pending_settlement_player=state.setup.order[-1])
            phase = GamePhase.SETUP_REVERSE
    else:
        if state.setup.index > 0:
            next_index = state.setup.index - 1
            setup = replace(setup, index=next_index, pending_settlement_player=state.setup.order[next_index])
            phase = GamePhase.SETUP_REVERSE
        else:
            phase = GamePhase.MAIN_TURN
            setup = replace(setup, pending_settlement_player=None)

    next_state = replace(state, phase=phase, setup=setup, players={**state.players, action.player_id: updated_player}, placed=replace(state.placed, roads=roads))
    if phase == GamePhase.MAIN_TURN:
        next_state = replace(next_state, turn=TurnState(current_player=state.setup.order[0], step=TurnStep.ROLL))
    return _update_winner(next_state, action.player_id)


def _apply_roll_dice(state: GameState) -> GameState:
    rolled, next_rng = roll_two_d6(state.rng_state)
    total = sum(rolled)

    if total == 7:
        discard_requirements = {
            pid: sum(player.resources.values()) // 2
            for pid, player in state.players.items()
            if sum(player.resources.values()) > 7
        }
        if discard_requirements:
            first = _next_discard_player(discard_requirements)
            return replace(
                state,
                rng_state=next_rng,
                discard_requirements=discard_requirements,
                turn=replace(state.turn, last_roll=rolled, step=TurnStep.DISCARD, priority_player=first),
            )
        return replace(
            state,
            rng_state=next_rng,
            turn=replace(state.turn, last_roll=rolled, step=TurnStep.ROBBER_MOVE, priority_player=state.turn.current_player),
        )

    next_state = replace(state, turn=replace(state.turn, step=TurnStep.ACTIONS, last_roll=rolled, priority_player=None), rng_state=next_rng)
    return _distribute_roll_resources(next_state, total)


def _apply_discard_resources(state: GameState, action: DiscardResources) -> GameState:
    player = state.players[action.player_id]
    resources = dict(player.resources)
    for resource, amount in action.resources:
        resources[resource] -= amount
    updated_player = replace(player, resources=resources)

    new_requirements = dict(state.discard_requirements)
    new_requirements[action.player_id] = 0
    next_player = _next_discard_player(new_requirements)
    if next_player is None:
        return replace(
            state,
            players={**state.players, action.player_id: updated_player},
            discard_requirements={pid: amt for pid, amt in new_requirements.items() if amt > 0},
            turn=replace(state.turn, step=TurnStep.ROBBER_MOVE, priority_player=state.turn.current_player),
        )

    return replace(
        state,
        players={**state.players, action.player_id: updated_player},
        discard_requirements={pid: amt for pid, amt in new_requirements.items() if amt > 0},
        turn=replace(state.turn, step=TurnStep.DISCARD, priority_player=next_player),
    )


def _apply_move_robber(state: GameState, action: MoveRobber) -> GameState:
    moved_state = replace(state, robber_tile_id=action.tile_id)
    targets = _eligible_robber_targets(moved_state, action.player_id)
    if not targets:
        return replace(moved_state, turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None))
    if len(targets) == 1:
        return _resolve_robber_steal(moved_state, action.player_id, targets[0])
    return replace(moved_state, turn=replace(state.turn, step=TurnStep.ROBBER_STEAL, priority_player=action.player_id))


def _apply_steal_resource(state: GameState, action: StealResource) -> GameState:
    return _resolve_robber_steal(state, action.player_id, action.target_player_id)


def _resolve_robber_steal(state: GameState, player_id: PlayerId, target_player_id: PlayerId) -> GameState:
    target = state.players[target_player_id]
    taker = state.players[player_id]
    available = [res for res, amount in target.resources.items() if amount > 0]
    if not available:
        return replace(state, turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None))

    value, next_rng = next_u32(state.rng_state)
    resource = available[value % len(available)]

    target_res = dict(target.resources)
    taker_res = dict(taker.resources)
    target_res[resource] -= 1
    taker_res[resource] += 1

    return replace(
        state,
        rng_state=next_rng,
        players={
            **state.players,
            target_player_id: replace(target, resources=target_res),
            player_id: replace(taker, resources=taker_res),
        },
        turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None),
    )


def _eligible_robber_targets(state: GameState, player_id: PlayerId) -> list[PlayerId]:
    if state.robber_tile_id is None:
        return []
    targets: set[PlayerId] = set()
    tile_nodes = state.board.tile_to_nodes.get(state.robber_tile_id, ())
    for node_id in tile_nodes:
        owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
        if owner is not None and owner != player_id and sum(state.players[owner].resources.values()) > 0:
            targets.add(owner)
    return sorted(targets)


def _next_discard_player(requirements: dict[PlayerId, int]) -> PlayerId | None:
    candidates = [pid for pid, amt in sorted(requirements.items()) if amt > 0]
    return candidates[0] if candidates else None


def _apply_build_road(state: GameState, action: BuildRoad) -> GameState:
    player = _pay_cost(state.players[action.player_id], ROAD_COST)
    roads = {**state.placed.roads, action.edge_id: action.player_id}
    return replace(state, players={**state.players, action.player_id: replace(player, roads_left=player.roads_left - 1)}, placed=replace(state.placed, roads=roads))


def _apply_build_settlement(state: GameState, action: BuildSettlement) -> GameState:
    player = _pay_cost(state.players[action.player_id], SETTLEMENT_COST)
    settlements = {**state.placed.settlements, action.node_id: action.player_id}
    next_state = replace(
        state,
        players={**state.players, action.player_id: replace(player, settlements_left=player.settlements_left - 1, victory_points=player.victory_points + 1)},
        placed=replace(state.placed, settlements=settlements),
    )
    return _update_winner(next_state, action.player_id)


def _apply_build_city(state: GameState, action: BuildCity) -> GameState:
    player = _pay_cost(state.players[action.player_id], CITY_COST)
    settlements = dict(state.placed.settlements)
    settlements.pop(action.node_id)
    cities = {**state.placed.cities, action.node_id: action.player_id}
    next_state = replace(
        state,
        players={**state.players, action.player_id: replace(player, settlements_left=player.settlements_left + 1, cities_left=player.cities_left - 1, victory_points=player.victory_points + 1)},
        placed=replace(state.placed, settlements=settlements, cities=cities),
    )
    return _update_winner(next_state, action.player_id)


def _apply_bank_trade(state: GameState, action: BankTrade) -> GameState:
    player = state.players[action.player_id]
    resources = dict(player.resources)
    resources[action.offer_resource] -= BANK_TRADE_RATE
    resources[action.request_resource] += 1
    return replace(state, players={**state.players, action.player_id: replace(player, resources=resources)})


def _apply_end_turn(state: GameState) -> GameState:
    order = list(state.players.keys())
    idx = order.index(state.turn.current_player)
    next_player = order[(idx + 1) % len(order)]
    return replace(state, turn=replace(state.turn, current_player=next_player, step=TurnStep.ROLL, last_roll=None, priority_player=None))


def _grant_setup_starting_resources(state: GameState, player_id: PlayerId, node_id: NodeId) -> GameState:
    player = state.players[player_id]
    resources = dict(player.resources)
    for tile_id in state.board.node_to_adjacent_tiles.get(node_id, ()): 
        tile = state.board.tiles[tile_id]
        resource = TERRAIN_TO_RESOURCE.get(tile.terrain)
        if resource is not None:
            resources[resource] += 1
    return replace(state, players={**state.players, player_id: replace(player, resources=resources)})


def _distribute_roll_resources(state: GameState, roll_total: int) -> GameState:
    players = dict(state.players)
    for tile in state.board.tiles:
        if tile.id == state.robber_tile_id:
            continue
        if tile.number_token != roll_total:
            continue
        resource = TERRAIN_TO_RESOURCE.get(tile.terrain)
        if resource is None:
            continue
        for node_id, adjacent_tiles in state.board.node_to_adjacent_tiles.items():
            if tile.id not in adjacent_tiles:
                continue
            settlement_owner = state.placed.settlements.get(node_id)
            city_owner = state.placed.cities.get(node_id)
            if settlement_owner is not None:
                p = players[settlement_owner]
                res = dict(p.resources)
                res[resource] += 1
                players[settlement_owner] = replace(p, resources=res)
            elif city_owner is not None:
                p = players[city_owner]
                res = dict(p.resources)
                res[resource] += 2
                players[city_owner] = replace(p, resources=res)
    return replace(state, players=players)


def _has_resources(player: PlayerState, cost: dict[ResourceType, int]) -> bool:
    return all(player.resources.get(resource, 0) >= amount for resource, amount in cost.items())


def _pay_cost(player: PlayerState, cost: dict[ResourceType, int]) -> PlayerState:
    resources = dict(player.resources)
    for resource, amount in cost.items():
        resources[resource] -= amount
    return replace(player, resources=resources)


def _update_winner(state: GameState, player_id: PlayerId) -> GameState:
    if state.players[player_id].victory_points >= 10:
        return replace(state, winner=player_id, phase=GamePhase.GAME_OVER)
    return state
