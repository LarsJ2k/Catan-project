from __future__ import annotations

from dataclasses import replace

from catan.core.engine import apply_action, create_initial_state, get_legal_actions, get_observation
from catan.core.models.action import BuyDevelopmentCard, MoveRobber, PlayKnightCard, StealResource
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, InitialGameConfig, PlacedPieces, PlayerState, SetupState, TurnState


def make_board() -> Board:
    return Board(
        nodes=(0, 1),
        edges=(Edge(id=0, node_a=0, node_b=1),),
        tiles=(Tile(id=0, terrain=TerrainType.FIELDS, number_token=8),),
        node_to_adjacent_tiles={0: (0,), 1: (0,)},
        node_to_adjacent_edges={0: (0,), 1: (0,)},
        edge_to_adjacent_nodes={0: (0, 1)},
        ports=(),
        node_to_ports={0: (), 1: ()},
    )


def make_main_turn_state() -> GameState:
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}),
        2: PlayerState(player_id=2, resources={r: 0 for r in ResourceType}),
    }
    return GameState(
        board=make_board(),
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        rng_state=1,
        dev_deck=(),
    )


def test_initial_dev_deck_composition_is_standard_25_cards() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=7))
    counts = {card_type: state.dev_deck.count(card_type) for card_type in DevelopmentCardType}
    assert len(state.dev_deck) == 25
    assert counts[DevelopmentCardType.KNIGHT] == 14
    assert counts[DevelopmentCardType.VICTORY_POINT] == 5
    assert counts[DevelopmentCardType.ROAD_BUILDING] == 2
    assert counts[DevelopmentCardType.YEAR_OF_PLENTY] == 2
    assert counts[DevelopmentCardType.MONOPOLY] == 2


def test_initial_dev_deck_shuffle_is_deterministic_for_seed() -> None:
    state_a = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=999))
    state_b = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=999))
    state_c = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=1000))
    assert state_a.dev_deck == state_b.dev_deck
    assert state_a.dev_deck != state_c.dev_deck


def test_buy_dev_card_consumes_resources_and_draws_top_card() -> None:
    state = make_main_turn_state()
    top = DevelopmentCardType.KNIGHT
    state = replace(
        state,
        dev_deck=(top, DevelopmentCardType.MONOPOLY),
        players={
            1: replace(
                state.players[1],
                resources={
                    **state.players[1].resources,
                    ResourceType.GRAIN: 1,
                    ResourceType.WOOL: 1,
                    ResourceType.ORE: 1,
                },
            ),
            2: state.players[2],
        },
    )

    action = BuyDevelopmentCard(player_id=1)
    assert action in get_legal_actions(state, 1)
    after = apply_action(state, action)
    assert after.players[1].resources[ResourceType.GRAIN] == 0
    assert after.players[1].resources[ResourceType.WOOL] == 0
    assert after.players[1].resources[ResourceType.ORE] == 0
    assert after.players[1].dev_cards[top] == 1
    assert after.dev_deck == (DevelopmentCardType.MONOPOLY,)


def test_cannot_buy_dev_card_without_resources_or_when_deck_empty() -> None:
    state = make_main_turn_state()
    state = replace(state, dev_deck=(DevelopmentCardType.KNIGHT,))
    assert BuyDevelopmentCard(player_id=1) not in get_legal_actions(state, 1)

    resourced = replace(
        state,
        players={
            1: replace(
                state.players[1],
                resources={
                    **state.players[1].resources,
                    ResourceType.GRAIN: 1,
                    ResourceType.WOOL: 1,
                    ResourceType.ORE: 1,
                },
            ),
            2: state.players[2],
        },
        dev_deck=(),
    )
    assert BuyDevelopmentCard(player_id=1) not in get_legal_actions(resourced, 1)


def test_victory_point_dev_card_counts_toward_actual_win() -> None:
    state = make_main_turn_state()
    state = replace(
        state,
        dev_deck=(DevelopmentCardType.VICTORY_POINT,),
        players={
            1: replace(
                state.players[1],
                victory_points=9,
                resources={
                    **state.players[1].resources,
                    ResourceType.GRAIN: 1,
                    ResourceType.WOOL: 1,
                    ResourceType.ORE: 1,
                },
            ),
            2: state.players[2],
        },
    )
    after = apply_action(state, BuyDevelopmentCard(player_id=1))
    assert after.winner == 1
    assert after.phase == GamePhase.GAME_OVER


def test_player_observation_hides_opponent_dev_card_types() -> None:
    state = make_main_turn_state()
    p1_cards = {card_type: 0 for card_type in DevelopmentCardType}
    p1_cards[DevelopmentCardType.KNIGHT] = 1
    p1_cards[DevelopmentCardType.VICTORY_POINT] = 2
    p2_cards = {card_type: 0 for card_type in DevelopmentCardType}
    p2_cards[DevelopmentCardType.MONOPOLY] = 2
    state = replace(
        state,
        dev_deck=(DevelopmentCardType.ROAD_BUILDING,),
        players={
            1: replace(state.players[1], dev_cards=p1_cards),
            2: replace(state.players[2], dev_cards=p2_cards),
        },
    )

    obs = get_observation(state, 1, debug=False)
    assert obs.own_dev_cards["KNIGHT"] == 1
    assert obs.own_dev_cards["VICTORY_POINT"] == 2
    p2_public = next(view for view in obs.players_public if view.player_id == 2)
    assert p2_public.dev_card_count == 2


def test_buying_dev_cards_is_deterministic_with_same_seed_and_actions() -> None:
    a = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=1234))
    b = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=make_board(), seed=1234))

    def prep(state: GameState) -> GameState:
        return replace(
            state,
            phase=GamePhase.MAIN_TURN,
            setup=SetupState(order=[1, 2]),
            turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
            players={
                1: replace(
                    state.players[1],
                    resources={resource: 3 for resource in ResourceType},
                ),
                2: state.players[2],
            },
        )

    a = prep(a)
    b = prep(b)
    for _ in range(2):
        a = apply_action(a, BuyDevelopmentCard(player_id=1))
        b = apply_action(b, BuyDevelopmentCard(player_id=1))
    assert a == b


def test_knight_play_requires_owned_and_playable_knight() -> None:
    state = make_main_turn_state()
    assert PlayKnightCard(player_id=1) not in get_legal_actions(state, 1)

    cards = {card_type: 0 for card_type in DevelopmentCardType}
    cards[DevelopmentCardType.KNIGHT] = 1
    fresh = {card_type: 0 for card_type in DevelopmentCardType}
    fresh[DevelopmentCardType.KNIGHT] = 1
    state = replace(state, players={1: replace(state.players[1], dev_cards=cards, new_dev_cards=fresh), 2: state.players[2]})
    assert PlayKnightCard(player_id=1) not in get_legal_actions(state, 1)

    state = replace(state, players={1: replace(state.players[1], new_dev_cards={card_type: 0 for card_type in DevelopmentCardType}), 2: state.players[2]})
    assert PlayKnightCard(player_id=1) in get_legal_actions(state, 1)


def test_knight_moves_robber_without_discard_and_steal_flow_matches_rules() -> None:
    board = Board(
        nodes=(0, 1, 2),
        edges=(Edge(id=0, node_a=0, node_b=1),),
        tiles=(Tile(id=0, terrain=TerrainType.FIELDS, number_token=8), Tile(id=1, terrain=TerrainType.FOREST, number_token=5)),
        node_to_adjacent_tiles={0: (0,), 1: (0,), 2: (1,)},
        node_to_adjacent_edges={0: (0,), 1: (0,), 2: ()},
        edge_to_adjacent_nodes={0: (0, 1)},
        tile_to_nodes={0: (0, 1), 1: (2,)},
        ports=(),
        node_to_ports={0: (), 1: (), 2: ()},
    )
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}),
        2: PlayerState(player_id=2, resources={r: 1 for r in ResourceType}),
        3: PlayerState(player_id=3, resources={r: 1 for r in ResourceType}),
    }
    state = GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(settlements={0: 2, 1: 3}, roads={}, cities={}),
        rng_state=9,
        robber_tile_id=1,
    )
    cards = {card_type: 0 for card_type in DevelopmentCardType}
    cards[DevelopmentCardType.KNIGHT] = 1
    state = replace(state, players={**state.players, 1: replace(state.players[1], dev_cards=cards, new_dev_cards={card_type: 0 for card_type in DevelopmentCardType})})

    after_play = apply_action(state, PlayKnightCard(player_id=1))
    assert after_play.turn.step == TurnStep.ROBBER_MOVE
    assert after_play.discard_requirements == {}

    after_move = apply_action(after_play, MoveRobber(player_id=1, tile_id=0))
    assert after_move.turn.step == TurnStep.ROBBER_STEAL
    targets = sorted(a.target_player_id for a in get_legal_actions(after_move, 1) if isinstance(a, StealResource))
    assert targets == [2, 3]


def test_repeated_dev_draws_update_deck_and_cards_without_state_aliasing() -> None:
    state = make_main_turn_state()
    starting_deck = (
        DevelopmentCardType.KNIGHT,
        DevelopmentCardType.MONOPOLY,
        DevelopmentCardType.VICTORY_POINT,
    )
    state = replace(
        state,
        dev_deck=starting_deck,
        players={
            1: replace(state.players[1], resources={resource: 3 for resource in ResourceType}),
            2: state.players[2],
        },
    )

    snapshots: list[GameState] = [state]
    for _ in range(3):
        snapshots.append(apply_action(snapshots[-1], BuyDevelopmentCard(player_id=1)))

    assert snapshots[0].dev_deck == starting_deck
    assert snapshots[1].dev_deck == starting_deck[1:]
    assert snapshots[2].dev_deck == starting_deck[2:]
    assert snapshots[3].dev_deck == ()
    assert snapshots[0].players[1].dev_cards[DevelopmentCardType.KNIGHT] == 0
    assert snapshots[3].players[1].dev_cards[DevelopmentCardType.KNIGHT] == 1
    assert snapshots[3].players[1].dev_cards[DevelopmentCardType.MONOPOLY] == 1
    assert snapshots[3].players[1].dev_cards[DevelopmentCardType.VICTORY_POINT] == 1


def test_hidden_victory_points_count_for_win_but_not_public_observation_display() -> None:
    state = make_main_turn_state()
    state = replace(
        state,
        dev_deck=(DevelopmentCardType.VICTORY_POINT,),
        players={
            1: replace(
                state.players[1],
                victory_points=9,
                resources={
                    **state.players[1].resources,
                    ResourceType.GRAIN: 1,
                    ResourceType.WOOL: 1,
                    ResourceType.ORE: 1,
                },
            ),
            2: state.players[2],
        },
    )

    after = apply_action(state, BuyDevelopmentCard(player_id=1))
    p1_obs = get_observation(after, 1, debug=False)
    p2_obs = get_observation(after, 2, debug=False)
    p1_public = next(view for view in p1_obs.players_public if view.player_id == 1)
    p2_public = next(view for view in p2_obs.players_public if view.player_id == 1)

    assert after.winner == 1
    assert p1_obs.own_total_victory_points == 10
    assert p1_public.victory_points == 9
    assert p2_public.victory_points == 9


def test_opponent_observation_only_reveals_dev_card_counts_not_types() -> None:
    state = make_main_turn_state()
    p1_cards = {card_type: 0 for card_type in DevelopmentCardType}
    p1_cards[DevelopmentCardType.KNIGHT] = 1
    p1_cards[DevelopmentCardType.VICTORY_POINT] = 1
    p2_cards = {card_type: 0 for card_type in DevelopmentCardType}
    p2_cards[DevelopmentCardType.MONOPOLY] = 1
    state = replace(
        state,
        players={
            1: replace(state.players[1], dev_cards=p1_cards),
            2: replace(state.players[2], dev_cards=p2_cards),
        },
    )

    p2_obs = get_observation(state, 2, debug=False)
    p1_public = next(view for view in p2_obs.players_public if view.player_id == 1)

    assert p2_obs.own_dev_cards["MONOPOLY"] == 1
    assert p2_obs.own_dev_cards["KNIGHT"] == 0
    assert p2_obs.own_dev_cards["VICTORY_POINT"] == 0
    assert p1_public.dev_card_count == 2


def test_public_observation_exposes_knights_and_longest_road_fields() -> None:
    state = make_main_turn_state()
    state = replace(
        state,
        largest_army_holder=1,
        longest_road_holder=2,
        players={
            1: replace(state.players[1], knights_played=3, longest_road_length=4),
            2: replace(state.players[2], knights_played=1, longest_road_length=5),
        },
    )
    obs = get_observation(state, 1, debug=False)
    p1 = next(view for view in obs.players_public if view.player_id == 1)
    p2 = next(view for view in obs.players_public if view.player_id == 2)
    assert p1.knights_played == 3
    assert p1.has_largest_army is True
    assert p1.has_longest_road is False
    assert p2.longest_road_length == 5
    assert p2.has_longest_road is True
