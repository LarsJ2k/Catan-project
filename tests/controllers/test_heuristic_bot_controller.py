from __future__ import annotations

from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.controllers.heuristic_params import HeuristicScoringParams
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import apply_action, create_initial_state, get_legal_actions
from catan.core.models.action import (
    BankTrade,
    BuildCity,
    BuildRoad,
    BuildSettlement,
    DiscardResources,
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


def test_heuristic_trade_response_uses_conservative_plan_check() -> None:
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
    assert isinstance(good_trade_choice, RespondToTradePass)

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


def test_heuristic_prefers_settlement_over_weak_road_when_both_available() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=22))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    bot = HeuristicBotController(seed=2, enable_delay=False)

    road = BuildRoad(player_id=1, edge_id=0)
    settlement = BuildSettlement(player_id=1, node_id=0)
    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[road, settlement])

    assert chosen == settlement


def test_heuristic_end_turn_beats_dead_road() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=31))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.placed.settlements[0] = 2
    state.placed.settlements[1] = 2
    state.placed.settlements[11] = 2
    state.placed.settlements[12] = 2
    bot = HeuristicBotController(seed=2, enable_delay=False)

    dead_road = BuildRoad(player_id=1, edge_id=0)
    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[dead_road, EndTurn(player_id=1)])

    assert isinstance(chosen, EndTurn)


def test_heuristic_prefers_road_that_advances_to_stronger_target() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=44))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.placed.settlements[10] = 1
    bot = HeuristicBotController(seed=9, enable_delay=False)

    anchor_edges = list(state.board.node_to_adjacent_edges[10])
    scored = [(edge_id, bot._score_road(BuildRoad(player_id=1, edge_id=edge_id), state)) for edge_id in anchor_edges]
    best_edge_id = max(scored, key=lambda pair: pair[1])[0]
    worst_edge_id = min(scored, key=lambda pair: pair[1])[0]
    road_to_strong_target = BuildRoad(player_id=1, edge_id=best_edge_id)
    road_to_weaker_target = BuildRoad(player_id=1, edge_id=worst_edge_id)
    chosen = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[road_to_weaker_target, road_to_strong_target],
    )

    assert chosen == road_to_strong_target


def test_heuristic_save_for_settlement_penalizes_road_spend() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=55))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 1,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 1,
        ResourceType.ORE: 0,
    }
    state.placed.settlements[10] = 1
    bot = HeuristicBotController(seed=4, enable_delay=False)

    road = BuildRoad(player_id=1, edge_id=11)
    chosen = bot.choose_action(observation=DebugObservation(state=state), legal_actions=[road, EndTurn(player_id=1)])

    assert isinstance(chosen, EndTurn)


def test_heuristic_bot_builds_valid_discard_action_from_placeholder() -> None:
    bot = HeuristicBotController(seed=6, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=88))
    state.phase = GamePhase.MAIN_TURN
    state.turn = TurnState(current_player=1, priority_player=1, step=TurnStep.DISCARD)
    state.discard_requirements = {1: 3}
    state.players[1].resources = {
        ResourceType.BRICK: 2,
        ResourceType.LUMBER: 1,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 1,
    }

    action = bot.choose_action(
        observation=DebugObservation(state=state),
        legal_actions=[DiscardResources(player_id=1, resources=tuple())],
    )

    assert isinstance(action, DiscardResources)
    assert sum(amount for _, amount in action.resources) == 3


def test_heuristic_param_change_can_change_choice_deterministically() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=91))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    legal = [BuildSettlement(player_id=1, node_id=0), EndTurn(player_id=1)]

    passive_bot = HeuristicBotController(
        seed=1,
        enable_delay=False,
        heuristic_params=HeuristicScoringParams(settlement_base_score=-500.0, end_turn_base_score=10.0),
    )
    active_bot = HeuristicBotController(
        seed=1,
        enable_delay=False,
        heuristic_params=HeuristicScoringParams(settlement_base_score=300.0, end_turn_base_score=0.0),
    )

    passive_choice_a = passive_bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    passive_choice_b = passive_bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)
    active_choice = active_bot.choose_action(observation=DebugObservation(state=state), legal_actions=legal)

    assert isinstance(passive_choice_a, EndTurn)
    assert passive_choice_a == passive_choice_b
    assert isinstance(active_choice, BuildSettlement)


def test_heuristic_rejects_no_progress_bank_trade() -> None:
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2), board=build_classic_19_tile_board(), seed=161))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 0,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 4,
        ResourceType.GRAIN: 0,
        ResourceType.ORE: 0,
    }
    bot = HeuristicBotController(seed=4, enable_delay=False)
    trade = BankTrade(player_id=1, offer_resource=ResourceType.WOOL, request_resource=ResourceType.BRICK, trade_rate=4)
    chosen = bot.choose_action(DebugObservation(state=state), [trade, EndTurn(player_id=1)])
    assert isinstance(chosen, EndTurn)


def test_heuristic_successful_trade_does_not_increase_player_trade_proposal_limit() -> None:
    bot = HeuristicBotController(seed=42, enable_delay=False)
    state = create_initial_state(InitialGameConfig(player_ids=(1, 2, 3), board=build_classic_19_tile_board(), seed=314))
    state.turn = TurnState(current_player=1, step=TurnStep.ACTIONS)
    state.players[1].resources = {
        ResourceType.BRICK: 2,
        ResourceType.LUMBER: 0,
        ResourceType.WOOL: 0,
        ResourceType.GRAIN: 2,
        ResourceType.ORE: 1,
    }
    state.players[2].resources[ResourceType.ORE] = 1
    state.players[1].player_trades_completed += 3

    bot._prepare_turn_context(state)
    bot._player_trade_proposals_this_turn = 1

    assert bot._candidate_player_trades(state, [EndTurn(player_id=1)]) == []
