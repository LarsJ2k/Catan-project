# Architecture Audit (Strict / Incremental)

## 1) Current project structure summary

- `src/catan/core/`: game-domain engine and immutable state models (`engine.py`, `models/*`, `observer.py`, `board_factory.py`).
- `src/catan/controllers/`: human + bot controllers, including many heuristic generations (`heuristic_*`) and parameter helpers.
- `src/catan/ui/pygame_ui/`: pygame rendering/input/menu app (`app.py`, `renderer.py`, `input_mapper.py`, `layout.py`).
- `src/catan/runners/`: launchers and orchestration for local UI, tournaments, training, and debug/headless flows.
- `tests/`: broad coverage for core/controller/runner/ui behavior, but mostly behavior-level tests; limited architectural seam tests.

## 2) Main architecture problems

1. **God-object UI application**
   - `src/catan/ui/pygame_ui/app.py` is very large (~2.3k LOC) and owns menu flow, event loop, setup state mutation, tournament execution triggering, training flow state, bot-lab CRUD flow, and rendering coordination.
   - This violates single responsibility and makes change-risk high.

2. **Monolithic rule engine**
   - `src/catan/core/engine.py` is also very large (~1.2k LOC) and centralizes action legality, action application dispatch, and many detailed rule branches.
   - The `if isinstance(...)` dispatch pattern is long and brittle for extension.

3. **Layer boundary leakage (UI/runners/controllers/core mixed at runtime edges)**
   - UI imports runner/training/tournament/bot-catalog concerns directly, instead of going through a thin application service boundary.
   - Runners sometimes absorb policy decisions (e.g., observation mode choice in `LocalPygameRunner`) that should be explicit strategy/config.

4. **Heuristic controller family divergence risk**
   - Multiple heuristic controllers carry near-duplicate scoring plumbing with slight policy changes.
   - Small bug fixes must be repeated across many files; behavior drift is likely.

## 3) Examples of UI/core coupling

- `PygameApp` imports `get_legal_actions` directly from `core.engine` and many core action/model enums; UI logic is aware of domain internals instead of consuming a narrow facade.
- `PygameApp` imports and coordinates `TrainingRunner`, `HeadlessTournamentRunner`, bot catalog CRUD, and game setup state in one class, coupling UI directly to orchestration and persistence-like concerns.
- `LocalPygameRunner.tick` chooses debug observation mode based on whether controller is `HumanController` (`debug=not isinstance(controller, HumanController)`), coupling runner control flow to concrete controller type.

## 4) Examples of duplicated logic

- Repeated heuristic constants and maps across controllers (token pip scores, terrain/resource maps, cost dictionaries).
- Repeated `choose_action` scaffolding in heuristic generations (candidate prep, discard override, delay, scoring loop, decision recording).
- Repeated score-note bookkeeping and near-identical decision report structures across heuristic variants.
- Setup-state style immutable “copy constructor” methods in `GameSetupState` / `TournamentSetupState` are verbose and repetitive (high edit surface, easy to miss fields).

## 5) Risky files/functions

- **Very high risk**: `src/catan/ui/pygame_ui/app.py`
  - Large mutable state surface and deeply nested event-handling branches.
  - Any UI feature change can regress unrelated flows.

- **Very high risk**: `src/catan/core/engine.py`
  - Rule logic density and long dispatch chains increase accidental rule regression risk.

- **High risk**: heuristic family files in `src/catan/controllers/heuristic_*`
  - Logic cloning + incremental divergence.

- **Medium risk**: `src/catan/runners/game_setup.py`
  - Repetitive state-transition helpers; field-addition bugs likely if a method forgets to propagate one field.

## 6) Missing tests (architectural gaps, not just feature gaps)

1. **No characterization tests for the full menu state machine in `PygameApp`**
   - Existing UI tests cover helper slices; they do not lock down end-to-end transition invariants across all app screens.

2. **Insufficient golden/contract tests for `engine.apply_action` dispatch matrix**
   - There are many action types; missing a strict matrix test that every legal action class routes correctly and preserves key invariants.

3. **No anti-regression tests around controller family parity expectations**
   - Shared behaviors (e.g., discard validity, no-illegal-action fallback behavior) should be tested once and parameterized across heuristic generations.

4. **No architecture seam tests enforcing allowed imports/dependencies**
   - Nothing prevents future UI files from importing deeper core internals or runner internals ad hoc.

## 7) Safest cleanup order (smallest blast radius first)

1. **Add characterization/contract tests first** (freeze behavior before refactor).
2. **Extract pure helper modules** (no behavior change): constants, scoring math, state-copy helpers.
3. **Refactor controller internals behind shared base/utils** while keeping public classes stable.
4. **Introduce application-service facade between UI and runners/core** with adapter shims.
5. **Split `PygameApp` by screen/workflow** only after facade exists.
6. **Incrementally decompose `engine.py` action handlers** into isolated rule modules with unchanged API.

## 8) Suggested target architecture

- **Core Domain Layer**: `core/` only (state, actions, rules, observation contracts).
- **Application Layer**: use-case services for “start game”, “run tournament”, “run training”, “submit human intent”, “tick game”.
- **Interface Adapters**:
  - UI adapter (pygame) that depends only on application interfaces + DTOs.
  - CLI/headless runners as separate adapters.
  - Bot catalog/training persistence adapters behind interfaces.
- **Bot/AI Layer**:
  - Shared heuristic toolkit module (feature extraction, scoring primitives, common decision loop).
  - Thin strategy variants only override parameter sets / a few hooks.
- **Dependency rule**: UI → Application → Core, never UI → Core internals directly.

## 9) First three cleanup tasks (one branch each)

### Task 1: Freeze current behavior with architecture-oriented tests
- Add a parameterized “controller contract” test suite across all heuristic controllers.
- Add an `apply_action` dispatch/invariant matrix test for all action classes currently supported.
- Add a minimal import-boundary test (e.g., ban `ui/pygame_ui/*` importing `core.engine` directly except through an allowed façade module).
- **Scope**: tests only, no production refactor.

### Task 2: Deduplicate heuristic shared scaffolding (no behavior changes)
- Create `controllers/heuristic_common.py` for shared constants + common choose/record scaffolding.
- Migrate one low-risk pair first (`HeuristicBotController` + `HeuristicV1BaselineBotController`) to shared utilities.
- Keep class names, constructor signatures, and output decision payloads stable.
- **Scope**: controller internals only; no UI/core changes.

### Task 3: Introduce thin app service seam for local game tick
- Add `application/game_session_service.py` wrapping legal-action retrieval, observation policy, and action application.
- Update `LocalPygameRunner` to delegate to this service.
- No change yet to `PygameApp` features; only swap dependency to seam.
- **Scope**: minimal adapter insertion to prepare larger UI decomposition safely.

---

### Strictness note
This audit intentionally avoids recommending a big-bang rewrite. The project already has substantial behavior surface area; safest path is **tests first**, then **small extraction steps**, then **boundary tightening**.
