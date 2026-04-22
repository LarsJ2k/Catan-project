from __future__ import annotations

from catan.core.engine import apply_action
from catan.core.models.action import (
    ChooseTradePartner,
    ProposePlayerTrade,
    RejectTradeResponses,
    RespondToTradeInterested,
    RespondToTradePass,
)
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState


def make_test_board() -> Board:
    edges = tuple(Edge(id=i, node_a=i, node_b=(i + 1) % 8) for i in range(8))
    tiles = (
        Tile(id=0, terrain=TerrainType.FOREST, number_token=6),
        Tile(id=1, terrain=TerrainType.HILLS, number_token=8),
        Tile(id=2, terrain=TerrainType.FIELDS, number_token=5),
    )
    return Board(
        nodes=tuple(range(8)),
        edges=edges,
        tiles=tiles,
        node_to_adjacent_tiles={
            0: (0,),
            1: (0,),
            2: (1,),
            3: (1,),
            4: (2,),
            5: (2,),
            6: (2,),
            7: (),
        },
        node_to_adjacent_edges={
            0: (0, 7),
            1: (0, 1),
            2: (1, 2),
            3: (2, 3),
            4: (3, 4),
            5: (4, 5),
            6: (5, 6),
            7: (6, 7),
        },
        edge_to_adjacent_nodes={i: (i, (i + 1) % 8) for i in range(8)},
    )


def _bundle(resource: ResourceType, amount: int) -> tuple[tuple[ResourceType, int], ...]:
    return ((resource, amount),)


def _trade_ready_state() -> GameState:
    board = make_test_board()
    players = {
        pid: PlayerState(player_id=pid, resources={r: 0 for r in ResourceType})
        for pid in (1, 2, 3, 4)
    }
    players[1].resources[ResourceType.GRAIN] = 3
    players[2].resources[ResourceType.ORE] = 2
    players[3].resources[ResourceType.ORE] = 1
    state = GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3, 4]),
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        rng_state=123,
    )
    return state


def test_trade_proposal_creation() -> None:
    state = _trade_ready_state()
    after = apply_action(
        state,
        ProposePlayerTrade(
            player_id=1,
            offered_resources=_bundle(ResourceType.GRAIN, 1),
            requested_resources=_bundle(ResourceType.ORE, 1),
        ),
    )

    assert after.player_trade is not None
    assert after.player_trade.proposer_player_id == 1
    assert after.player_trade.eligible_responders == (2, 3)
    assert after.turn is not None
    assert after.turn.step == TurnStep.PLAYER_TRADE
    assert after.turn.priority_player == 2


def test_ineligible_players_are_auto_skipped() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradePass(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))

    assert state.player_trade is None
    assert state.turn is not None
    assert state.turn.step == TurnStep.ACTIONS


def test_responders_can_express_interest_or_pass() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))

    assert state.player_trade is not None
    assert state.player_trade.interested_responders == (2,)
    assert state.turn is not None
    assert state.turn.priority_player == 3


def test_zero_interested_trade_expires() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradePass(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))

    assert state.player_trade is None
    assert state.turn is not None
    assert state.turn.step == TurnStep.ACTIONS


def test_interested_players_enable_partner_selection() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))
    state = apply_action(state, RespondToTradeInterested(player_id=3))

    assert state.player_trade is not None
    assert state.player_trade.interested_responders == (2, 3)
    assert state.turn is not None
    assert state.turn.priority_player == 1


def test_proposer_can_reject_all_interested_players() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))

    state = apply_action(state, RejectTradeResponses(player_id=1))

    assert state.player_trade is None
    assert state.turn is not None
    assert state.turn.step == TurnStep.ACTIONS


def test_successful_trade_transfers_resources_correctly() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))
    state = apply_action(state, ChooseTradePartner(player_id=1, partner_player_id=2))

    assert state.players[1].resources[ResourceType.GRAIN] == 2
    assert state.players[1].resources[ResourceType.ORE] == 1
    assert state.players[2].resources[ResourceType.GRAIN] == 1
    assert state.players[2].resources[ResourceType.ORE] == 1


def test_non_interested_or_ineligible_player_cannot_be_selected() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))

    try:
        apply_action(state, ChooseTradePartner(player_id=1, partner_player_id=4))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_turn_flow_returns_to_actions_after_trade_resolution() -> None:
    state = _trade_ready_state()
    state = apply_action(state, ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)))
    state = apply_action(state, RespondToTradeInterested(player_id=2))
    state = apply_action(state, RespondToTradePass(player_id=3))
    final = apply_action(state, ChooseTradePartner(player_id=1, partner_player_id=2))

    assert final.turn is not None
    assert final.turn.current_player == 1
    assert final.turn.step == TurnStep.ACTIONS
    assert final.turn.priority_player is None


def test_determinism_remains_intact_for_player_trade_flow() -> None:
    state_a = _trade_ready_state()
    state_b = _trade_ready_state()
    actions = [
        ProposePlayerTrade(player_id=1, offered_resources=_bundle(ResourceType.GRAIN, 1), requested_resources=_bundle(ResourceType.ORE, 1)),
        RespondToTradeInterested(player_id=2),
        RespondToTradePass(player_id=3),
        ChooseTradePartner(player_id=1, partner_player_id=2),
    ]

    for action in actions:
        state_a = apply_action(state_a, action)
        state_b = apply_action(state_b, action)

    assert state_a == state_b
