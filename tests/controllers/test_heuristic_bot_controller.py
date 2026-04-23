from __future__ import annotations

from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import (
    BuildCity,
    BuildRoad,
    BuildSettlement,
    EndTurn,
    ProposePlayerTrade,
    RespondToTradeInterested,
    RespondToTradePass,
    RollDice,
)
from catan.core.models.enums import GamePhase, PlayerTradePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, PlayerTradeState, TurnState
from catan.core.observer import DebugObservation
from catan.runners.headless_runner import HeadlessRunner


def test_heuristic_bot_always_selects_legal_action() -> None:
    bot = HeuristicBotController(seed=7, enable_delay=False)
    legal = [EndTurn(player_id=1), BuildRoad(player_id=1, edge_id=2)]

    for _ in range(30):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert action in legal


def test_heuristic_bot_never_selects_trade_initiation_action() -> None:
    bot = HeuristicBotController(seed=5, enable_delay=False)
    legal = [
        ProposePlayerTrade(
            player_id=1,
            offered_resources=((ResourceType.GRAIN, 1),),
            requested_resources=((ResourceType.ORE, 1),),
        ),
        EndTurn(player_id=1),
    ]

    for _ in range(30):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert not isinstance(action, ProposePlayerTrade)


def test_heuristic_prefers_roll_dice_when_available() -> None:
    bot = HeuristicBotController(seed=3, enable_delay=False)
    legal = [RollDice(player_id=1), EndTurn(player_id=1)]

    assert bot.choose_action(observation=None, legal_actions=legal) == RollDice(player_id=1)  # type: ignore[arg-type]


def test_heuristic_prefers_settlement_over_end_turn() -> None:
    bot = HeuristicBotController(seed=11, enable_delay=False)
    legal = [EndTurn(player_id=1), BuildSettlement(player_id=1, node_id=9)]

    assert bot.choose_action(observation=None, legal_actions=legal) == BuildSettlement(player_id=1, node_id=9)  # type: ignore[arg-type]


def test_heuristic_prefers_city_over_road() -> None:
    bot = HeuristicBotController(seed=4, enable_delay=False)
    legal = [BuildRoad(player_id=1, edge_id=6), BuildCity(player_id=1, node_id=3)]

    assert bot.choose_action(observation=None, legal_actions=legal) == BuildCity(player_id=1, node_id=3)  # type: ignore[arg-type]


def test_heuristic_trade_response_uses_simple_value_check() -> None:
    bot = HeuristicBotController(seed=4, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=44))
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=2, step=TurnStep.ACTIONS)
    state.players[2].resources[ResourceType.BRICK] = 2
    state.players[2].resources[ResourceType.ORE] = 1
    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.ORE, 1),),
        requested_resources=((ResourceType.BRICK, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )

    legal = [RespondToTradeInterested(player_id=2), RespondToTradePass(player_id=2)]
    good_trade_choice = bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert isinstance(good_trade_choice, RespondToTradeInterested)

    state.player_trade = PlayerTradeState(
        proposer_player_id=1,
        offered_resources=((ResourceType.BRICK, 1),),
        requested_resources=((ResourceType.ORE, 1),),
        responder_order=(2,),
        current_responder_index=0,
        eligible_responders=(2,),
        interested_responders=(),
        phase=PlayerTradePhase.RESPONSES,
    )
    bad_trade_choice = bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    assert isinstance(bad_trade_choice, RespondToTradePass)


def test_heuristic_bot_rng_does_not_affect_engine_determinism() -> None:
    state_a = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=222))
    state_b = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=222))
    bot = HeuristicBotController(seed=999, enable_delay=False)

    runner = HeadlessRunner()

    for _ in range(12):
        actor = runner._active_player(state_a)
        assert actor is not None
        legal_a = get_legal_actions(state_a, actor)
        legal_b = get_legal_actions(state_b, actor)
        assert legal_a == legal_b

        _ = bot.choose_action(observation=None, legal_actions=legal_a)  # type: ignore[arg-type]
        state_a = apply_action(state_a, legal_a[0])
        state_b = apply_action(state_b, legal_b[0])

    assert state_a == state_b
    assert state_a.rng_state == state_b.rng_state
