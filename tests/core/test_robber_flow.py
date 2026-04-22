from __future__ import annotations

from dataclasses import replace

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import DiscardResources, MoveRobber, RollDice, SkipSteal, StealResource
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import GameState, InitialGameConfig, PlacedPieces, SetupState, TurnState
from catan.core.rng import roll_two_d6


def _seed_for_total(total: int) -> int:
    for seed in range(1, 2_000_000):
        dice, _ = roll_two_d6(seed)
        if sum(dice) == total:
            return seed
    raise AssertionError("no seed")


def _base_main_turn_state() -> GameState:
    board = build_classic_19_tile_board()
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=board, seed=1))
    return replace(
        state,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3]),
        turn=TurnState(current_player=1, step=TurnStep.ROLL),
    )


def test_roll_7_triggers_discard_not_resource_payout() -> None:
    state = _base_main_turn_state()
    tile = next(t for t in state.board.tiles if t.number_token == 7 or t.number_token is None)
    node = state.board.tile_to_nodes[tile.id][0]

    players = dict(state.players)
    players[1] = replace(players[1], resources={r: 0 for r in ResourceType})
    players[2] = replace(players[2], resources={r: 4 for r in ResourceType})
    state = replace(
        state,
        players=players,
        placed=PlacedPieces(settlements={node: 1}, roads={}, cities={}),
        rng_state=_seed_for_total(7),
    )

    after = apply_action(state, RollDice(player_id=1))
    assert after.turn.step == TurnStep.DISCARD
    assert sum(after.players[1].resources.values()) == 0


def test_discard_enforced_until_all_done() -> None:
    state = _base_main_turn_state()
    players = dict(state.players)
    players[1] = replace(players[1], resources={r: 0 for r in ResourceType})
    players[2] = replace(players[2], resources={r: 3 for r in ResourceType})  # total 15 -> discard 7
    players[3] = replace(players[3], resources={r: 2 for r in ResourceType})  # total 10 -> discard 5
    state = replace(state, players=players, rng_state=_seed_for_total(7))

    state = apply_action(state, RollDice(player_id=1))
    assert state.turn.step == TurnStep.DISCARD
    assert state.turn.priority_player == 2

    legal_p1 = get_legal_actions(state, 1)
    assert legal_p1 == []

    state = apply_action(
        state,
        DiscardResources(player_id=2, resources=((ResourceType.BRICK, 3), (ResourceType.LUMBER, 2), (ResourceType.WOOL, 2))),
    )
    assert state.turn.step == TurnStep.DISCARD
    assert state.turn.priority_player == 3

    state = apply_action(
        state,
        DiscardResources(player_id=3, resources=((ResourceType.BRICK, 2), (ResourceType.LUMBER, 1), (ResourceType.WOOL, 2))),
    )
    assert state.turn.step == TurnStep.ROBBER_MOVE


def test_robber_blocks_production() -> None:
    state = _base_main_turn_state()
    target_tile = next(t for t in state.board.tiles if t.number_token is not None and t.id != state.robber_tile_id)
    node = state.board.tile_to_nodes[target_tile.id][0]
    players = dict(state.players)
    players[1] = replace(players[1], resources={r: 0 for r in ResourceType})

    state = replace(
        state,
        players=players,
        placed=PlacedPieces(settlements={node: 1}, roads={}, cities={}),
        robber_tile_id=target_tile.id,
        rng_state=_seed_for_total(target_tile.number_token),
    )

    after = apply_action(state, RollDice(player_id=1))
    assert sum(after.players[1].resources.values()) == 0


def test_robber_move_legality_and_optional_steal() -> None:
    state = _base_main_turn_state()
    tile = next(t for t in state.board.tiles if t.id != state.robber_tile_id)
    node = state.board.tile_to_nodes[tile.id][0]

    players = dict(state.players)
    players[1] = replace(players[1], resources={r: 0 for r in ResourceType})
    players[2] = replace(players[2], resources={r: 1 for r in ResourceType})

    state = replace(
        state,
        players=players,
        placed=PlacedPieces(settlements={node: 2}, roads={}, cities={}),
        turn=TurnState(current_player=1, step=TurnStep.ROBBER_MOVE, priority_player=1),
    )

    legal = get_legal_actions(state, 1)
    assert any(isinstance(a, MoveRobber) for a in legal)

    state = apply_action(state, MoveRobber(player_id=1, tile_id=tile.id))
    assert state.robber_tile_id == tile.id
    assert state.turn.step == TurnStep.ROBBER_STEAL

    steal_action = next(a for a in get_legal_actions(state, 1) if isinstance(a, StealResource))
    after = apply_action(state, steal_action)
    assert sum(after.players[1].resources.values()) == 1


def test_steal_determinism_same_seed_same_actions() -> None:
    s1 = _base_main_turn_state()
    s2 = _base_main_turn_state()
    tile = next(t for t in s1.board.tiles if t.id != s1.robber_tile_id)
    node = s1.board.tile_to_nodes[tile.id][0]

    def prep(state: GameState) -> GameState:
        players = dict(state.players)
        players[2] = replace(players[2], resources={r: 1 for r in ResourceType})
        return replace(
            state,
            players=players,
            placed=PlacedPieces(settlements={node: 2}, roads={}, cities={}),
            turn=TurnState(current_player=1, step=TurnStep.ROBBER_MOVE, priority_player=1),
            rng_state=1234,
        )

    s1 = prep(s1)
    s2 = prep(s2)

    actions = [MoveRobber(player_id=1, tile_id=tile.id), StealResource(player_id=1, target_player_id=2)]
    for action in actions:
        s1 = apply_action(s1, action)
        s2 = apply_action(s2, action)

    assert s1 == s2
