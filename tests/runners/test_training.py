from __future__ import annotations

from catan.controllers.bot_catalog import get_bot_definition, list_bot_definitions
from catan.runners.game_setup import TrainingSetupState
from catan.runners.training import (
    TrainingConfig,
    generate_balanced_screening_matches,
    generate_temporary_candidates,
    mutable_numeric_parameter_keys,
    promote_training_candidates,
)


def test_multi_parent_candidate_generation_is_deterministic_and_unique_ids() -> None:
    config = TrainingConfig(
        parent_bot_ids=("heuristic_bot", "heuristic_v1_1"),
        population_per_parent=3,
        mutation_modifier=0.7,
        mutation_seed=99,
        candidate_prefix="mut",
        games_per_bot=8,
        tournament_seed=1,
    )
    first = generate_temporary_candidates(config)
    second = generate_temporary_candidates(config)

    assert first == second
    assert len(first) == 6
    assert len({candidate.temporary_id for candidate in first}) == 6
    assert {candidate.parent_bot_id for candidate in first} == {"heuristic_bot", "heuristic_v1_1"}


def test_mutation_respects_modifier_range_and_non_mutable_keys() -> None:
    parent = get_bot_definition("heuristic_bot")
    assert parent is not None

    config = TrainingConfig(
        parent_bot_ids=("heuristic_bot",),
        population_per_parent=4,
        mutation_modifier=0.7,
        mutation_seed=7,
        candidate_prefix="mut",
        games_per_bot=8,
        tournament_seed=1,
    )
    candidates = generate_temporary_candidates(config)
    assert candidates
    mutable_keys = set(mutable_numeric_parameter_keys(parent))
    for candidate in candidates:
        assert candidate.metadata["temporary"] is True
        assert candidate.metadata["parent_bot_id"] == "heuristic_bot"
        for key, value in parent.parameters.items():
            mutated = candidate.parameters[key]
            if key in {"seed", "delay_seconds", "candidate_count"}:
                assert mutated == value
            if key in mutable_keys and isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0:
                low = value * 0.7
                high = value * 1.3
                assert low <= float(mutated) <= high


def test_balanced_screening_schedule_is_approximately_balanced() -> None:
    candidate_ids = tuple(f"tmp_{idx}" for idx in range(8))
    matches = generate_balanced_screening_matches(candidate_ids, games_per_bot=12, base_seed=5)

    games_per_bot = {candidate: 0 for candidate in candidate_ids}
    seat_counts = {candidate: [0, 0, 0, 0] for candidate in candidate_ids}
    for match in matches:
        for seat, bot_id in enumerate(match.seat_order):
            games_per_bot[bot_id] += 1
            seat_counts[bot_id][seat] += 1

    assert abs(len(matches) - (len(candidate_ids) * 12 / 4)) <= 4
    for candidate in candidate_ids:
        assert abs(games_per_bot[candidate] - 12) <= 3
        assert max(seat_counts[candidate]) - min(seat_counts[candidate]) <= 3


def test_training_candidates_not_persisted_unless_promoted(tmp_path, monkeypatch) -> None:
    from catan.controllers import bot_catalog as catalog_module

    monkeypatch.setattr(catalog_module, "_BOT_CATALOG_FILE", tmp_path / "custom_bots.json")
    before = list_bot_definitions(storage_path=tmp_path / "custom_bots.json")

    config = TrainingConfig(
        parent_bot_ids=("heuristic_v1_1",),
        population_per_parent=4,
        mutation_modifier=0.7,
        mutation_seed=17,
        candidate_prefix="mut",
        games_per_bot=2,
        tournament_seed=3,
    )
    candidates = generate_temporary_candidates(config)
    assert candidates
    after = list_bot_definitions(storage_path=tmp_path / "custom_bots.json")
    assert len(after) == len(before)

    promoted = promote_training_candidates(
        candidates=candidates,
        promoted_names_by_id={candidates[0].temporary_id: "Promoted Candidate"},
    )
    assert len(promoted) == 1

    final_defs = list_bot_definitions(storage_path=tmp_path / "custom_bots.json")
    promoted_def = next(defn for defn in final_defs if defn.display_name == "Promoted Candidate")
    assert promoted_def.metadata["source"] == "training"
    assert promoted_def.metadata["parent_bot_id"] == candidates[0].parent_bot_id


def test_promotion_rejects_duplicate_or_empty_names() -> None:
    config = TrainingConfig(
        parent_bot_ids=("heuristic_bot",),
        population_per_parent=4,
        mutation_modifier=0.7,
        mutation_seed=17,
        candidate_prefix="mut",
        games_per_bot=1,
        tournament_seed=3,
    )
    candidates = generate_temporary_candidates(config)

    try:
        promote_training_candidates(
            candidates=candidates,
            promoted_names_by_id={candidates[0].temporary_id: "   "},
        )
        assert False, "Expected empty name failure"
    except ValueError:
        pass


def test_training_setup_state_builds_config_for_multi_parent() -> None:
    state = TrainingSetupState().toggle_parent_bot("heuristic_bot").toggle_parent_bot("heuristic_v1_1")
    config = state.to_training_config()
    assert config is not None
    assert config.parent_bot_ids == ("heuristic_bot", "heuristic_v1_1")
