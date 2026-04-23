from __future__ import annotations

from dataclasses import replace

from .models.action import (
    Action,
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    BuyDevelopmentCard,
    ChooseMonopolyResource,
    PlayKnightCard,
    PlayMonopolyCard,
    PlayRoadBuildingCard,
    PlayYearOfPlentyCard,
    ChooseYearOfPlentyResources,
    FinishRoadBuildingCard,
    DiscardResources,
    EndTurn,
    MoveRobber,
    ChooseTradePartner,
    ProposePlayerTrade,
    RejectTradeResponses,
    RespondToTradeInterested,
    RespondToTradePass,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    RollDice,
    SkipSteal,
    StealResource,
)
from .models.board import EdgeId, NodeId, PlayerId, TileId
from .models.enums import DevelopmentCardType, GamePhase, PlayerTradePhase, ResourceType, TerrainType, TurnStep
from .models.state import DevCardFlowState, GameState, InitialGameConfig, PlacedPieces, PlayerState, PlayerTradeState, SetupState, TurnState
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
DEVELOPMENT_CARD_COST = {
    ResourceType.ORE: 1,
    ResourceType.GRAIN: 1,
    ResourceType.WOOL: 1,
}
BANK_TRADE_RATE = 4

TERRAIN_TO_RESOURCE = {
    TerrainType.HILLS: ResourceType.BRICK,
    TerrainType.FOREST: ResourceType.LUMBER,
    TerrainType.PASTURE: ResourceType.WOOL,
    TerrainType.FIELDS: ResourceType.GRAIN,
    TerrainType.MOUNTAINS: ResourceType.ORE,
}


DEVELOPMENT_CARD_DISTRIBUTION = {
    DevelopmentCardType.KNIGHT: 14,
    DevelopmentCardType.VICTORY_POINT: 5,
    DevelopmentCardType.ROAD_BUILDING: 2,
    DevelopmentCardType.YEAR_OF_PLENTY: 2,
    DevelopmentCardType.MONOPOLY: 2,
}


def create_initial_state(config: InitialGameConfig) -> GameState:
    players: dict[PlayerId, PlayerState] = {}
    for player_id in config.player_ids:
        players[player_id] = PlayerState(
            player_id=player_id,
            resources={resource: 0 for resource in ResourceType},
        )

    robber_tile_id = next((tile.id for tile in config.board.tiles if tile.terrain == TerrainType.DESERT), None)

    dev_deck, shuffled_rng = _build_and_shuffle_dev_deck(config.seed)
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
        rng_state=shuffled_rng,
        robber_tile_id=robber_tile_id,
        dev_deck=dev_deck,
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

    if state.player_trade is not None:
        return _get_player_trade_legal_actions(state, player_id)

    if state.turn.step == TurnStep.ROLL:
        legal_actions: list[Action] = [RollDice(player_id=player_id)]
        if _can_play_knight_card(state, player_id):
            legal_actions.append(PlayKnightCard(player_id=player_id))
        return legal_actions
    if state.turn.step == TurnStep.ROBBER_MOVE:
        return [MoveRobber(player_id=player_id, tile_id=tile.id) for tile in state.board.tiles if tile.id != state.robber_tile_id]
    if state.turn.step == TurnStep.ROBBER_STEAL:
        return [StealResource(player_id=player_id, target_player_id=target) for target in _eligible_robber_targets(state, player_id)]
    if state.turn.step == TurnStep.ROAD_BUILDING:
        legal_actions = [BuildRoad(player_id=player_id, edge_id=edge_id) for edge_id in _legal_road_edges(state, player_id, require_resources=False)]
        legal_actions.append(FinishRoadBuildingCard(player_id=player_id))
        return legal_actions
    if state.turn.step == TurnStep.YEAR_OF_PLENTY:
        legal_actions: list[Action] = []
        for first in ResourceType:
            for second in ResourceType:
                legal_actions.append(
                    ChooseYearOfPlentyResources(
                        player_id=player_id,
                        first_resource=first,
                        second_resource=second,
                    )
                )
        return legal_actions
    if state.turn.step == TurnStep.MONOPOLY:
        return [ChooseMonopolyResource(player_id=player_id, resource=resource) for resource in ResourceType]

    legal_actions: list[Action] = [EndTurn(player_id=player_id)]
    legal_actions.extend(BuildRoad(player_id=player_id, edge_id=edge_id) for edge_id in _legal_road_edges(state, player_id))
    legal_actions.extend(
        BuildSettlement(player_id=player_id, node_id=node_id) for node_id in _legal_settlement_nodes_main(state, player_id)
    )
    legal_actions.extend(BuildCity(player_id=player_id, node_id=node_id) for node_id in _legal_city_nodes(state, player_id))
    if _can_buy_development_card(state, player_id):
        legal_actions.append(BuyDevelopmentCard(player_id=player_id))
    if _can_play_knight_card(state, player_id):
        legal_actions.append(PlayKnightCard(player_id=player_id))
    if _can_play_dev_card(state, player_id, DevelopmentCardType.ROAD_BUILDING):
        legal_actions.append(PlayRoadBuildingCard(player_id=player_id))
    if _can_play_dev_card(state, player_id, DevelopmentCardType.YEAR_OF_PLENTY):
        legal_actions.append(PlayYearOfPlentyCard(player_id=player_id))
    if _can_play_dev_card(state, player_id, DevelopmentCardType.MONOPOLY):
        legal_actions.append(PlayMonopolyCard(player_id=player_id))
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
        return replace(
            state,
            turn=replace(state.turn, step=_next_step_after_robber_resolution(state), priority_player=None),
            robber_source=None,
        )
    if isinstance(action, BuildRoad):
        return _apply_build_road(state, action)
    if isinstance(action, BuildSettlement):
        return _apply_build_settlement(state, action)
    if isinstance(action, BuildCity):
        return _apply_build_city(state, action)
    if isinstance(action, BuyDevelopmentCard):
        return _apply_buy_development_card(state, action)
    if isinstance(action, PlayKnightCard):
        return _apply_play_knight_card(state, action)
    if isinstance(action, PlayRoadBuildingCard):
        return _apply_play_road_building_card(state, action)
    if isinstance(action, FinishRoadBuildingCard):
        return _apply_finish_road_building_card(state, action)
    if isinstance(action, PlayYearOfPlentyCard):
        return _apply_play_year_of_plenty_card(state, action)
    if isinstance(action, ChooseYearOfPlentyResources):
        return _apply_choose_year_of_plenty_resources(state, action)
    if isinstance(action, PlayMonopolyCard):
        return _apply_play_monopoly_card(state, action)
    if isinstance(action, ChooseMonopolyResource):
        return _apply_choose_monopoly_resource(state, action)
    if isinstance(action, BankTrade):
        return _apply_bank_trade(state, action)
    if isinstance(action, ProposePlayerTrade):
        return _apply_propose_player_trade(state, action)
    if isinstance(action, RespondToTradeInterested):
        return _apply_respond_to_trade(state, action, interested=True)
    if isinstance(action, RespondToTradePass):
        return _apply_respond_to_trade(state, action, interested=False)
    if isinstance(action, ChooseTradePartner):
        return _apply_choose_trade_partner(state, action)
    if isinstance(action, RejectTradeResponses):
        return _apply_reject_trade_responses(state, action)
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
            dev_card_count=sum(pstate.dev_cards.values()),
            knights_played=pstate.knights_played,
            longest_road_length=pstate.longest_road_length,
            has_largest_army=state.largest_army_holder == pid,
            has_longest_road=state.longest_road_holder == pid,
        )
        for pid, pstate in state.players.items()
    )
    own_dev_cards = {card_type.name: count for card_type, count in own.dev_cards.items()}

    return PlayerObservation(
        requesting_player_id=player_id,
        current_player_id=state.turn.current_player if state.turn else None,
        phase=state.phase.name,
        own_resources=own_resources,
        own_dev_cards=own_dev_cards,
        own_total_victory_points=_total_victory_points(state, player_id),
        dev_deck_remaining=len(state.dev_deck),
        players_public=players_public,
    )


def _is_legal_action(state: GameState, action: Action) -> bool:
    if isinstance(action, ProposePlayerTrade):
        return _is_legal_propose_player_trade(state, action)
    if isinstance(action, RespondToTradeInterested):
        return _is_legal_trade_response(state, action.player_id)
    if isinstance(action, RespondToTradePass):
        return _is_legal_trade_response(state, action.player_id)
    if isinstance(action, ChooseTradePartner):
        return _is_legal_choose_trade_partner(state, action)
    if isinstance(action, RejectTradeResponses):
        return _is_legal_reject_trade_responses(state, action)
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


def _legal_road_edges(state: GameState, player_id: PlayerId, *, require_resources: bool = True) -> list[EdgeId]:
    player = state.players[player_id]
    if player.roads_left <= 0:
        return []
    if require_resources and not _has_resources(player, ROAD_COST):
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
        trade_rate, via_port_resource = _best_trade_rate_for_offer(state, player_id, offer_resource)
        if amount < trade_rate:
            continue
        for request_resource in ResourceType:
            if request_resource == offer_resource:
                continue
            actions.append(
                BankTrade(
                    player_id=player_id,
                    offer_resource=offer_resource,
                    request_resource=request_resource,
                    trade_rate=trade_rate,
                    via_port_resource=via_port_resource,
                )
            )
    return actions


def _get_player_trade_legal_actions(state: GameState, player_id: PlayerId) -> list[Action]:
    trade = state.player_trade
    if trade is None:
        return []
    if trade.phase == PlayerTradePhase.RESPONSES:
        return [RespondToTradeInterested(player_id=player_id), RespondToTradePass(player_id=player_id)]
    if trade.phase == PlayerTradePhase.PARTNER_SELECTION:
        actions: list[Action] = [RejectTradeResponses(player_id=player_id)]
        actions.extend(ChooseTradePartner(player_id=player_id, partner_player_id=pid) for pid in trade.interested_responders)
        return actions
    return []


def _is_legal_propose_player_trade(state: GameState, action: ProposePlayerTrade) -> bool:
    if state.turn is None or state.turn.step != TurnStep.ACTIONS or state.player_trade is not None:
        return False
    if action.player_id != state.turn.current_player:
        return False
    offered = _bundle_to_dict(action.offered_resources)
    requested = _bundle_to_dict(action.requested_resources)
    if not _is_valid_bundle(offered) or not _is_valid_bundle(requested):
        return False
    return _player_has_bundle(state.players[action.player_id], offered)


def _is_legal_trade_response(state: GameState, player_id: PlayerId) -> bool:
    trade = state.player_trade
    if state.turn is None or trade is None or state.turn.step != TurnStep.PLAYER_TRADE:
        return False
    if trade.phase != PlayerTradePhase.RESPONSES:
        return False
    if state.turn.priority_player != player_id:
        return False
    return player_id in trade.eligible_responders


def _is_legal_choose_trade_partner(state: GameState, action: ChooseTradePartner) -> bool:
    trade = state.player_trade
    if state.turn is None or trade is None or state.turn.step != TurnStep.PLAYER_TRADE:
        return False
    if trade.phase != PlayerTradePhase.PARTNER_SELECTION:
        return False
    if action.player_id != trade.proposer_player_id or state.turn.priority_player != trade.proposer_player_id:
        return False
    if action.partner_player_id not in trade.interested_responders:
        return False
    proposer_bundle = _bundle_to_dict(trade.offered_resources)
    requested_bundle = _bundle_to_dict(trade.requested_resources)
    return _player_has_bundle(state.players[action.player_id], proposer_bundle) and _player_has_bundle(state.players[action.partner_player_id], requested_bundle)


def _is_legal_reject_trade_responses(state: GameState, action: RejectTradeResponses) -> bool:
    trade = state.player_trade
    if state.turn is None or trade is None or state.turn.step != TurnStep.PLAYER_TRADE:
        return False
    return trade.phase == PlayerTradePhase.PARTNER_SELECTION and action.player_id == trade.proposer_player_id


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
    next_state = _recompute_longest_road_state(next_state)
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
        return replace(
            moved_state,
            turn=replace(state.turn, step=_next_step_after_robber_resolution(state), priority_player=None),
            robber_source=None,
        )
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
        return replace(
            state,
            turn=replace(state.turn, step=_next_step_after_robber_resolution(state), priority_player=None),
            robber_source=None,
        )

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
        turn=replace(state.turn, step=_next_step_after_robber_resolution(state), priority_player=None),
        robber_source=None,
    )


def _next_step_after_robber_resolution(state: GameState) -> TurnStep:
    if (
        state.robber_source == "knight"
        and state.turn is not None
        and state.turn.last_roll is None
    ):
        return TurnStep.ROLL
    return TurnStep.ACTIONS


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
    is_free_road = (
        state.dev_card_flow is not None
        and state.dev_card_flow.card_type == DevelopmentCardType.ROAD_BUILDING
        and state.turn is not None
        and state.turn.step == TurnStep.ROAD_BUILDING
    )
    player = state.players[action.player_id] if is_free_road else _pay_cost(state.players[action.player_id], ROAD_COST)
    roads = {**state.placed.roads, action.edge_id: action.player_id}
    updated_player = replace(player, roads_left=player.roads_left - 1)
    next_state = replace(
        state,
        players={**state.players, action.player_id: updated_player},
        placed=replace(state.placed, roads=roads),
    )
    if is_free_road and next_state.dev_card_flow is not None:
        flow = next_state.dev_card_flow
        remaining = max(flow.roads_remaining - 1, 0)
        placed = flow.roads_placed + 1
        if remaining <= 0:
            next_state = replace(
                next_state,
                turn=replace(next_state.turn, step=TurnStep.ACTIONS, priority_player=None),
                dev_card_flow=None,
            )
        else:
            next_state = replace(next_state, dev_card_flow=replace(flow, roads_remaining=remaining, roads_placed=placed))
            if not _legal_road_edges(next_state, action.player_id, require_resources=False):
                next_state = replace(
                    next_state,
                    turn=replace(next_state.turn, step=TurnStep.ACTIONS, priority_player=None),
                    dev_card_flow=None,
                )
    next_state = _recompute_longest_road_state(next_state)
    return _update_winner(next_state, action.player_id)


def _apply_build_settlement(state: GameState, action: BuildSettlement) -> GameState:
    player = _pay_cost(state.players[action.player_id], SETTLEMENT_COST)
    settlements = {**state.placed.settlements, action.node_id: action.player_id}
    next_state = replace(
        state,
        players={**state.players, action.player_id: replace(player, settlements_left=player.settlements_left - 1, victory_points=player.victory_points + 1)},
        placed=replace(state.placed, settlements=settlements),
    )
    next_state = _recompute_longest_road_state(next_state)
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
    next_state = _recompute_longest_road_state(next_state)
    return _update_winner(next_state, action.player_id)


def _apply_buy_development_card(state: GameState, action: BuyDevelopmentCard) -> GameState:
    player = _pay_cost(state.players[action.player_id], DEVELOPMENT_CARD_COST)
    drawn_card = state.dev_deck[0]
    remaining_deck = state.dev_deck[1:]
    dev_cards = dict(player.dev_cards)
    dev_cards[drawn_card] += 1
    new_dev_cards = dict(player.new_dev_cards)
    new_dev_cards[drawn_card] += 1
    updated_player = replace(player, dev_cards=dev_cards, new_dev_cards=new_dev_cards)
    next_state = replace(
        state,
        players={**state.players, action.player_id: updated_player},
        dev_deck=remaining_deck,
    )
    return _update_winner(next_state, action.player_id)


def _apply_play_knight_card(state: GameState, action: PlayKnightCard) -> GameState:
    player = state.players[action.player_id]
    dev_cards = dict(player.dev_cards)
    dev_cards[DevelopmentCardType.KNIGHT] -= 1
    updated_player = replace(player, dev_cards=dev_cards, knights_played=player.knights_played + 1)
    next_state = replace(
        state,
        players={**state.players, action.player_id: updated_player},
        turn=replace(
            state.turn,
            step=TurnStep.ROBBER_MOVE,
            priority_player=action.player_id,
            dev_card_played_this_turn=True,
        ),
        robber_source="knight",
    )
    next_state = _recompute_largest_army_state(next_state)
    return _update_winner(next_state, action.player_id)


def _apply_play_road_building_card(state: GameState, action: PlayRoadBuildingCard) -> GameState:
    player = state.players[action.player_id]
    dev_cards = dict(player.dev_cards)
    dev_cards[DevelopmentCardType.ROAD_BUILDING] -= 1
    updated_player = replace(player, dev_cards=dev_cards)
    flow = DevCardFlowState(card_type=DevelopmentCardType.ROAD_BUILDING, roads_remaining=2, roads_placed=0)
    next_state = replace(
        state,
        players={**state.players, action.player_id: updated_player},
        turn=replace(
            state.turn,
            step=TurnStep.ROAD_BUILDING,
            priority_player=action.player_id,
            dev_card_played_this_turn=True,
        ),
        dev_card_flow=flow,
    )
    if not _legal_road_edges(next_state, action.player_id, require_resources=False):
        return replace(
            next_state,
            turn=replace(next_state.turn, step=TurnStep.ACTIONS, priority_player=None),
            dev_card_flow=None,
        )
    return next_state


def _apply_finish_road_building_card(state: GameState, action: FinishRoadBuildingCard) -> GameState:
    return replace(
        state,
        turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None),
        dev_card_flow=None,
    )


def _apply_play_year_of_plenty_card(state: GameState, action: PlayYearOfPlentyCard) -> GameState:
    player = state.players[action.player_id]
    dev_cards = dict(player.dev_cards)
    dev_cards[DevelopmentCardType.YEAR_OF_PLENTY] -= 1
    updated_player = replace(player, dev_cards=dev_cards)
    return replace(
        state,
        players={**state.players, action.player_id: updated_player},
        turn=replace(
            state.turn,
            step=TurnStep.YEAR_OF_PLENTY,
            priority_player=action.player_id,
            dev_card_played_this_turn=True,
        ),
        dev_card_flow=DevCardFlowState(card_type=DevelopmentCardType.YEAR_OF_PLENTY),
    )


def _apply_choose_year_of_plenty_resources(state: GameState, action: ChooseYearOfPlentyResources) -> GameState:
    player = state.players[action.player_id]
    resources = dict(player.resources)
    resources[action.first_resource] += 1
    resources[action.second_resource] += 1
    return replace(
        state,
        players={**state.players, action.player_id: replace(player, resources=resources)},
        turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None),
        dev_card_flow=None,
    )


def _apply_play_monopoly_card(state: GameState, action: PlayMonopolyCard) -> GameState:
    player = state.players[action.player_id]
    dev_cards = dict(player.dev_cards)
    dev_cards[DevelopmentCardType.MONOPOLY] -= 1
    updated_player = replace(player, dev_cards=dev_cards)
    return replace(
        state,
        players={**state.players, action.player_id: updated_player},
        turn=replace(
            state.turn,
            step=TurnStep.MONOPOLY,
            priority_player=action.player_id,
            dev_card_played_this_turn=True,
        ),
        dev_card_flow=DevCardFlowState(card_type=DevelopmentCardType.MONOPOLY),
    )


def _apply_choose_monopoly_resource(state: GameState, action: ChooseMonopolyResource) -> GameState:
    players = dict(state.players)
    collector = players[action.player_id]
    total_collected = 0
    for player_id, player in state.players.items():
        if player_id == action.player_id:
            continue
        amount = player.resources.get(action.resource, 0)
        if amount <= 0:
            continue
        total_collected += amount
        next_res = dict(player.resources)
        next_res[action.resource] = 0
        players[player_id] = replace(player, resources=next_res)
    collector_res = dict(collector.resources)
    collector_res[action.resource] += total_collected
    players[action.player_id] = replace(collector, resources=collector_res)
    return replace(
        state,
        players=players,
        turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None),
        dev_card_flow=None,
    )


def _apply_bank_trade(state: GameState, action: BankTrade) -> GameState:
    player = state.players[action.player_id]
    resources = dict(player.resources)
    resources[action.offer_resource] -= action.trade_rate
    resources[action.request_resource] += 1
    return replace(state, players={**state.players, action.player_id: replace(player, resources=resources)})


def _apply_propose_player_trade(state: GameState, action: ProposePlayerTrade) -> GameState:
    order = _player_order_after(state, action.player_id)
    requested_bundle = _bundle_to_dict(action.requested_resources)
    eligible = tuple(pid for pid in order if _player_has_bundle(state.players[pid], requested_bundle))
    trade = PlayerTradeState(
        proposer_player_id=action.player_id,
        offered_resources=_normalize_bundle(action.offered_resources),
        requested_resources=_normalize_bundle(action.requested_resources),
        responder_order=tuple(order),
        current_responder_index=0,
        eligible_responders=eligible,
        interested_responders=tuple(),
        phase=PlayerTradePhase.RESPONSES,
    )
    return _advance_trade_flow(replace(state, player_trade=trade, turn=replace(state.turn, step=TurnStep.PLAYER_TRADE)))


def _apply_respond_to_trade(state: GameState, action: RespondToTradeInterested | RespondToTradePass, *, interested: bool) -> GameState:
    trade = state.player_trade
    if trade is None:
        return state
    interested_responders = trade.interested_responders
    if interested:
        interested_responders = (*interested_responders, action.player_id)
    next_trade = replace(trade, current_responder_index=trade.current_responder_index + 1, interested_responders=interested_responders)
    return _advance_trade_flow(replace(state, player_trade=next_trade))


def _apply_choose_trade_partner(state: GameState, action: ChooseTradePartner) -> GameState:
    trade = state.player_trade
    if trade is None:
        return state
    proposer_bundle = _bundle_to_dict(trade.offered_resources)
    requested_bundle = _bundle_to_dict(trade.requested_resources)
    proposer = _apply_resource_bundle_delta(state.players[action.player_id], proposer_bundle, requested_bundle)
    partner = _apply_resource_bundle_delta(state.players[action.partner_player_id], requested_bundle, proposer_bundle)
    return replace(
        state,
        players={
            **state.players,
            action.player_id: proposer,
            action.partner_player_id: partner,
        },
        player_trade=None,
        turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None),
    )


def _apply_reject_trade_responses(state: GameState, action: RejectTradeResponses) -> GameState:
    return replace(state, player_trade=None, turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None))


def _advance_trade_flow(state: GameState) -> GameState:
    trade = state.player_trade
    if trade is None:
        return state
    next_index = trade.current_responder_index
    while next_index < len(trade.responder_order) and trade.responder_order[next_index] not in trade.eligible_responders:
        next_index += 1
    trade = replace(trade, current_responder_index=next_index)
    if next_index >= len(trade.responder_order):
        if trade.interested_responders:
            return replace(
                state,
                player_trade=replace(trade, phase=PlayerTradePhase.PARTNER_SELECTION),
                turn=replace(state.turn, step=TurnStep.PLAYER_TRADE, priority_player=trade.proposer_player_id),
            )
        return replace(state, player_trade=None, turn=replace(state.turn, step=TurnStep.ACTIONS, priority_player=None))
    responder = trade.responder_order[next_index]
    return replace(state, player_trade=trade, turn=replace(state.turn, step=TurnStep.PLAYER_TRADE, priority_player=responder))


def _best_trade_rate_for_offer(
    state: GameState, player_id: PlayerId, offer_resource: ResourceType
) -> tuple[int, ResourceType | None]:
    accessible_ports = _accessible_ports(state, player_id)
    has_generic = any(port.trade_resource is None for port in accessible_ports)
    has_specific = any(port.trade_resource == offer_resource for port in accessible_ports)
    if has_specific:
        return 2, offer_resource
    if has_generic:
        return 3, None
    return BANK_TRADE_RATE, None


def _bundle_to_dict(bundle: tuple[tuple[ResourceType, int], ...]) -> dict[ResourceType, int]:
    result = {resource: 0 for resource in ResourceType}
    for resource, amount in bundle:
        result[resource] += amount
    return result


def _normalize_bundle(bundle: tuple[tuple[ResourceType, int], ...]) -> tuple[tuple[ResourceType, int], ...]:
    merged = _bundle_to_dict(bundle)
    return tuple((resource, amount) for resource, amount in merged.items() if amount > 0)


def _is_valid_bundle(bundle: dict[ResourceType, int]) -> bool:
    return sum(bundle.values()) > 0 and all(amount >= 0 for amount in bundle.values())


def _player_has_bundle(player: PlayerState, bundle: dict[ResourceType, int]) -> bool:
    return all(player.resources.get(resource, 0) >= amount for resource, amount in bundle.items())


def _apply_resource_bundle_delta(player: PlayerState, pay_bundle: dict[ResourceType, int], gain_bundle: dict[ResourceType, int]) -> PlayerState:
    resources = dict(player.resources)
    for resource, amount in pay_bundle.items():
        resources[resource] -= amount
    for resource, amount in gain_bundle.items():
        resources[resource] += amount
    return replace(player, resources=resources)


def _player_order_after(state: GameState, proposer_id: PlayerId) -> list[PlayerId]:
    order = sorted(state.players.keys())
    idx = order.index(proposer_id)
    rotated = order[idx + 1 :] + order[:idx]
    return rotated


def _accessible_ports(state: GameState, player_id: PlayerId):
    owned_nodes = {
        node_id
        for node_id, owner in state.placed.settlements.items()
        if owner == player_id
    }
    owned_nodes.update(
        node_id
        for node_id, owner in state.placed.cities.items()
        if owner == player_id
    )
    port_ids: set[int] = set()
    for node_id in owned_nodes:
        port_ids.update(state.board.node_to_ports.get(node_id, ()))
    return [state.board.ports[port_id] for port_id in sorted(port_ids)]


def _apply_end_turn(state: GameState) -> GameState:
    current_player = state.turn.current_player
    current = state.players[current_player]
    reset_new = {card_type: 0 for card_type in DevelopmentCardType}
    updated_current = replace(current, new_dev_cards=reset_new)
    order = list(state.players.keys())
    idx = order.index(current_player)
    next_player = order[(idx + 1) % len(order)]
    return replace(
        state,
        players={**state.players, current_player: updated_current},
        turn=replace(
            state.turn,
            current_player=next_player,
            step=TurnStep.ROLL,
            last_roll=None,
            priority_player=None,
            dev_card_played_this_turn=False,
        ),
        robber_source=None,
    )


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
    for pid in sorted(state.players):
        if _total_victory_points(state, pid) >= 10:
            return replace(state, winner=pid, phase=GamePhase.GAME_OVER)
    return state


def _can_buy_development_card(state: GameState, player_id: PlayerId) -> bool:
    if state.turn is None or state.turn.step != TurnStep.ACTIONS:
        return False
    if state.turn.current_player != player_id:
        return False
    if not state.dev_deck:
        return False
    return _has_resources(state.players[player_id], DEVELOPMENT_CARD_COST)


def _can_play_knight_card(state: GameState, player_id: PlayerId) -> bool:
    if state.turn is None or state.turn.step not in (TurnStep.ROLL, TurnStep.ACTIONS):
        return False
    if state.turn.current_player != player_id:
        return False
    if state.turn.dev_card_played_this_turn:
        return False
    player = state.players[player_id]
    playable_knights = player.dev_cards.get(DevelopmentCardType.KNIGHT, 0) - player.new_dev_cards.get(DevelopmentCardType.KNIGHT, 0)
    return playable_knights > 0


def _can_play_dev_card(state: GameState, player_id: PlayerId, card_type: DevelopmentCardType) -> bool:
    if state.turn is None or state.turn.step != TurnStep.ACTIONS:
        return False
    if state.turn.current_player != player_id:
        return False
    if state.turn.dev_card_played_this_turn:
        return False
    player = state.players[player_id]
    playable = player.dev_cards.get(card_type, 0) - player.new_dev_cards.get(card_type, 0)
    return playable > 0


def _total_victory_points(state: GameState, player_id: PlayerId) -> int:
    player = state.players[player_id]
    total = player.victory_points + player.dev_cards.get(DevelopmentCardType.VICTORY_POINT, 0)
    if state.largest_army_holder == player_id:
        total += 2
    if state.longest_road_holder == player_id:
        total += 2
    return total


def _recompute_largest_army_state(state: GameState) -> GameState:
    counts = {pid: player.knights_played for pid, player in state.players.items()}
    holder = _recompute_award_holder(counts, state.largest_army_holder, minimum=3)
    return replace(state, largest_army_holder=holder)


def _recompute_longest_road_state(state: GameState) -> GameState:
    players = dict(state.players)
    lengths: dict[PlayerId, int] = {}
    for pid, player in state.players.items():
        length = _calculate_longest_road_length(state, pid)
        lengths[pid] = length
        players[pid] = replace(player, longest_road_length=length)
    holder = _recompute_award_holder(lengths, state.longest_road_holder, minimum=5)
    return replace(state, players=players, longest_road_holder=holder)


def _recompute_award_holder(counts: dict[PlayerId, int], current_holder: PlayerId | None, *, minimum: int) -> PlayerId | None:
    if current_holder is None:
        max_count = max(counts.values(), default=0)
        if max_count < minimum:
            return None
        leaders = [pid for pid, count in counts.items() if count == max_count]
        return leaders[0] if len(leaders) == 1 else None

    current_count = counts.get(current_holder, 0)
    if current_count < minimum:
        max_count = max(counts.values(), default=0)
        if max_count < minimum:
            return None
        leaders = [pid for pid, count in counts.items() if count == max_count]
        return leaders[0] if len(leaders) == 1 else None

    better = [(pid, count) for pid, count in counts.items() if pid != current_holder and count > current_count]
    if not better:
        return current_holder
    best_count = max(count for _, count in better)
    leaders = [pid for pid, count in better if count == best_count]
    return leaders[0] if len(leaders) == 1 else current_holder


def _calculate_longest_road_length(state: GameState, player_id: PlayerId) -> int:
    owned_edges = [edge_id for edge_id, owner in state.placed.roads.items() if owner == player_id]
    if not owned_edges:
        return 0
    node_to_edges: dict[NodeId, list[EdgeId]] = {}
    for edge_id in owned_edges:
        a, b = state.board.edge_to_adjacent_nodes[edge_id]
        node_to_edges.setdefault(a, []).append(edge_id)
        node_to_edges.setdefault(b, []).append(edge_id)

    def can_transit(node_id: NodeId) -> bool:
        owner = state.placed.cities.get(node_id) or state.placed.settlements.get(node_id)
        return owner is None or owner == player_id

    def dfs_from_node(node_id: NodeId, used_edges: frozenset[EdgeId]) -> int:
        if not can_transit(node_id):
            return 0
        best = 0
        for next_edge in node_to_edges.get(node_id, []):
            if next_edge in used_edges:
                continue
            a, b = state.board.edge_to_adjacent_nodes[next_edge]
            next_node = b if a == node_id else a
            best = max(best, 1 + dfs_from_node(next_node, used_edges | {next_edge}))
        return best

    longest = 0
    for edge_id in owned_edges:
        a, b = state.board.edge_to_adjacent_nodes[edge_id]
        longest = max(longest, 1 + dfs_from_node(a, frozenset({edge_id})))
        longest = max(longest, 1 + dfs_from_node(b, frozenset({edge_id})))
    return longest


def _build_and_shuffle_dev_deck(seed: int) -> tuple[tuple[DevelopmentCardType, ...], int]:
    deck: list[DevelopmentCardType] = []
    for card_type, amount in DEVELOPMENT_CARD_DISTRIBUTION.items():
        deck.extend([card_type] * amount)
    rng_state = seed
    for index in range(len(deck) - 1, 0, -1):
        value, rng_state = next_u32(rng_state)
        swap_index = value % (index + 1)
        deck[index], deck[swap_index] = deck[swap_index], deck[index]
    return tuple(deck), rng_state
