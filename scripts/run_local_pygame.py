from __future__ import annotations

import pygame

from catan.core.board_factory import build_classic_19_tile_board
from catan.core.engine import create_initial_state
from catan.core.models.state import InitialGameConfig
from catan.runners.launcher import create_controllers
from catan.ui.pygame_ui.app import PygameApp

def main() -> None:
    app = PygameApp(pygame)
    while True:
        launch_config = app.run_main_menu_and_setup()
        if launch_config is None:
            return
        state = create_initial_state(
            InitialGameConfig(
                player_ids=tuple(slot.player_id for slot in launch_config.player_slots),
                board=build_classic_19_tile_board(),
                seed=launch_config.seed,
            )
        )
        app.run(state, create_controllers(launch_config))
        if not app.return_to_main_menu:
            return


if __name__ == "__main__":
    main()
