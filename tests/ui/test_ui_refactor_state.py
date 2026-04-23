from __future__ import annotations

from dataclasses import replace

from catan.core.models.action import BankTrade, BuildCity, BuildRoad, BuildSettlement, BuyDevelopmentCard, DiscardResources, EndTurn, PlayKnightCard, RollDice
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState
from catan.controllers.human_controller import HumanController
from catan.ui.pygame_ui.app import PygameApp
from catan.ui.pygame_ui.renderer import PygameRenderer, primary_turn_button_state


class DummyRect:
    def __init__(self, hit: bool = False):
        self._hit = hit

    def collidepoint(self, _pos) -> bool:
        return self._hit


class DummyPygame:
    pass


class DummyDraw:
    @staticmethod
    def rect(*_args, **_kwargs) -> None:
        return None


class DummyRectFactory:
    def __call__(self, *_args, **_kwargs):
        return DummyRect(False)


def make_state() -> GameState:
    board = Board(
        nodes=(0, 1),
        edges=(Edge(id=0, node_a=0, node_b=1),),
        tiles=(Tile(id=0, terrain=TerrainType.FIELDS, number_token=8),),
        node_to_adjacent_tiles={0: (0,), 1: (0,)},
        node_to_adjacent_edges={0: (0,), 1: (0,)},
        edge_to_adjacent_nodes={0: (0, 1)},
        ports=(),
        node_to_ports={0: (), 1: ()},
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
        turn=TurnState(current_player=1, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        rng_state=1,
    )


def test_bank_counts_subtract_player_hands() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = make_state()
    p1 = replace(state.players[1], resources={**state.players[1].resources, ResourceType.LUMBER: 2})
    p2 = replace(state.players[2], resources={**state.players[2].resources, ResourceType.LUMBER: 1, ResourceType.ORE: 3})
    state = replace(state, players={1: p1, 2: p2})

    counts = renderer._bank_counts(state)

    assert counts[ResourceType.LUMBER] == 16
    assert counts[ResourceType.ORE] == 16
    assert counts[ResourceType.BRICK] == 19


def test_draw_bottom_bar_subtracts_selected_discard_cards_from_visible_hand() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    renderer.pg = DummyPygame()
    renderer.pg.draw = DummyDraw()
    renderer.pg.Rect = DummyRectFactory()
    renderer._draw_dev_card_panel = lambda *_args, **_kwargs: {}
    captured: dict[ResourceType, int] = {}

    def capture_card(_screen, _x, _y, _w, _h, resource, amount, *, compact: bool = False) -> None:
        if not compact:
            captured[resource] = amount

    renderer._draw_resource_card = capture_card
    state = make_state()
    p1 = replace(state.players[1], resources={**state.players[1].resources, ResourceType.ORE: 3})
    state = replace(state, players={1: p1, 2: state.players[2]})
    discard_ui = {"selected": {r: 0 for r in ResourceType}}
    discard_ui["selected"][ResourceType.ORE] = 2

    renderer._draw_bottom_bar(
        screen=object(),
        state=state,
        active_player=1,
        width=1200,
        height=700,
        panel_x=900,
        bottom_h=170,
        trade_ui=None,
        discard_ui=discard_ui,
        legal_actions=[],
    )

    assert captured[ResourceType.ORE] == 1


def test_bank_trade_draft_validity_respects_port_rates() -> None:
    app = PygameApp(DummyPygame())
    legal = [
        BankTrade(player_id=1, offer_resource=ResourceType.LUMBER, request_resource=ResourceType.BRICK, trade_rate=4),
        BankTrade(player_id=1, offer_resource=ResourceType.LUMBER, request_resource=ResourceType.ORE, trade_rate=2),
    ]
    offered = {r: 0 for r in ResourceType}
    requested = {r: 0 for r in ResourceType}
    offered[ResourceType.LUMBER] = 2
    requested[ResourceType.ORE] = 1

    assert app._is_valid_bank_trade_draft(legal, 1, offered, requested) is True

    requested = {r: 0 for r in ResourceType}
    requested[ResourceType.BRICK] = 1
    assert app._is_valid_bank_trade_draft(legal, 1, offered, requested) is False


def test_trade_draft_offer_click_caps_to_available_resources_and_cancel_signal() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    p1 = replace(state.players[1], resources={**state.players[1].resources, ResourceType.ORE: 1})
    state = replace(state, players={1: p1, 2: state.players[2]})
    offered = {r: 0 for r in ResourceType}
    requested = {r: 0 for r in ResourceType}
    trade_ui = {
        "bank_supply_rects": {r: DummyRect(False) for r in ResourceType},
        "request_rects": {r: DummyRect(False) for r in ResourceType},
        "offer_rects": {r: DummyRect(False) for r in ResourceType},
        "hand_rects": {r: DummyRect(r == ResourceType.ORE) for r in ResourceType},
        "cancel_button_rect": DummyRect(False),
        "bank_button_rect": DummyRect(False),
    }

    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    assert offered[ResourceType.ORE] == 1

    trade_ui["hand_rects"][ResourceType.ORE] = DummyRect(False)
    trade_ui["cancel_button_rect"] = DummyRect(True)
    assert app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested) == "cancel"


def test_button_enablement_for_build_and_dev() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = make_state()
    state = replace(
        state,
        players={
            1: replace(
                state.players[1],
                resources={
                    **state.players[1].resources,
                    ResourceType.ORE: 1,
                    ResourceType.GRAIN: 1,
                    ResourceType.WOOL: 1,
                },
            ),
            2: state.players[2],
        },
    )
    legal = [
        BuildRoad(player_id=1, edge_id=0),
        BuildSettlement(player_id=1, node_id=0),
        BuildCity(player_id=1, node_id=1),
        BuyDevelopmentCard(player_id=1),
    ]

    assert renderer._is_action_enabled("road", legal, state, 1) is True
    assert renderer._is_action_enabled("settlement", legal, state, 1) is True
    assert renderer._is_action_enabled("city", legal, state, 1) is True
    assert renderer._is_action_enabled("dev", legal, state, 1) is True


def test_primary_turn_button_state_logic() -> None:
    assert primary_turn_button_state(can_roll=True, can_end=False) == "Roll Dice"
    assert primary_turn_button_state(can_roll=False, can_end=True) == "End Turn"
    assert primary_turn_button_state(can_roll=False, can_end=False) == "Waiting"


def test_phase_banner_uses_active_player_color_and_name() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = make_state()

    color, label = renderer._phase_banner_config(state)

    assert color == (235, 87, 87)
    assert label == "P1: bouw, trade of eindig je beurt"


def test_phase_banner_uses_setup_player_when_turn_is_none() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = replace(make_state(), turn=None, setup=SetupState(pending_settlement_player=2, order=[1, 2]))

    color, label = renderer._phase_banner_config(state)

    assert color == (92, 178, 92)
    assert label == "Setup fase • P2: plaats een settlement"


def test_hand_view_player_uses_active_player_for_human_turn() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()

    hand_player = app._hand_view_player(state, 1, {1: HumanController(), 2: object()})

    assert hand_player == 1


def test_hand_view_player_hides_bot_hand_and_shows_previous_player() -> None:
    app = PygameApp(DummyPygame())
    state = replace(make_state(), turn=TurnState(current_player=2, step=TurnStep.ACTIONS))

    hand_player = app._hand_view_player(state, 2, {1: HumanController(), 2: object()})

    assert hand_player == 1


def test_hand_view_player_shows_single_human_in_1v3_even_when_not_adjacent() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    players = {
        1: state.players[1],
        2: state.players[2],
        3: replace(state.players[2], player_id=3),
        4: replace(state.players[2], player_id=4),
    }
    state = replace(
        state,
        players=players,
        setup=SetupState(order=[1, 2, 3, 4]),
        turn=TurnState(current_player=3, step=TurnStep.ACTIONS),
    )

    hand_player = app._hand_view_player(state, 3, {1: HumanController(), 2: object(), 3: object(), 4: object()})

    assert hand_player == 1


def test_scoreboard_vp_text_hides_hidden_vp_when_private_info_not_available() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = make_state()
    players = {
        1: replace(
            state.players[1],
            dev_cards={**state.players[1].dev_cards, DevelopmentCardType.VICTORY_POINT: 1},
        ),
        2: state.players[2],
    }
    state = replace(state, players=players, turn=TurnState(current_player=1, step=TurnStep.ACTIONS))

    assert renderer._scoreboard_vp_text(state, player_id=1, reveal_current_hidden_vp=False) == "VP 0"
    assert renderer._scoreboard_vp_text(state, player_id=1, reveal_current_hidden_vp=True) == "VP 0(1)"


def test_clicking_dice_button_only_rolls() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    roll_action = RollDice(player_id=1)
    end_action = EndTurn(player_id=1)
    button_rects = {
        "trade": DummyRect(False),
        "dev": DummyRect(False),
        "road": DummyRect(False),
        "settlement": DummyRect(False),
        "city": DummyRect(False),
        "primary": DummyRect(False),
        "dice": DummyRect(True),
        "trade_cancel": DummyRect(False),
    }

    clicked = app._handle_action_button_click((0, 0), button_rects, [roll_action, end_action], state, 1, None, False)
    assert clicked == roll_action

    clicked = app._handle_action_button_click((0, 0), button_rects, [end_action], state, 1, None, False)
    assert clicked is None


def test_build_mode_is_not_cleared_by_non_button_click() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    button_rects = {
        "trade": DummyRect(False),
        "dev": DummyRect(False),
        "road": DummyRect(False),
        "settlement": DummyRect(False),
        "city": DummyRect(False),
        "primary": DummyRect(False),
        "dice": DummyRect(False),
        "trade_cancel": DummyRect(False),
    }
    clicked = app._handle_action_button_click((0, 0), button_rects, [], state, 1, "road", False)
    assert clicked is None


def test_effective_build_mode_forces_road_during_road_building_step() -> None:
    app = PygameApp(DummyPygame())
    state = replace(make_state(), turn=TurnState(current_player=1, step=TurnStep.ROAD_BUILDING))

    assert app._effective_build_mode(state, None) == "road"
    assert app._effective_build_mode(state, "city") == "road"


def test_clicking_dev_button_returns_buy_dev_action_when_legal() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    button_rects = {
        "trade": DummyRect(False),
        "dev": DummyRect(True),
        "road": DummyRect(False),
        "settlement": DummyRect(False),
        "city": DummyRect(False),
        "primary": DummyRect(False),
        "dice": DummyRect(False),
        "trade_cancel": DummyRect(False),
    }
    buy_dev = BuyDevelopmentCard(player_id=1)
    clicked = app._handle_action_button_click((0, 0), button_rects, [buy_dev], state, 1, None, False)
    assert clicked == buy_dev


def test_trade_overlay_clicks_follow_four_row_behavior() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    p1 = replace(state.players[1], resources={**state.players[1].resources, ResourceType.ORE: 2})
    state = replace(state, players={1: p1, 2: state.players[2]})
    offered = {r: 0 for r in ResourceType}
    requested = {r: 0 for r in ResourceType}
    trade_ui = {
        "bank_supply_rects": {r: DummyRect(r == ResourceType.GRAIN) for r in ResourceType},
        "request_rects": {r: DummyRect(False) for r in ResourceType},
        "offer_rects": {r: DummyRect(False) for r in ResourceType},
        "hand_rects": {r: DummyRect(r == ResourceType.ORE) for r in ResourceType},
        "cancel_button_rect": DummyRect(False),
        "bank_button_rect": DummyRect(False),
    }

    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    assert requested[ResourceType.GRAIN] == 1

    trade_ui["bank_supply_rects"][ResourceType.GRAIN] = DummyRect(False)
    trade_ui["request_rects"][ResourceType.GRAIN] = DummyRect(True)
    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    assert requested[ResourceType.GRAIN] == 0

    trade_ui["request_rects"][ResourceType.GRAIN] = DummyRect(False)
    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    assert offered[ResourceType.ORE] == 1

    trade_ui["hand_rects"][ResourceType.ORE] = DummyRect(False)
    trade_ui["offer_rects"][ResourceType.ORE] = DummyRect(True)
    app._handle_trade_overlay_click((0, 0), trade_ui, [], state, 1, offered, requested)
    assert offered[ResourceType.ORE] == 0


def test_discard_overlay_clicks_add_remove_and_submit() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    p1 = replace(
        state.players[1],
        resources={**state.players[1].resources, ResourceType.BRICK: 2, ResourceType.ORE: 2},
    )
    state = replace(state, players={1: p1, 2: state.players[2]})
    selection = {r: 0 for r in ResourceType}
    discard_ui = {
        "required": 2,
        "hand_rects": {r: DummyRect(r == ResourceType.BRICK) for r in ResourceType},
        "selected_rects": {r: DummyRect(False) for r in ResourceType},
        "continue_button_rect": DummyRect(False),
    }

    app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection)
    assert selection[ResourceType.BRICK] == 1

    discard_ui["hand_rects"] = {r: DummyRect(r == ResourceType.ORE) for r in ResourceType}
    app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection)
    assert selection[ResourceType.ORE] == 1

    discard_ui["hand_rects"] = {r: DummyRect(False) for r in ResourceType}
    discard_ui["selected_rects"] = {r: DummyRect(r == ResourceType.BRICK) for r in ResourceType}
    app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection)
    assert selection[ResourceType.BRICK] == 0

    discard_ui["hand_rects"] = {r: DummyRect(r == ResourceType.BRICK) for r in ResourceType}
    app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection)
    discard_ui["hand_rects"] = {r: DummyRect(False) for r in ResourceType}
    discard_ui["selected_rects"] = {r: DummyRect(False) for r in ResourceType}
    discard_ui["continue_button_rect"] = DummyRect(True)
    action = app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection)
    assert action == DiscardResources(
        player_id=1,
        resources=((ResourceType.BRICK, 1), (ResourceType.ORE, 1)),
    )


def test_discard_overlay_submit_stays_blocked_until_required_count() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    p1 = replace(state.players[1], resources={**state.players[1].resources, ResourceType.ORE: 2})
    state = replace(state, players={1: p1, 2: state.players[2]})
    selection = {r: 0 for r in ResourceType}
    selection[ResourceType.ORE] = 1
    discard_ui = {
        "required": 2,
        "hand_rects": {r: DummyRect(False) for r in ResourceType},
        "selected_rects": {r: DummyRect(False) for r in ResourceType},
        "continue_button_rect": DummyRect(True),
    }

    assert app._handle_discard_overlay_click((0, 0), discard_ui, state, 1, selection) is None


def test_sync_discard_selection_resets_when_discard_player_changes() -> None:
    app = PygameApp(DummyPygame())
    state = replace(
        make_state(),
        turn=TurnState(current_player=2, step=TurnStep.DISCARD),
        discard_requirements={1: 3, 2: 4},
    )
    selection = {r: 0 for r in ResourceType}
    selection[ResourceType.BRICK] = 2

    current_player = app._sync_discard_selection(state, 2, selection, 1)

    assert current_player == 2
    assert all(amount == 0 for amount in selection.values())


def test_sync_discard_selection_clears_when_discard_phase_ends() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()
    selection = {r: 0 for r in ResourceType}
    selection[ResourceType.ORE] = 1

    current_player = app._sync_discard_selection(state, 1, selection, 1)

    assert current_player is None
    assert all(amount == 0 for amount in selection.values())


def test_dev_card_click_action_only_returns_legal_knight_action() -> None:
    app = PygameApp(DummyPygame())
    knight_action = PlayKnightCard(player_id=1)
    rects = {DevelopmentCardType.KNIGHT: DummyRect(True)}

    assert app._dev_card_click_action((0, 0), rects, [knight_action]) == knight_action
    assert app._dev_card_click_action((0, 0), rects, []) is None
    assert app._dev_card_click_action((0, 0), {DevelopmentCardType.KNIGHT: DummyRect(False)}, [knight_action]) is None


def test_settings_click_toggles_when_gear_is_clicked() -> None:
    app = PygameApp(DummyPygame())
    settings_ui = {
        "settings_button_rect": DummyRect(True),
    }

    assert app._handle_settings_click((0, 0), settings_ui, menu_open=False) == "toggle"




def test_settings_click_returns_menu_when_clicking_inside_menu() -> None:
    app = PygameApp(DummyPygame())
    settings_ui = {
        "settings_button_rect": DummyRect(False),
        "quit_to_menu_rect": DummyRect(False),
        "quit_to_desktop_rect": DummyRect(False),
        "apply_delay_rect": DummyRect(False),
        "settings_menu_rect": DummyRect(True),
    }

    assert app._handle_settings_click((0, 0), settings_ui, menu_open=True) == "menu"

def test_settings_click_selects_quit_actions_when_menu_is_open() -> None:
    app = PygameApp(DummyPygame())
    settings_ui = {
        "settings_button_rect": DummyRect(False),
        "quit_to_menu_rect": DummyRect(True),
        "quit_to_desktop_rect": DummyRect(False),
        "settings_menu_rect": DummyRect(False),
    }
    assert app._handle_settings_click((0, 0), settings_ui, menu_open=True) == "quit_menu"

    settings_ui["quit_to_menu_rect"] = DummyRect(False)
    settings_ui["quit_to_desktop_rect"] = DummyRect(True)
    assert app._handle_settings_click((0, 0), settings_ui, menu_open=True) == "quit_desktop"
