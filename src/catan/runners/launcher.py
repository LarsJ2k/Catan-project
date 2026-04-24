from __future__ import annotations

from catan.controllers.base import Controller
from catan.controllers.bot_catalog import build_bot_controller_from_definition
from catan.controllers.human_controller import HumanController
from catan.runners.game_setup import ControllerType, GameLaunchConfig


def create_controllers(
    config: GameLaunchConfig,
    *,
    enable_bot_delay: bool = True,
    enable_v2_profiling: bool | None = None,
) -> dict[int, Controller]:
    controllers: dict[int, Controller] = {}
    v2_profiling_enabled = config.enable_v2_profiling if enable_v2_profiling is None else enable_v2_profiling
    for slot in config.player_slots:
        if slot.controller_key == ControllerType.HUMAN.value:
            controllers[slot.player_id] = HumanController()
        else:
            controllers[slot.player_id] = build_bot_controller_from_definition(
                slot.controller_key,
                enable_bot_delay=enable_bot_delay,
                seed=config.seed + slot.player_id,
                delay_seconds=config.bot_delay_seconds,
                enable_v2_profiling=v2_profiling_enabled,
            )
    return controllers
