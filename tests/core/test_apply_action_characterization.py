from __future__ import annotations

from dataclasses import replace

import pytest

from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import (
    BankTrade,
    BuyDevelopmentCard,
    ChooseTradePartner,
    ChooseYearOfPlentyResources,
    EndTurn,
    MoveRobber,
    PlaceSetupRoad,
    PlaceSetupSettlement,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RollDice,
)
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, InitialGameConfig, PlacedPieces, PlayerState, SetupState, TurnState


def _board() -> Board:
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


def _main_state() -> GameState:
    return GameState(
        board=_board(),
        players={
            1: PlayerState(player_id=1, resources={resource: 0 for resource in ResourceType}),
            2: PlayerState(player_id=2, resources={resource: 0 for resource in ResourceType}),
        },
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        rng_state=3,
    )


def _assert_structural_invariants(before: GameState, after: GameState) -> None:
    assert isinstance(after, GameState)
    assert set(after.players.keys()) == set(before.players.keys())
    assert after.board == before.board
    assert after.turn is None or after.turn.current_player in after.players
    for player in after.players.values():
        assert set(player.resources.keys()) == set(ResourceType)
        assert player.roads_left >= 0 and player.settlements_left >= 0 and player.cities_left >= 0


@pytest.mark.parametrize(
    ("label", "builder"),
    [
        ("setup-settlement", lambda: (create_initial_state(InitialGameConfig(player_ids=(1, 2), board=_board(), seed=1)), PlaceSetupSettlement(player_id=1, node_id=0))),
        ("setup-road", lambda: (apply_action(create_initial_state(InitialGameConfig(player_ids=(1, 2), board=_board(), seed=1)), PlaceSetupSettlement(player_id=1, node_id=0)), PlaceSetupRoad(player_id=1, edge_id=0))),
        ("roll", lambda: (replace(_main_state(), turn=TurnState(current_player=1, step=TurnStep.ROLL)), RollDice(player_id=1))),
        ("buy-dev-card", lambda: (
            replace(
                _main_state(),
                dev_deck=(DevelopmentCardType.KNIGHT,),
                players={
                    1: replace(_main_state().players[1], resources={ResourceType.BRICK: 0, ResourceType.LUMBER: 0, ResourceType.WOOL: 1, ResourceType.GRAIN: 1, ResourceType.ORE: 1}),
                    2: _main_state().players[2],
                },
            ),
            BuyDevelopmentCard(player_id=1),
        )),
        ("bank-trade", lambda: (
            replace(
                _main_state(),
                players={
                    1: replace(_main_state().players[1], resources={ResourceType.BRICK: 4, ResourceType.LUMBER: 0, ResourceType.WOOL: 0, ResourceType.GRAIN: 0, ResourceType.ORE: 0}),
                    2: _main_state().players[2],
                },
            ),
            BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.GRAIN, trade_rate=4),
        )),
        ("player-trade-choose-partner", lambda: (apply_action(apply_action(replace(_main_state(), players={1: replace(_main_state().players[1], resources={ResourceType.BRICK:0,ResourceType.LUMBER:0,ResourceType.WOOL:0,ResourceType.GRAIN:1,ResourceType.ORE:0}), 2: replace(_main_state().players[2], resources={ResourceType.BRICK:0,ResourceType.LUMBER:0,ResourceType.WOOL:0,ResourceType.GRAIN:0,ResourceType.ORE:1})}), ProposePlayerTrade(player_id=1, offered_resources=((ResourceType.GRAIN, 1),), requested_resources=((ResourceType.ORE, 1),))), RespondToTradeInterested(player_id=2)), ChooseTradePartner(player_id=1, partner_player_id=2))),
        ("move-robber", lambda: (replace(_main_state(), turn=TurnState(current_player=1, step=TurnStep.ROBBER_MOVE), robber_tile_id=None), MoveRobber(player_id=1, tile_id=0))),
        ("year-of-plenty-choice", lambda: (replace(_main_state(), turn=TurnState(current_player=1, step=TurnStep.YEAR_OF_PLENTY)), ChooseYearOfPlentyResources(player_id=1, first_resource=ResourceType.ORE, second_resource=ResourceType.WOOL))),
        ("end-turn", lambda: (_main_state(), EndTurn(player_id=1))),
    ],
)
def test_apply_action_characterization_for_core_categories(label: str, builder: object) -> None:
    state, action = builder()
    assert action in get_legal_actions(state, 1), label
    after = apply_action(state, action)
    _assert_structural_invariants(state, after)


@pytest.mark.parametrize(
    "state,action",
    [
        (_main_state(), EndTurn(player_id=2)),
        (_main_state(), BankTrade(player_id=1, offer_resource=ResourceType.BRICK, request_resource=ResourceType.BRICK, trade_rate=4)),
    ],
)
def test_apply_action_rejects_illegal_actions(state: GameState, action: object) -> None:
    assert action not in get_legal_actions(state, 1)
    with pytest.raises(ValueError):
        apply_action(state, action)
