from __future__ import annotations

import json

from catan.controllers.bot_catalog import create_custom_bot_definition, delete_custom_bot_definition, get_bot_definition, list_bot_definitions
from catan.runners.game_setup import ControllerType, TournamentSetupState, available_controller_types


def test_new_bot_copy_starts_from_selected_without_mutating_selected(tmp_path) -> None:
    base = get_bot_definition("random_bot")
    assert base is not None
    copied_params = dict(base.parameters)

    created = create_custom_bot_definition(
        name="Random Fast",
        base_bot_id=base.bot_id,
        description="faster random",
        parameters=copied_params,
        storage_path=tmp_path / "custom_bots.json",
    )

    assert created.base_controller_type == base.base_controller_type
    assert "delay_seconds" not in created.parameters
    assert "delay_seconds" not in base.parameters


def test_empty_name_rejected(tmp_path) -> None:
    try:
        create_custom_bot_definition(
            name="   ",
            base_bot_id="random_bot",
            description="",
            parameters={},
            storage_path=tmp_path / "custom_bots.json",
        )
        assert False, "Expected empty name to be rejected"
    except ValueError as exc:
        assert "required" in str(exc)


def test_setup_and_tournament_see_saved_custom_bots(tmp_path, monkeypatch) -> None:
    from catan.controllers import bot_catalog as catalog_module

    monkeypatch.setattr(catalog_module, "_BOT_CATALOG_FILE", tmp_path / "custom_bots.json")
    create_custom_bot_definition(
        name="Heuristic Seeded",
        base_bot_id="heuristic_bot",
        description="seeded",
        parameters={"seed": 7, "delay_seconds": 0.0},
        storage_path=tmp_path / "custom_bots.json",
    )

    created = next(bot for bot in list_bot_definitions(storage_path=tmp_path / "custom_bots.json") if bot.display_name == "Heuristic Seeded")
    assert "seed" not in created.parameters
    assert "delay_seconds" not in created.parameters
    options = available_controller_types()
    assert ControllerType.HUMAN.value in options
    builtin_ids = {
        ControllerType.HUMAN.value,
        "random_bot",
        "heuristic_bot",
        "heuristic_v1_baseline",
        "heuristic_v1_fixed",
        "heuristic_v1_1",
    }
    assert any(option not in builtin_ids for option in options)

    custom_id = next(option for option in options if option not in builtin_ids)
    tournament_state = TournamentSetupState(selected_bots=()).toggle_bot(custom_id)
    assert custom_id in tournament_state.selected_bots


def test_heuristic_params_are_visible_and_copy_editable(tmp_path) -> None:
    base = get_bot_definition("heuristic_bot")
    assert base is not None
    assert "brick_value" in base.parameters
    assert "road_to_target_weight" in base.parameters

    edited = dict(base.parameters)
    edited["road_to_target_weight"] = 0.01
    edited["settlement_base_score"] = 350.0
    created = create_custom_bot_definition(
        name="Heuristic Aggressive Settlements",
        base_bot_id=base.bot_id,
        description="edited heuristic weights",
        parameters=edited,
        storage_path=tmp_path / "custom_bots.json",
    )

    assert created.parameters["road_to_target_weight"] == 0.01
    assert created.parameters["settlement_base_score"] == 350.0
    loaded = get_bot_definition(created.bot_id, storage_path=tmp_path / "custom_bots.json")
    assert loaded is not None
    assert loaded.parameters["road_to_target_weight"] == 0.01
    assert loaded.parameters["settlement_base_score"] == 350.0


def test_delete_custom_bot_definition_removes_only_custom_bot(tmp_path) -> None:
    storage_path = tmp_path / "custom_bots.json"
    created = create_custom_bot_definition(
        name="Delete Me",
        base_bot_id="random_bot",
        description="to remove",
        parameters={},
        storage_path=storage_path,
    )

    assert delete_custom_bot_definition(created.bot_id, storage_path=storage_path) is True
    assert get_bot_definition(created.bot_id, storage_path=storage_path) is None
    assert get_bot_definition("random_bot", storage_path=storage_path) is not None


def test_delete_custom_bot_definition_returns_false_for_missing_or_builtin(tmp_path) -> None:
    storage_path = tmp_path / "custom_bots.json"
    assert delete_custom_bot_definition("missing_bot", storage_path=storage_path) is False
    assert delete_custom_bot_definition("random_bot", storage_path=storage_path) is False


def test_loading_custom_bots_prunes_builtin_id_collisions(tmp_path) -> None:
    storage_path = tmp_path / "custom_bots.json"
    storage_path.write_text(
        json.dumps(
            [
                {
                    "bot_id": "heuristic_v1_fixed",
                    "display_name": "Heuristic v1 Fixed",
                    "base_controller_type": "heuristic_v1_fixed",
                    "description": "legacy duplicate of built-in",
                    "parameters": {},
                },
                {
                    "bot_id": "custom_heuristic",
                    "display_name": "Custom Heuristic",
                    "base_controller_type": "heuristic_bot",
                    "description": "valid custom bot",
                    "parameters": {},
                },
            ]
        ),
        encoding="utf-8",
    )

    definitions = list_bot_definitions(storage_path=storage_path)
    custom_ids = {definition.bot_id for definition in definitions if not definition.is_builtin}
    assert custom_ids == {"custom_heuristic"}

    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert [entry["bot_id"] for entry in persisted] == ["custom_heuristic"]
