from __future__ import annotations

import pygame

from catan.controllers.human_controller import HumanController
from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.state import InitialGameConfig
from catan.ui.pygame_ui.app import PygameApp


def main() -> None:
    state = create_initial_state(
        InitialGameConfig(
            player_ids=(1, 2, 3, 4),
            board=build_classic_19_tile_board(),
            seed=123,
        )
    )
    controllers = {1: HumanController(), 2: HumanController(), 3: HumanController(), 4: HumanController()}
    PygameApp(pygame).run(state, controllers)


if __name__ == "__main__":
    main()
