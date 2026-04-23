from __future__ import annotations

from catan.controllers.base import Controller
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.action import EndTurn
from catan.core.models.state import InitialGameConfig
from catan.runners.local_pygame_runner import LocalPygameRunner


class _IllegalActionController(Controller):
    def choose_action(self, observation, legal_actions):  # type: ignore[override]
        return EndTurn(player_id=1)


class _MustNotBeCalledController(Controller):
    def choose_action(self, observation, legal_actions):  # type: ignore[override]
        raise AssertionError("choose_action should not be called when no legal actions are available")


def test_tick_ignores_illegal_action_instead_of_crashing() -> None:
    runner = LocalPygameRunner()
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3, 4),
            board=build_classic_19_tile_board(seed=1),
            seed=1,
        )
    )

    after = runner.tick(state, _IllegalActionController(), player_id=1)

    assert after == state


def test_tick_skips_controller_when_no_legal_actions() -> None:
    runner = LocalPygameRunner()
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3, 4),
            board=build_classic_19_tile_board(seed=1),
            seed=1,
        )
    )

    after = runner.tick(state, _MustNotBeCalledController(), player_id=99)

    assert after == state
