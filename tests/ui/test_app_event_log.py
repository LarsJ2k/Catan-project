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
