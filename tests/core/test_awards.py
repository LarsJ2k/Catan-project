from __future__ import annotations

from dataclasses import replace

from catan.core.engine import apply_action, get_legal_actions
from catan.core.models.action import BuildRoad, EndTurn, MoveRobber, PlayKnightCard
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState


def _line_board() -> Board:
    edges = tuple(Edge(id=i, node_a=i, node_b=i + 1) for i in range(7))
    return Board(
        nodes=tuple(range(8)),
        edges=edges,
        tiles=(Tile(id=0, terrain=TerrainType.FIELDS, number_token=8), Tile(id=1, terrain=TerrainType.FOREST, number_token=5)),
        node_to_adjacent_tiles={i: (0, 1) for i in range(8)},
        node_to_adjacent_edges={
            0: (0,),
            1: (0, 1),
            2: (1, 2),
            3: (2, 3),
            4: (3, 4),
            5: (4, 5),
            6: (5, 6),
            7: (6,),
        },
        edge_to_adjacent_nodes={i: (i, i + 1) for i in range(7)},
        tile_to_nodes={0: tuple(range(4)), 1: tuple(range(4, 8))},
        ports=(),
        node_to_ports={i: () for i in range(8)},
    )


def _base_state() -> GameState:
    players = {pid: PlayerState(player_id=pid, resources={r: 10 for r in ResourceType}) for pid in (1, 2, 3)}
    return GameState(
        board=_line_board(),
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(settlements={0: 1, 7: 2}, roads={}, cities={}),
        robber_tile_id=0,
        rng_state=123,
    )


def _give_knights(state: GameState, player_id: int, amount: int) -> GameState:
    cards = {card_type: 0 for card_type in DevelopmentCardType}
    cards[DevelopmentCardType.KNIGHT] = amount
    return replace(
        state,
        players={
            **state.players,
            player_id: replace(
                state.players[player_id],
                dev_cards=cards,
                new_dev_cards={card_type: 0 for card_type in DevelopmentCardType},
            ),
        },
    )


def _play_knight_cycle(state: GameState, player_id: int) -> GameState:
    state = replace(state, turn=TurnState(current_player=player_id, step=TurnStep.ACTIONS))
    state = apply_action(state, PlayKnightCard(player_id=player_id))
    if state.phase == GamePhase.GAME_OVER:
        return state
    legal_moves = [a for a in get_legal_actions(state, player_id) if isinstance(a, MoveRobber)]
    state = apply_action(state, legal_moves[0])
    return state


def test_largest_army_requires_three_and_ties_do_not_steal() -> None:
    state = _base_state()
    state = _give_knights(state, 1, 4)
    state = _give_knights(state, 2, 4)

    for _ in range(2):
        state = _play_knight_cycle(state, 1)
    assert state.largest_army_holder is None

    state = _play_knight_cycle(state, 1)
    assert state.largest_army_holder == 1

    for _ in range(3):
        state = _play_knight_cycle(state, 2)
    assert state.largest_army_holder == 1


def test_largest_army_surpass_transfers_and_affects_win() -> None:
    state = _base_state()
    state = _give_knights(state, 1, 3)
    state = _give_knights(state, 2, 4)
    state = replace(state, players={**state.players, 2: replace(state.players[2], victory_points=8)})

    for _ in range(3):
        state = _play_knight_cycle(state, 1)
    assert state.largest_army_holder == 1
    assert state.winner is None

    for _ in range(4):
        state = _play_knight_cycle(state, 2)
    assert state.largest_army_holder == 2
    assert state.winner == 2


def test_longest_road_branching_and_blocking_rules() -> None:
    state = _base_state()
    # Player 1 roads make a branch: 0-1-2-3 and 2-4
    roads = {0: 1, 1: 1, 2: 1, 3: 1}
    state = replace(state, placed=replace(state.placed, roads=roads))
    state = apply_action(state, EndTurn(player_id=1))  # trigger cleanup path; no road recompute here
    state = replace(state, turn=TurnState(current_player=1, step=TurnStep.ACTIONS))
    state = apply_action(state, BuildRoad(player_id=1, edge_id=4))

    assert state.players[1].longest_road_length == 5
    assert state.longest_road_holder == 1

    # Opponent settlement at node 3 blocks continuity through node 3
    state = replace(state, placed=replace(state.placed, settlements={0: 1, 3: 2, 7: 2}))
    state = apply_action(state, BuildRoad(player_id=1, edge_id=5))
    assert state.players[1].longest_road_length == 3


def test_longest_road_tie_does_not_steal_and_surpass_transfers() -> None:
    state = _base_state()
    state = replace(state, placed=replace(state.placed, roads={0: 1, 1: 1, 2: 1, 3: 1}))
    state = apply_action(state, BuildRoad(player_id=1, edge_id=4))
    assert state.longest_road_holder == 1

    state = replace(state, turn=TurnState(current_player=2, step=TurnStep.ACTIONS))
    state = replace(state, placed=replace(state.placed, roads={**state.placed.roads, 6: 2}))
    state = apply_action(state, BuildRoad(player_id=2, edge_id=5))
    assert state.players[2].longest_road_length == 2
    assert state.longest_road_holder == 1
