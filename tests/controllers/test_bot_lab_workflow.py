from __future__ import annotations

from catan.controllers.bot_catalog import create_custom_bot_definition, get_bot_definition, list_bot_definitions
from catan.runners.game_setup import ControllerType, TournamentSetupState, available_controller_types


def test_new_bot_copy_starts_from_selected_without_mutating_selected(tmp_path) -> None:
    base = get_bot_definition("random_bot")
    assert base is not None
    copied_params = dict(base.parameters)
    copied_params["delay_seconds"] = 0.25

    created = create_custom_bot_definition(
        name="Random Fast",
        base_bot_id=base.bot_id,
        description="faster random",
        parameters=copied_params,
        storage_path=tmp_path / "custom_bots.json",
    )

    assert created.base_controller_type == base.base_controller_type
    assert created.parameters["delay_seconds"] == 0.25
    assert base.parameters["delay_seconds"] == 1.2


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

    assert any(bot.display_name == "Heuristic Seeded" for bot in list_bot_definitions(storage_path=tmp_path / "custom_bots.json"))
    options = available_controller_types()
    assert ControllerType.HUMAN.value in options
    builtin_ids = {ControllerType.HUMAN.value, "random_bot", "heuristic_bot", "heuristic_v1_baseline"}
    assert any(option not in builtin_ids for option in options)

    custom_id = next(option for option in options if option not in builtin_ids)
    tournament_state = TournamentSetupState(selected_bots=()).toggle_bot(custom_id)
    assert custom_id in tournament_state.selected_bots
