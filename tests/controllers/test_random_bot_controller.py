from __future__ import annotations

from catan.controllers.random_bot_controller import RandomBotController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import (
    ChooseTradePartner,
    DiscardResources,
    EndTurn,
    ProposePlayerTrade,
    RejectTradeResponses,
    RespondToTradeInterested,
    RespondToTradePass,
)
from catan.core.models.enums import GamePhase, ResourceType, TurnStep
from catan.core.models.state import InitialGameConfig, TurnState
from catan.core.observer import DebugObservation
from catan.runners.headless_runner import HeadlessRunner


def test_random_bot_always_selects_legal_action() -> None:
    bot = RandomBotController(seed=7, enable_delay=False)
    legal = [EndTurn(player_id=1), RespondToTradePass(player_id=1)]

    for _ in range(30):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert action in legal


def test_random_bot_never_selects_trade_initiation_action() -> None:
    bot = RandomBotController(seed=5, enable_delay=False)
    legal = [
        ProposePlayerTrade(
            player_id=1,
            offered_resources=((ResourceType.GRAIN, 1),),
            requested_resources=((ResourceType.ORE, 1),),
        ),
        RejectTradeResponses(player_id=1),
    ]

    for _ in range(30):
        action = bot.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
        assert not isinstance(action, ProposePlayerTrade)


def test_random_bot_can_respond_to_trade() -> None:
    bot = RandomBotController(seed=2, enable_delay=False)
    legal = [RespondToTradeInterested(player_id=2), RespondToTradePass(player_id=2)]

    seen = {type(bot.choose_action(observation=None, legal_actions=legal)) for _ in range(20)}  # type: ignore[arg-type]

    assert RespondToTradeInterested in seen
    assert RespondToTradePass in seen


def test_random_bot_can_select_trade_partner_or_reject_all() -> None:
    bot = RandomBotController(seed=3, enable_delay=False)
    legal = [
        ChooseTradePartner(player_id=1, partner_player_id=2),
        ChooseTradePartner(player_id=1, partner_player_id=3),
        RejectTradeResponses(player_id=1),
    ]

    seen = {bot.choose_action(observation=None, legal_actions=legal) for _ in range(30)}  # type: ignore[arg-type]

    assert ChooseTradePartner(player_id=1, partner_player_id=2) in seen
    assert ChooseTradePartner(player_id=1, partner_player_id=3) in seen
    assert RejectTradeResponses(player_id=1) in seen


def test_random_bot_works_across_multiple_turns_without_crashing() -> None:
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3, 4),
            board=build_classic_19_tile_board(),
            seed=101,
        )
    )
    bots = {pid: RandomBotController(seed=pid, enable_delay=False) for pid in (1, 2, 3, 4)}

    result = HeadlessRunner().play_until_terminal(state, bots, max_steps=60)

    assert result is not None


def test_bot_rng_does_not_affect_engine_determinism() -> None:
    state_a = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2),
            board=build_classic_19_tile_board(),
            seed=222,
        )
    )
    state_b = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2),
            board=build_classic_19_tile_board(),
            seed=222,
        )
    )
    bot = RandomBotController(seed=999, enable_delay=False)

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


def test_random_bot_builds_valid_discard_action_from_placeholder() -> None:
    bot = RandomBotController(seed=13, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=77))
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=1, step=TurnStep.DISCARD)
    state.discard_requirements = {1: 2}
    state.players[1].resources = {
        ResourceType.BRICK: 2,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }

    action = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[DiscardResources(player_id=1, resources=tuple())],
    )

    assert isinstance(action, DiscardResources)
    assert sum(amount for _, amount in action.resources) == 2
