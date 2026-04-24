# Catan Project

## Test runner setup (standardized)

Use the standardized test command below:

```bash
PYTHONPATH=src pytest -q
```

This is the intended and reliable test path for this repo.

## Heuristic v2 decision profiling (headless/tournaments)

`heuristic_v2_positional` profiling is optional and disabled by default. Enable it by setting
`enable_v2_profiling=True` on `TournamentConfig` (or via `TournamentSetupState.enable_v2_profiling`).

When enabled, headless tournament runs emit:

* a console summary (`V2 Profiling Summary`)
* a JSON file at `tournament_results/<tournament_id>_v2_profile.json`

Suggested repeatable scenario for profiling:

* fixed lineup of 4 `heuristic_v2_positional` bots
* `seed_blocks=1` (or `2`)
* `seat_rotation_enabled=True`
* bot delays disabled (default for headless tournament runner)
