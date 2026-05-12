# Catan Cleanup Plan

## Purpose
This document converts the architecture audit into an execution plan that improves maintainability **without changing game rules/behavior** during initial phases.

---

## Current Architecture Problems

1. **God-object UI application loop**
   - `PygameApp` handles menu flow, setup flow, tournament flow, training flow, bot lab CRUD, rendering orchestration, input handling, and thread/progress integration in one file/function.
   - Main risk: high cognitive load and accidental regressions when touching unrelated features.

2. **Monolithic game engine dispatch/rules file**
   - `core/engine.py` contains broad legal-action generation and action-application branching.
   - Main risk: rules changes are hard to isolate and test incrementally.

3. **Duplication in interaction paths**
   - Tournament config logic is duplicated between mouse and keyboard event branches.
   - Main risk: drift where one input path behaves differently.

4. **Weakly bounded state mutation/ownership**
   - Mutable nested state structures are touched across core engine, runner, UI flow objects, and controllers.
   - Main risk: side effects and hard-to-trace bugs.

5. **Legality enforcement split across layers**
   - Engine is authoritative, but controller/runner handling can suppress or loosely pre-validate invalid intents.
   - Main risk: hidden invalid-action behavior that is hard to diagnose.

6. **Large bot/controller family with variant sprawl**
   - Multiple large heuristic controller files likely share structure but diverge over time.
   - Main risk: duplicated logic and inconsistent strategy updates.

---

## Target Architecture

### 1) Layer boundaries
- **Core Domain (rules/state transitions):**
  - Pure game logic (`core/*`) with explicit action handling modules by concern/phase.
- **Application Services (orchestration):**
  - Runner/services that connect controllers + engine + telemetry.
- **Interface Adapters:**
  - Pygame UI event translation + rendering.
  - Bot/human controllers as action providers.

### 2) Design goals
- Single authoritative legality check in engine, with clear pre-validation contracts.
- Smaller, composable modules for setup/tournament/training UI workflows.
- Shared helper functions for duplicated interaction behaviors.
- Characterization tests around all fragile seams before structural refactors.
- Observable failures (log/metrics) for illegal actions instead of silent swallowing.

### 3) Non-goals for early phases
- No game-balance tuning.
- No rules changes.
- No broad rewrite of rendering visuals.

---

## Cleanup Phases

## Phase 0 — Safety Net Expansion (Tests First)

### Objectives
- Lock in current behavior around risky seams before refactors.

### Files involved
- `tests/runners/test_local_pygame_runner.py`
- `tests/controllers/test_human_controller.py`
- `tests/ui/test_menu_setup_flow.py`
- `tests/ui/test_ui_refactor_state.py`
- `tests/core/test_engine_mvp.py`

### Tests needed before phase work
1. Runner illegal action handling characterization:
   - when controller returns invalid action, state remains stable (current behavior), and diagnostic expectation is defined.
2. Human controller legal-intent matching:
   - trade/discard queue behavior against varying legal action sets.
3. Tournament setup parity:
   - mouse path and keyboard path produce equivalent state transitions for format/seed/export toggles.
4. Engine action dispatch completeness smoke test:
   - ensure each expected action type routes through valid application path or explicit illegal error.

### Manual playtest checklist after phase
- Start game via menu and complete setup with mixed human/bot players.
- Trigger tournament setup and toggle all options via both mouse and keyboard.
- Run one short tournament and verify progress UI updates until completion.
- Validate no crashes when clicking rapidly between screens.

---

## Phase 1 — UI Orchestration Decomposition (`app.py`)

### Objectives
- Break `PygameApp` into coherent screen handlers with stable interfaces.
- Keep behavior identical.

### Files involved
- Primary:
  - `src/catan/ui/pygame_ui/app.py`
- New modules (suggested):
  - `src/catan/ui/pygame_ui/screens/main_menu.py`
  - `src/catan/ui/pygame_ui/screens/game_setup.py`
  - `src/catan/ui/pygame_ui/screens/tournament_setup.py`
  - `src/catan/ui/pygame_ui/screens/training_setup.py`
  - `src/catan/ui/pygame_ui/screens/bot_lab.py`
- Supporting:
  - `src/catan/ui/pygame_ui/input_mapper.py`
  - `src/catan/runners/game_setup.py`

### Tests needed before phase work
- Existing Phase 0 tests green.
- Add targeted tests for extracted screen handler pure functions:
  - event -> state transition reducers for each screen.

### Manual playtest checklist after phase
- Navigate every screen: Main Menu -> Game Setup -> Back.
- Add/remove players repeatedly and verify selected controller behavior.
- Use fixed and random seed toggles.
- Bot Lab create/delete workflow check.
- Training screen form entry + validation + run button behavior.

---

## Phase 2 — Remove Duplicated Tournament Interaction Logic

### Objectives
- Centralize tournament option updates so mouse and keyboard share one implementation.

### Files involved
- `src/catan/ui/pygame_ui/app.py` (or extracted `tournament_setup.py` from Phase 1)
- `src/catan/runners/game_setup.py` (if state helper methods are needed)
- `tests/ui/test_menu_setup_flow.py`

### Tests needed before phase work
- Input parity tests proving shared behavior across interaction modes.
- Boundary tests for seed/game count increments/decrements (min values, format-dependent behavior).

### Manual playtest checklist after phase
- Configure tournament entirely by mouse; note resulting options.
- Repeat same config entirely by keyboard; verify exact match.
- Run tournament in each format once (fixed lineup, round robin, balanced sample).

---

## Phase 3 — Runner/Controller Legality & Observability Hardening

### Objectives
- Keep engine as source of truth while making invalid-action paths explicit/observable.

### Files involved
- `src/catan/runners/local_pygame_runner.py`
- `src/catan/controllers/human_controller.py`
- `src/catan/controllers/random_bot_controller.py`
- `src/catan/controllers/base.py`
- `tests/runners/test_local_pygame_runner.py`
- `tests/controllers/test_human_controller.py`

### Tests needed before phase work
- Characterization tests for current invalid-intent handling.
- New tests for telemetry/logging hooks (or callback counters) on illegal actions.
- Regression tests to ensure gameplay flow remains non-blocking for human input wait states.

### Manual playtest checklist after phase
- Perform illegal click/intent sequences in UI and confirm graceful handling.
- Confirm no freeze while waiting for human action.
- Verify bots still act each turn and game completes.

---

## Phase 4 — Engine Modularization by Action/Phase (High Risk)

### Objectives
- Split monolithic `engine.py` into action/phase modules while preserving exact behavior.

### Files involved
- Primary:
  - `src/catan/core/engine.py`
- New modules (suggested):
  - `src/catan/core/engine/legal_actions.py`
  - `src/catan/core/engine/apply_actions.py`
  - `src/catan/core/engine/phases/setup.py`
  - `src/catan/core/engine/phases/turn.py`
  - `src/catan/core/engine/phases/trade.py`
  - `src/catan/core/engine/phases/dev_cards.py`
  - `src/catan/core/engine/phases/robber.py`
- Tests:
  - `tests/core/test_engine_mvp.py`
  - `tests/core/test_invariants.py`
  - `tests/core/test_player_trade.py`
  - `tests/core/test_dev_cards.py`
  - `tests/core/test_robber_flow.py`

### Tests needed before phase work
- Full core test suite baseline green.
- Add golden-state transition snapshots for representative actions.
- Add invariants checks after each action application in parameterized scenarios.

### Manual playtest checklist after phase
- Full game with only bots to completion.
- Human-vs-bot game through robber/trade/dev-card interactions.
- Verify victory point progression and game-over detection.

---

## Phase 5 — Bot Family Consolidation (After Core Stabilization)

### Objectives
- Extract shared heuristics scaffolding and keep per-bot strategy differences explicit.

### Files involved
- `src/catan/controllers/heuristic_bot_controller.py`
- `src/catan/controllers/heuristic_v1_baseline_bot_controller.py`
- `src/catan/controllers/heuristic_v1_1_bot_controller.py`
- `src/catan/controllers/heuristic_v2_positional_bot_controller.py`
- `src/catan/controllers/heuristic_v2_1_strategic_bot_controller.py`
- `src/catan/controllers/heuristic_v3_lookahead_bot_controller.py`
- `src/catan/controllers/heuristic_v2_position_evaluator.py`
- `src/catan/controllers/heuristic_strategic_helpers.py`
- `tests/controllers/test_*.py` for all heuristic families

### Tests needed before phase work
- Behavioral baseline tournaments for each bot family (win-rate/profile snapshots with fixed seeds).
- Decision legality tests for all bots across tricky turn states.
- Smoke tests for performance budget (decision latency bounds).

### Manual playtest checklist after phase
- Run quick tournament including all built-in bots.
- Confirm no bot hangs or returns empty action.
- Spot-check strategic behavior differences still appear (not homogenized).

---

## Suggested Refactor Sequence (Safest Order)
1. Phase 0 (tests)
2. Phase 1 (decompose app)
3. Phase 2 (dedupe tournament interaction)
4. Phase 3 (legality observability)
5. Phase 4 (engine modularization)
6. Phase 5 (bot consolidation)

---

## Explicit Out-of-Scope Items

1. **Game rules changes** (resource costs, victory conditions, development card behavior).
2. **Balance tuning** for bot strategies or trade heuristics.
3. **UI redesign/visual overhaul** of renderer aesthetics.
4. **Networked multiplayer** or online services.
5. **Persistence/storage redesign** beyond minimal refactor support.
6. **Performance optimization projects** not required for safety/maintainability.
7. **New gameplay features** (expansions, house rules, plugins) during cleanup phases.

---

## Exit Criteria

Cleanup is considered successful when:
- UI orchestration is split into maintainable modules with stable tests.
- Engine logic is modularized with unchanged externally observable behavior.
- Duplicated interaction logic is removed.
- Invalid action flows are explicit and diagnosable.
- Bot family structure is easier to evolve without cross-file duplication.
- Manual playtest checklist passes after each phase.
