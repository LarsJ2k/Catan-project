from __future__ import annotations

from dataclasses import dataclass

from catan.controllers.human_controller import HumanController
from catan.core.engine import create_initial_state
from catan.core.models.board import Board, Edge, Tile
from catan.core.models.enums import TerrainType
from catan.core.models.state import InitialGameConfig
from catan.ui.pygame_ui import app as app_module


class FakePygame:
    QUIT = 256
    KEYDOWN = 257
    VIDEORESIZE = 258
    K_F11 = 122
    RESIZABLE = 1
    FULLSCREEN = 2

    def __init__(self) -> None:
        self.inited = False
        self.font_inited = False

        class _Font:
            def __init__(inner_self, outer) -> None:
                inner_self.outer = outer

            def init(inner_self) -> None:
                inner_self.outer.font_inited = True

        class _Display:
            @staticmethod
            def set_caption(_caption: str) -> None:
                return None

            @staticmethod
            def set_mode(_size, _flags=0):
                return _Screen()

            @staticmethod
            def flip() -> None:
                return None

            @staticmethod
            def Info():
                return type("Info", (), {"current_w": 1280, "current_h": 720})()

        class _Screen:
            @staticmethod
            def get_size() -> tuple[int, int]:
                return (1200, 820)

        class _Clock:
            @staticmethod
            def tick(_fps: int) -> None:
                return None

        class _Time:
            @staticmethod
            def Clock() -> _Clock:
                return _Clock()

        class _Event:
            called = False

            @classmethod
            def get(cls):
                if not cls.called:
                    cls.called = True
                    return [type("Evt", (), {"type": FakePygame.QUIT})()]
                return []

        class _Mouse:
            @staticmethod
            def get_pos() -> tuple[int, int]:
                return (0, 0)

        self.font = _Font(self)
        self.display = _Display()
        self.time = _Time()
        self.event = _Event()
        self.mouse = _Mouse()

    def init(self) -> None:
        self.inited = True

    @staticmethod
    def quit() -> None:
        return None


class StubRenderer:
    def __init__(self, pg) -> None:
        assert pg.inited is True
        assert pg.font_inited is True

    @dataclass
    class _Drawn:
        roll_button_rect: object = object()
        end_turn_button_rect: object = object()

    def render(self, *args, **kwargs):
        return self._Drawn()


class StubInputMapper:
    def __init__(self, pg) -> None:
        assert pg.inited is True

    class _Mapped:
        action = None
        status = None

    class _Hover:
        node_id = None
        edge_id = None

    def get_hover_target(self, *args, **kwargs):
        return self._Hover()

    def map_event(self, *args, **kwargs):
        return self._Mapped()


def make_state():
    edges = tuple(Edge(id=i, node_a=i, node_b=(i + 1) % 8) for i in range(8))
    board = Board(
        nodes=tuple(range(8)),
        edges=edges,
        tiles=(
            Tile(id=0, terrain=TerrainType.FOREST, number_token=6),
            Tile(id=1, terrain=TerrainType.HILLS, number_token=8),
            Tile(id=2, terrain=TerrainType.FIELDS, number_token=5),
        ),
        node_to_adjacent_tiles={0: (0,), 1: (0,), 2: (1,), 3: (1,), 4: (2,), 5: (2,), 6: (2,), 7: ()},
        node_to_adjacent_edges={0: (0, 7), 1: (0, 1), 2: (1, 2), 3: (2, 3), 4: (3, 4), 5: (4, 5), 6: (5, 6), 7: (6, 7)},
        edge_to_adjacent_nodes={i: (i, (i + 1) % 8) for i in range(8)},
    )
    return create_initial_state(InitialGameConfig(player_ids=(1, 2), board=board, seed=123))


def test_pygame_init_happens_before_renderer_construction(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "PygameRenderer", StubRenderer)
    monkeypatch.setattr(app_module, "PygameInputMapper", StubInputMapper)

    app = app_module.PygameApp(FakePygame())
    state = make_state()
    controllers = {1: HumanController(), 2: HumanController()}
    app.run(state, controllers)
