from __future__ import annotations

from dataclasses import replace

from .models.action import (
    Action,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    EndTurn,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    RollDice,
)
from .models.board import EdgeId, NodeId, PlayerId
from .models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from .models.state import GameState, InitialGameConfig, PlacedPieces, PlayerState, SetupState, TurnState
from .observer import DebugObservation, Observation, PlayerObservation, PublicPlayerView
from .rng import roll_two_d6

ROAD_COST = {ResourceType.BRICK: 1, ResourceType.LUMBER: 1}
SETTLEMENT_COST = {
    ResourceType.BRICK: 1,
    ResourceType.LUMBER: 1,
    ResourceType.WOOL: 1,
    ResourceType.GRAIN: 1,
}
CITY_COST = {ResourceType.ORE: 3, ResourceType.GRAIN: 2}

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
    )


def get_legal_actions(state: GameState, player_id: PlayerId) -> list[Action]:
    if state.phase == GamePhase.GAME_OVER:
        return []
    if state.phase in (GamePhase.SETUP_FORWARD, GamePhase.SETUP_REVERSE):
        return _get_setup_legal_actions(state, player_id)
    if state.turn is None or state.turn.current_player != player_id:
        return []
    if state.turn.step == TurnStep.ROLL:
        return [RollDice(player_id=player_id)]

    legal: list[Action] = [EndTurn(player_id=player_id)]
    legal.extend(BuildRoad(player_id=player_id, edge_id=edge_id) for edge_id in _legal_road_edges(state, player_id))
    legal.extend(
        BuildSettlement(player_id=player_id, node_id=node_id) for node_id in _legal_settlement_nodes_main(state, player_id)
    )
    legal.extend(BuildCity(player_id=player_id, node_id=node_id) for node_id in _legal_city_nodes(state, player_id))
    return legal


def apply_action(state: GameState, action: Action) -> GameState:
    if action not in get_legal_actions(state, action.player_id):
        raise ValueError(f"Illegal action: {action}")

    if isinstance(action, PlaceSetupSettlement):
        return _apply_setup_settlement(state, action)
    if isinstance(action, PlaceSetupRoad):
        return _apply_setup_road(state, action)
    if isinstance(action, RollDice):
        return _apply_roll_dice(state)
    if isinstance(action, BuildRoad):
        return _apply_build_road(state, action)
    if isinstance(action, BuildSettlement):
        return _apply_build_settlement(state, action)
    if isinstance(action, BuildCity):
        return _apply_build_city(state, action)
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
    legal: list[EdgeId] = []
    for edge_id in state.board.node_to_adjacent_edges.get(origin, ()):
        if edge_id not in state.placed.roads:
            legal.append(edge_id)
    return legal


def _legal_road_edges(state: GameState, player_id: PlayerId) -> list[EdgeId]:
    player = state.players[player_id]
    if player.roads_left <= 0 or not _has_resources(player, ROAD_COST):
        return []

    anchors = set(_player_anchor_nodes(state, player_id))
    legal: list[EdgeId] = []
    for edge in state.board.edges:
        if edge.id in state.placed.roads:
            continue
        if edge.node_a in anchors or edge.node_b in anchors:
            legal.append(edge.id)
    return legal


def _legal_settlement_nodes_main(state: GameState, player_id: PlayerId) -> list[NodeId]:
    player = state.players[player_id]
    if player.settlements_left <= 0 or not _has_resources(player, SETTLEMENT_COST):
        return []

    connected_nodes = set(_nodes_connected_to_player_roads(state, player_id))
    return [
        node_id
        for node_id in connected_nodes
        if _can_place_settlement_at_node(state, node_id)
    ]


def _legal_city_nodes(state: GameState, player_id: PlayerId) -> list[NodeId]:
    player = state.players[player_id]
    if player.cities_left <= 0 or not _has_resources(player, CITY_COST):
        return []
    return [node_id for node_id, owner in state.placed.settlements.items() if owner == player_id]


def _can_place_settlement_at_node(state: GameState, node_id: NodeId) -> bool:
    if node_id in state.placed.settlements or node_id in state.placed.cities:
        return False
    for neighbor in state.board.node_neighbors(node_id):
        if neighbor in state.placed.settlements or neighbor in state.placed.cities:
            return False
    return True


def _nodes_connected_to_player_roads(state: GameState, player_id: PlayerId) -> tuple[NodeId, ...]:
    connected: set[NodeId] = set()
    for edge_id, owner in state.placed.roads.items():
        if owner != player_id:
            continue
        a, b = state.board.edge_to_adjacent_nodes[edge_id]
        connected.add(a)
        connected.add(b)
    return tuple(connected)


def _player_anchor_nodes(state: GameState, player_id: PlayerId) -> tuple[NodeId, ...]:
    anchors = set(_nodes_connected_to_player_roads(state, player_id))
    anchors.update(node_id for node_id, owner in state.placed.settlements.items() if owner == player_id)
    anchors.update(node_id for node_id, owner in state.placed.cities.items() if owner == player_id)
    return tuple(anchors)


def _apply_setup_settlement(state: GameState, action: PlaceSetupSettlement) -> GameState:
    player = state.players[action.player_id]
    settlements = dict(state.placed.settlements)
    settlements[action.node_id] = action.player_id

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
        setup=replace(
            state.setup,
            pending_settlement_player=None,
            pending_road_player=action.player_id,
            pending_road_origin_node=action.node_id,
        ),
    )

    if updated_player.setup_settlements_placed == 2:
        next_state = _grant_setup_starting_resources(next_state, action.player_id, action.node_id)

    return _update_winner(next_state, action.player_id)


def _apply_setup_road(state: GameState, action: PlaceSetupRoad) -> GameState:
    roads = dict(state.placed.roads)
    roads[action.edge_id] = action.player_id
    player = state.players[action.player_id]
    updated_player = replace(player, roads_left=player.roads_left - 1)

    setup = replace(
        state.setup,
        pending_road_player=None,
        pending_road_origin_node=None,
    )

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

    next_state = replace(
        state,
        phase=phase,
        setup=setup,
        players={**state.players, action.player_id: updated_player},
        placed=replace(state.placed, roads=roads),
        turn=state.turn,
    )

    if phase == GamePhase.MAIN_TURN:
        next_state = replace(
            next_state,
            turn=TurnState(current_player=state.setup.order[0], step=TurnStep.ROLL),
        )

    return _update_winner(next_state, action.player_id)


def _apply_roll_dice(state: GameState) -> GameState:
    assert state.turn is not None
    rolled, next_rng = roll_two_d6(state.rng_state)
    next_state = replace(
        state,
        turn=replace(state.turn, step=TurnStep.ACTIONS, last_roll=rolled),
        rng_state=next_rng,
    )
    return _distribute_roll_resources(next_state, sum(rolled))


def _apply_build_road(state: GameState, action: BuildRoad) -> GameState:
    player = _pay_cost(state.players[action.player_id], ROAD_COST)
    roads = dict(state.placed.roads)
    roads[action.edge_id] = action.player_id
    return replace(
        state,
        players={**state.players, action.player_id: replace(player, roads_left=player.roads_left - 1)},
        placed=replace(state.placed, roads=roads),
    )


def _apply_build_settlement(state: GameState, action: BuildSettlement) -> GameState:
    player = _pay_cost(state.players[action.player_id], SETTLEMENT_COST)
    settlements = dict(state.placed.settlements)
    settlements[action.node_id] = action.player_id
    next_state = replace(
        state,
        players={
            **state.players,
            action.player_id: replace(
                player,
                settlements_left=player.settlements_left - 1,
                victory_points=player.victory_points + 1,
            ),
        },
        placed=replace(state.placed, settlements=settlements),
    )
    return _update_winner(next_state, action.player_id)


def _apply_build_city(state: GameState, action: BuildCity) -> GameState:
    player = _pay_cost(state.players[action.player_id], CITY_COST)
    settlements = dict(state.placed.settlements)
    del settlements[action.node_id]

    cities = dict(state.placed.cities)
    cities[action.node_id] = action.player_id

    next_state = replace(
        state,
        players={
            **state.players,
            action.player_id: replace(
                player,
                settlements_left=player.settlements_left + 1,
                cities_left=player.cities_left - 1,
                victory_points=player.victory_points + 1,
            ),
        },
        placed=replace(state.placed, settlements=settlements, cities=cities),
    )
    return _update_winner(next_state, action.player_id)


def _apply_end_turn(state: GameState) -> GameState:
    assert state.turn is not None
    order = list(state.players.keys())
    idx = order.index(state.turn.current_player)
    next_player = order[(idx + 1) % len(order)]
    next_turn = replace(state.turn, current_player=next_player, step=TurnStep.ROLL, last_roll=None)
    return replace(state, turn=next_turn)


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
