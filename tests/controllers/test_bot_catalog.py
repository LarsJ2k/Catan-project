from __future__ import annotations

from pathlib import Path

from catan.controllers.bot_catalog import build_bot_controller, list_bot_specs
from catan.controllers.bot_catalog import create_custom_bot_definition, list_bot_definitions
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


def test_custom_bot_persistence_and_name_validation(tmp_path: Path) -> None:
    create_custom_bot_definition(
        name="My Random Variant",
        base_bot_id="random_bot",
        description="custom",
        parameters={"seed": "", "delay_seconds": 0.4},
        storage_path=tmp_path / "bots.json",
    )
    loaded = list_bot_definitions(storage_path=tmp_path / "bots.json")
    assert any(bot.display_name == "My Random Variant" and not bot.is_builtin for bot in loaded)

    try:
        create_custom_bot_definition(
            name="My Random Variant",
            base_bot_id="random_bot",
            description="dup",
            parameters={"seed": "", "delay_seconds": 0.5},
            storage_path=tmp_path / "bots.json",
        )
        assert False, "Expected duplicate-name validation to fail."
    except ValueError as exc:
        assert "already exists" in str(exc)
