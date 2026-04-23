from __future__ import annotations

from dataclasses import replace

from catan.controllers.human_controller import HumanController
from catan.core.models.action import BuildRoad, BuildSettlement, MoveRobber
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import DevelopmentCardType, GamePhase, ResourceType, TerrainType, TurnStep
from catan.core.models.state import GameState, PlacedPieces, PlayerState, SetupState, TurnState
from catan.ui.pygame_ui.app import PygameApp
from catan.ui.pygame_ui.renderer import PygameRenderer


class DummyRect:
    def __init__(self, hit: bool = False):
        self._hit = hit

    def collidepoint(self, _pos) -> bool:
        return self._hit


class DrawRect:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.width = w
        self.height = h


class DummyPygame:
    pass


class DummySurface:
    def get_width(self) -> int:
        return 20


def make_state() -> GameState:
    board = Board(
        nodes=(0, 1, 2),
        edges=(Edge(id=0, node_a=0, node_b=1), Edge(id=1, node_a=1, node_b=2)),
        tiles=(
            Tile(id=0, terrain=TerrainType.FIELDS, number_token=6),
            Tile(id=1, terrain=TerrainType.FOREST, number_token=9),
            Tile(id=2, terrain=TerrainType.HILLS, number_token=3),
            Tile(id=3, terrain=TerrainType.MOUNTAINS, number_token=8),
            Tile(id=4, terrain=TerrainType.FIELDS, number_token=10),
        ),
        node_to_adjacent_tiles={0: (0, 1, 2), 1: (3, 4), 2: (4,)},
        node_to_adjacent_edges={0: (0,), 1: (0, 1), 2: (1,)},
        edge_to_adjacent_nodes={0: (0, 1), 1: (1, 2)},
        ports=(),
        node_to_ports={0: (), 1: (), 2: ()},
    )
    players = {
        pid: PlayerState(
            player_id=pid,
            resources={r: pid for r in ResourceType},
            dev_cards={
                DevelopmentCardType.KNIGHT: pid % 2,
                DevelopmentCardType.ROAD_BUILDING: 0,
                DevelopmentCardType.YEAR_OF_PLENTY: 0,
                DevelopmentCardType.MONOPOLY: 0,
                DevelopmentCardType.VICTORY_POINT: 0,
            },
        )
        for pid in (1, 2, 3, 4)
    }
    return GameState(
        board=board,
        players=players,
        phase=GamePhase.MAIN_TURN,
        setup=SetupState(order=[1, 2, 3, 4]),
        turn=TurnState(current_player=2, step=TurnStep.ACTIONS),
        placed=PlacedPieces(),
        robber_tile_id=0,
        rng_state=1,
    )


def test_spectator_mode_state_selection() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()

    assert app._is_spectator_mode(state, {1: object(), 2: object(), 3: object(), 4: object()}) is True
    assert app._is_spectator_mode(state, {1: HumanController(), 2: object(), 3: object(), 4: object()}) is False


def test_speed_button_state_changes() -> None:
    app = PygameApp(DummyPygame())
    rects = {0.0: DummyRect(False), 1.0: DummyRect(False), 2.0: DummyRect(True), 4.0: DummyRect(False)}

    assert app._match_speed_button((0, 0), rects) == 2.0


def test_human_readable_action_labels_for_spectator() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()

    settlement = app._action_label(BuildSettlement(player_id=1, node_id=0), state)
    road = app._action_label(BuildRoad(player_id=1, edge_id=1), state)
    robber = app._action_label(MoveRobber(player_id=1, tile_id=0), state)

    assert settlement == "Settlement 6-9-3"
    assert road == "Road toward 8-10"
    assert robber == "Robber → 6 (Wheat)"


def test_decision_panel_behavior_heuristic_vs_random() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()

    class HeuristicBot:
        def get_last_decision(self):
            return {
                "kind": "heuristic",
                "chosen_action": BuildSettlement(player_id=2, node_id=0),
                "top_candidates": [
                    (BuildSettlement(player_id=2, node_id=0), 0.9),
                    (BuildRoad(player_id=2, edge_id=1), 0.8),
                ],
            }

    class RandomBot:
        def get_last_decision(self):
            return {
                "kind": "random",
                "chosen_action": BuildRoad(player_id=2, edge_id=1),
                "legal_action_count": 12,
                "message": "Random choice from 12 legal actions",
            }

    heuristic_ui = app._spectator_decision_ui(HeuristicBot(), state)
    random_ui = app._spectator_decision_ui(RandomBot(), state)

    assert heuristic_ui["chosen_line"] == "Settlement 6-9-3"
    assert "+0.90" in heuristic_ui["candidate_lines"][0]
    assert random_ui["fallback_message"] == "Random choice from 12 legal actions"


def test_decision_panel_shows_scored_candidates_for_v1_heuristic_payload() -> None:
    app = PygameApp(DummyPygame())
    state = make_state()

    class HeuristicV1Bot:
        def get_last_decision(self):
            return {
                "kind": "heuristic_v1_baseline",
                "chosen_action": BuildSettlement(player_id=2, node_id=0),
                "top_candidates": [
                    (BuildSettlement(player_id=2, node_id=0), 124.8),
                    (BuildRoad(player_id=2, edge_id=1), 122.1),
                    (MoveRobber(player_id=2, tile_id=0), 98.0),
                ],
            }

    ui = app._spectator_decision_ui(HeuristicV1Bot(), state)

    assert ui["chosen_line"] == "Settlement 6-9-3"
    assert len(ui["candidate_lines"]) == 3
    assert "+124.80" in ui["candidate_lines"][0]


def test_spectator_dashboard_shows_all_players_and_active_outline() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    renderer._player_color = PygameRenderer._player_color.__get__(renderer, PygameRenderer)
    rect_calls: list[tuple] = []

    class Draw:
        @staticmethod
        def rect(_screen, color, rect, width=0, border_radius=0):
            rect_calls.append((color, width))

        @staticmethod
        def line(*_args, **_kwargs):
            return None

    class DummyFont:
        def render(self, *_args, **_kwargs):
            return DummySurface()

    class DummyScreen:
        def blit(self, *_args, **_kwargs):
            return None

    class PG:
        draw = Draw()

        @staticmethod
        def Rect(*args):
            return DrawRect(*args)

    renderer.pg = PG()
    renderer.font = DummyFont()
    renderer.small_font = DummyFont()
    cards: list[ResourceType] = []

    def capture_card(_screen, _x, _y, _w, _h, resource, _amount, *, compact=False):
        if compact:
            cards.append(resource)

    renderer._draw_resource_card = capture_card
    state = make_state()

    renderer._draw_spectator_dashboard(DummyScreen(), state, active_player=2, panel_x=900, height=700, bottom_h=220, spectator_data={})

    assert len(cards) == 20
    highlighted = [call for call in rect_calls if call[0] == renderer._player_color(2) and call[1] == 3]
    assert len(highlighted) >= 1
    drawn_dev_cards = [call for call in rect_calls if call[0] == (78, 88, 112)]
    assert len(drawn_dev_cards) == 2


def test_scoreboard_vp_text_can_reveal_hidden_vp_for_all_players_in_spectator_mode() -> None:
    renderer = PygameRenderer.__new__(PygameRenderer)
    state = make_state()
    state.players[1].victory_points = 4
    state.players[1].dev_cards[DevelopmentCardType.VICTORY_POINT] = 2

    vp_text = renderer._scoreboard_vp_text(
        state,
        player_id=1,
        reveal_current_hidden_vp=False,
        reveal_all_hidden_vp=True,
    )

    assert vp_text == "VP 4(6)"
