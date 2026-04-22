from __future__ import annotations

from catan.controllers.base import Controller
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.state import InitialGameConfig
from catan.runners.debug_text_runner import DebugTextRunner


class FirstLegalController(Controller):
    def choose_action(self, observation, legal_actions):  # type: ignore[override]
        return legal_actions[0]


def main() -> None:
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3, 4),
            board=build_classic_19_tile_board(),
            seed=42,
        )
    )
    controllers = {1: FirstLegalController(), 2: FirstLegalController(), 3: FirstLegalController(), 4: FirstLegalController()}
    DebugTextRunner().run(state, controllers, max_steps=100)


if __name__ == "__main__":
    main()
