from __future__ import annotations

from catan.controllers.base import Controller
from catan.controllers.bot_placeholder_controller import BotPlaceholderController
from catan.controllers.human_controller import HumanController
from catan.runners.game_setup import ControllerType, GameLaunchConfig


def create_controllers(config: GameLaunchConfig) -> dict[int, Controller]:
    controllers: dict[int, Controller] = {}
    for slot in config.player_slots:
        if slot.controller_type == ControllerType.HUMAN:
            controllers[slot.player_id] = HumanController()
        else:
            controllers[slot.player_id] = BotPlaceholderController()
    return controllers
