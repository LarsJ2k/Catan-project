from __future__ import annotations

from pathlib import Path

from catan.controllers.bot_catalog import build_bot_controller, build_bot_controller_from_definition, list_bot_specs
from catan.controllers.bot_catalog import create_custom_bot_definition, list_bot_definitions
from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.controllers.random_bot_controller import RandomBotController
from catan.runners.game_setup import ControllerType


def test_bot_catalog_contains_random_and_heuristic_bots() -> None:
    specs = list_bot_specs()
    types = {spec.controller_type for spec in specs}

    assert ControllerType.RANDOM_BOT in types
    assert ControllerType.HEURISTIC_BOT in types
    assert ControllerType.HEURISTIC_V1_BASELINE in types


def test_bot_catalog_builds_expected_controllers() -> None:
    random_bot = build_bot_controller(ControllerType.RANDOM_BOT, enable_bot_delay=False)
    heuristic_bot = build_bot_controller(ControllerType.HEURISTIC_BOT, enable_bot_delay=False)
    heuristic_v1 = build_bot_controller(ControllerType.HEURISTIC_V1_BASELINE, enable_bot_delay=False)

    assert isinstance(random_bot, RandomBotController)
    assert isinstance(heuristic_bot, HeuristicBotController)
    assert isinstance(heuristic_v1, HeuristicV1BaselineBotController)


def test_custom_bot_persistence_and_name_validation(tmp_path: Path) -> None:
    create_custom_bot_definition(
        name="My Random Variant",
        base_bot_id="random_bot",
        description="custom",
        parameters={},
        storage_path=tmp_path / "bots.json",
    )
    loaded = list_bot_definitions(storage_path=tmp_path / "bots.json")
    assert any(bot.display_name == "My Random Variant" and not bot.is_builtin for bot in loaded)

    try:
        create_custom_bot_definition(
            name="My Random Variant",
            base_bot_id="random_bot",
            description="dup",
            parameters={},
            storage_path=tmp_path / "bots.json",
        )
        assert False, "Expected duplicate-name validation to fail."
    except ValueError as exc:
        assert "already exists" in str(exc)


def test_heuristic_defaults_and_partial_overrides_merge(tmp_path: Path) -> None:
    create_custom_bot_definition(
        name="Heuristic Partial",
        base_bot_id="heuristic_bot",
        description="partial",
        parameters={"road_to_target_weight": 0.01},
        storage_path=tmp_path / "bots.json",
    )
    created = next(bot for bot in list_bot_definitions(storage_path=tmp_path / "bots.json") if bot.display_name == "Heuristic Partial")
    assert created.parameters["road_to_target_weight"] == 0.01
    assert "settlement_base_score" in created.parameters
    assert "delay_seconds" not in created.parameters


def test_backward_compat_old_partial_custom_definition_loads(tmp_path: Path) -> None:
    path = tmp_path / "bots.json"
    path.write_text(
        '[{"bot_id":"legacy_h","display_name":"Legacy H","base_controller_type":"heuristic_bot","description":"","parameters":{"seed":7,"delay_seconds":0.0}}]',
        encoding="utf-8",
    )
    loaded = list_bot_definitions(storage_path=path)
    legacy = next(bot for bot in loaded if bot.bot_id == "legacy_h")
    assert "seed" not in legacy.parameters
    assert "delay_seconds" not in legacy.parameters
    assert "brick_value" in legacy.parameters
    controller = build_bot_controller_from_definition("legacy_h", enable_bot_delay=False, storage_path=path)
    assert isinstance(controller, HeuristicBotController)
