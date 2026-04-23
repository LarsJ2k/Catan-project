from __future__ import annotations

from catan.controllers.base import Controller
from catan.controllers.bot_catalog import build_bot_controller
from catan.controllers.human_controller import HumanController
from catan.runners.game_setup import ControllerType, GameLaunchConfig


def create_controllers(config: GameLaunchConfig, *, enable_bot_delay: bool = True) -> dict[int, Controller]:
    controllers: dict[int, Controller] = {}
    for slot in config.player_slots:
        if slot.controller_type == ControllerType.HUMAN:
            controllers[slot.player_id] = HumanController()
        else:
            controllers[slot.player_id] = build_bot_controller(slot.controller_type, enable_bot_delay=enable_bot_delay)
    return controllers
