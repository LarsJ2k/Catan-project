from __future__ import annotations

from catan.controllers.bot_catalog import build_bot_controller, list_bot_specs
from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.controllers.random_bot_controller import RandomBotController
from catan.runners.game_setup import ControllerType


def test_bot_catalog_contains_random_and_heuristic_bots() -> None:
    specs = list_bot_specs()
    types = {spec.controller_type for spec in specs}

    assert ControllerType.RANDOM_BOT in types
    assert ControllerType.HEURISTIC_BOT in types


def test_bot_catalog_builds_expected_controllers() -> None:
    random_bot = build_bot_controller(ControllerType.RANDOM_BOT, enable_bot_delay=False)
    heuristic_bot = build_bot_controller(ControllerType.HEURISTIC_BOT, enable_bot_delay=False)

    assert isinstance(random_bot, RandomBotController)
    assert isinstance(heuristic_bot, HeuristicBotController)
