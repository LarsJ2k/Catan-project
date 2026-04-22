from __future__ import annotations

from dataclasses import replace

from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState
from catan.ui.pygame_ui.app import PygameApp


class DummyPygame:
    pass


def make_state() -> GameState:
    board = Board(
        nodes=(0, 1),
        edges=(Edge(id=0, node_a=0, node_b=1),),
        tiles=(Tile(id=0, terrain=TerrainType.FIELDS, number_token=10),),
        node_to_adjacent_tiles={0: (0,), 1: (0,)},
        node_to_adjacent_edges={0: (0,), 1: (0,)},
        edge_to_adjacent_nodes={0: (0, 1)},
    )
    players = {
        1: PlayerState(player_id=1, resources={r: 0 for r in ResourceType}),
        2: PlayerState(player_id=2, resources={r: 0 for r in ResourceType}),
    }
    return GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ROLL, last_roll=None),
        placed=PlacedPieces(),
        rng_state=1,
    )


def test_describe_transition_includes_dice_and_payouts() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()

    p1 = replace(before.players[1], resources={**before.players[1].resources, ResourceType.GRAIN: 1})
    p2 = replace(before.players[2], resources={**before.players[2].resources, ResourceType.ORE: 2})
    after = replace(
        before,
        players={1: p1, 2: p2},
        turn=replace(before.turn, last_roll=(6, 4), step=TurnStep.ACTIONS),
    )

    lines = app._describe_transition(before, after, "RollDice(player_id=1)")
    assert "applied RollDice(player_id=1)" in lines
    assert "Dice rolled 6 + 4 = 10" in lines
    assert "P1 received 1 Wheat" in lines
    assert "P2 received 2 Ore" in lines


def test_describe_transition_logs_robber_no_victim_and_manual_prompt_and_steal() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()
    before = replace(before, robber_tile_id=None, turn=replace(before.turn, step=TurnStep.ROBBER_MOVE))

    no_victim_after = replace(before, robber_tile_id=0, turn=replace(before.turn, step=TurnStep.ACTIONS))
    lines = app._describe_transition(before, no_victim_after, "MoveRobber(player_id=1, tile_id=0)")
    assert "No eligible victim to steal from" in lines

    prompt_after = replace(before, robber_tile_id=0, turn=replace(before.turn, step=TurnStep.ROBBER_STEAL))
    lines = app._describe_transition(before, prompt_after, "MoveRobber(player_id=1, tile_id=0)")
    assert "Select a victim to steal from" in lines

    before_steal = replace(
        before,
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.GRAIN: 0}),
            2: replace(before.players[2], resources={**before.players[2].resources, ResourceType.GRAIN: 1}),
        },
        turn=replace(before.turn, step=TurnStep.ROBBER_STEAL),
    )
    p1 = replace(before_steal.players[1], resources={**before_steal.players[1].resources, ResourceType.GRAIN: 1})
    p2 = replace(before_steal.players[2], resources={**before_steal.players[2].resources, ResourceType.GRAIN: 0})
    steal_after = replace(before_steal, players={1: p1, 2: p2}, turn=replace(before_steal.turn, step=TurnStep.ACTIONS))
    lines = app._describe_transition(before_steal, steal_after, "StealResource(player_id=1, target_player_id=2)")
    assert "P1 stole 1 Wheat from P2" in lines


def test_describe_transition_logs_bank_trade() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()
    before = replace(
        before,
        turn=replace(before.turn, step=TurnStep.ACTIONS),
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.BRICK: 4}),
            2: replace(before.players[2], resources={**before.players[2].resources}),
        },
    )
    after = replace(
        before,
        players={
            1: replace(
                before.players[1],
                resources={
                    **before.players[1].resources,
                    ResourceType.BRICK: 0,
                    ResourceType.GRAIN: 1,
                },
            ),
            2: replace(before.players[2], resources={**before.players[2].resources}),
        },
    )

    lines = app._describe_transition(before, after, "BankTrade(player_id=1, ...)")
    assert "P1 traded 4 Brick for 1 Wheat" in lines
