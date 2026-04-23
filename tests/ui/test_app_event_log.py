from __future__ import annotations

from dataclasses import replace

from catan.core.models.board import Board, Edge, Port, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, PlayerTradePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, PlayerTradeState, SetupState, TurnState
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
        ports=(Port(id=0, edge_id=0, node_ids=(0, 1), trade_resource=ResourceType.ORE),),
        node_to_ports={0: (0,), 1: (0,)},
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


def test_describe_transition_logs_port_trade_rate_and_source() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()
    before = replace(
        before,
        turn=replace(before.turn, step=TurnStep.ACTIONS),
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.ORE: 2}),
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
                    ResourceType.ORE: 0,
                    ResourceType.GRAIN: 1,
                },
            ),
            2: replace(before.players[2], resources={**before.players[2].resources}),
        },
    )

    lines = app._describe_transition(before, after, "BankTrade(player_id=1, ...)")
    assert "P1 traded 2 Ore for 1 Wheat via Ore port" in lines


def test_describe_transition_player_trade_selection_does_not_log_rejection_on_success() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()
    before = replace(
        before,
        turn=replace(before.turn, step=TurnStep.PLAYER_TRADE),
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.BRICK: 1}),
            2: replace(before.players[2], resources={**before.players[2].resources}),
        },
        player_trade=PlayerTradeState(
            proposer_player_id=1,
            offered_resources=((ResourceType.BRICK, 1),),
            requested_resources=((ResourceType.ORE, 1),),
            responder_order=(2,),
            current_responder_index=1,
            eligible_responders=(2,),
            interested_responders=(2,),
            phase=PlayerTradePhase.PARTNER_SELECTION,
        ),
    )
    after = replace(
        before,
        turn=replace(before.turn, step=TurnStep.ACTIONS),
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.BRICK: 0, ResourceType.ORE: 1}),
            2: replace(before.players[2], resources={**before.players[2].resources, ResourceType.BRICK: 1, ResourceType.ORE: 0}),
        },
        player_trade=None,
    )

    lines = app._describe_transition(before, after, "ChooseTradePartner(player_id=1, partner_player_id=2)")
    assert "P1 traded 1 Brick for 1 Ore with P2" in lines
    assert "P1 rejected all trade responses" not in lines


def test_describe_transition_dev_card_purchase_does_not_leak_card_type() -> None:
    app = PygameApp(DummyPygame())
    before = make_state()
    before = replace(
        before,
        turn=replace(before.turn, step=TurnStep.ACTIONS),
        dev_deck=(DevelopmentCardType.VICTORY_POINT,),
        players={
            1: replace(before.players[1], dev_cards={**before.players[1].dev_cards}),
            2: before.players[2],
        },
    )
    p1_after_cards = {**before.players[1].dev_cards, DevelopmentCardType.VICTORY_POINT: 1}
    after = replace(
        before,
        dev_deck=(),
        players={
            1: replace(before.players[1], dev_cards=p1_after_cards),
            2: before.players[2],
        },
    )

    lines = app._describe_transition(before, after, "BuyDevelopmentCard(player_id=1)")

    assert "P1 bought a development card" in lines
    assert not any("victory" in line.lower() for line in lines)


def test_describe_transition_year_of_plenty_only_logs_combined_gain() -> None:
    app = PygameApp(DummyPygame())
    before = replace(make_state(), turn=TurnState(current_player=1, step=TurnStep.YEAR_OF_PLENTY))
    after = replace(
        before,
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        players={
            1: replace(
                before.players[1],
                resources={
                    **before.players[1].resources,
                    ResourceType.LUMBER: 1,
                    ResourceType.WOOL: 1,
                },
            ),
            2: before.players[2],
        },
    )

    lines = app._describe_transition(before, after, "ChooseYearOfPlentyResources(player_id=1, resources=[...])")
    assert "P1 received 1 Lumber and 1 Sheep" in lines
    assert "P1 received 1 Lumber" not in lines
    assert "P1 received 1 Sheep" not in lines


def test_describe_transition_monopoly_logs_combined_gain_only_once() -> None:
    app = PygameApp(DummyPygame())
    before = replace(
        make_state(),
        turn=TurnState(current_player=1, step=TurnStep.MONOPOLY),
        players={
            1: replace(make_state().players[1], resources={r: 0 for r in ResourceType}),
            2: replace(make_state().players[2], resources={**{r: 0 for r in ResourceType}, ResourceType.ORE: 3}),
        },
    )
    after = replace(
        before,
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        players={
            1: replace(before.players[1], resources={**before.players[1].resources, ResourceType.ORE: 3}),
            2: replace(before.players[2], resources={**before.players[2].resources, ResourceType.ORE: 0}),
        },
    )

    lines = app._describe_transition(before, after, "ChooseMonopolyResource(player_id=1, resource='ORE')")
    assert "P1 played Monopoly on Ore" in lines
    assert "P1 collected 3 Ore" in lines
    assert "P1 received 3 Ore" not in lines
