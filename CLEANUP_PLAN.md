# Cleanup Plan (Incremental, Low-Risk)

This plan translates `ARCHITECTURE_AUDIT.md` into execution-ready work with strict constraints:
- **No big-bang rewrites**
- **Behavior frozen by tests before refactors**
- **One concern per branch**
- **Small PRs with explicit rollback paths**

---

## 1) Scope and non-goals

### In scope
- Reduce architectural risk in UI, runner, and controller layers.
- Improve maintainability by introducing seams and deduplicating shared logic.
- Add characterization and contract tests that lock behavior before internal cleanup.

### Out of scope (for this plan phase)
- Changing game rules or balance behavior intentionally.
- Replacing pygame UI framework.
- Reworking domain models in a single large migration.

---

## 2) Guardrails (must hold for every branch)

1. **No game behavior changes unless explicitly flagged**.
2. **Every refactor PR starts with characterization tests** (or includes them first in same PR if tiny).
3. **Public interfaces remain stable** for existing runners/controllers unless a migration shim is included.
4. **Any new module extraction is pure move + wiring first**, cleanup second.
5. **Rollback-friendly commits**: each commit should be revertable without partial breakage.

---

## 3) Risk-ranked backlog

### Tier A (highest risk reduction first)
1. Characterization tests around `core.engine.apply_action` dispatch + invariants.
2. Characterization tests for UI screen transitions and main menu/setup/tournament/training flows.
3. Controller-family contract tests (shared behavior across heuristic variants).

### Tier B (medium risk, high maintainability gain)
4. Deduplicate heuristic constants + decision-loop scaffolding into shared helpers.
5. Add application service seam for local game tick (runner → service abstraction).
6. Reduce `game_setup` repetitive state-copy patterns safely.

### Tier C (enables larger future decomposition)
7. Introduce import-boundary checks to prevent UI ↔ deep core coupling creep.
8. Split `PygameApp` by workflow modules after seams/tests are in place.
9. Decompose engine action handlers by action category with unchanged API.

---

## 4) Ordered execution plan

## Phase 0 — Baseline and safety net

### Goal
Establish confidence and reproducibility before any structural changes.

### Deliverables
- CI command documented and used consistently: `PYTHONPATH=src pytest -q`.
- Test runtime baseline captured (so later PRs can explain changes in runtime).
- Minimal architecture decision record (ADR) note for “incremental refactor strategy”.

### Exit criteria
- Main branch passes full test suite.
- Baseline metrics saved in repo docs (short, factual).

---

## Phase 1 — Freeze behavior with tests (no production refactor)

### Goal
Prevent accidental regressions when internals are reorganized.

### Deliverables
1. **Engine dispatch matrix tests**
   - Parameterized coverage for all supported action types.
   - Validate: legal action applies, illegal action rejected, core invariants remain true.

2. **Controller contract tests**
   - Shared expectations across heuristic controllers:
     - never choose action outside legal set
     - deterministic behavior under fixed seed where intended
     - discard/trade special-case validity rules

3. **UI transition characterization tests**
   - Screen transition invariants across main menu/setup/tournament/training paths.
   - Ensure no accidental dead-end states.

4. **Import-boundary tests (lightweight)**
   - Enforce that selected UI modules cannot directly import deep core internals except approved seam(s).

### Exit criteria
- New tests pass and are stable.
- At least one test each for engine, controller contracts, UI transitions, and import boundaries.

---

## Phase 2 — Controller deduplication (internal only)

### Goal
Lower maintenance cost and divergence risk in heuristic bot family.

### Deliverables
- Add shared module for constants + scoring loop/decision-record helpers.
- Migrate two closest variants first (baseline pair) with zero behavior drift.
- Keep public class names/signatures unchanged.

### Verification
- Existing controller tests + new contract suite pass unchanged.
- Optional snapshot/trace comparisons for selected seeds to confirm parity.

### Exit criteria
- Repetition reduced in migrated controllers.
- No behavioral diff in test-observed outputs.

---

## Phase 3 — Introduce application seam for local game tick

### Goal
Decouple runner orchestration policy from concrete controller type checks.

### Deliverables
- New service module handling:
  - legal actions retrieval
  - observation policy selection
  - action application + invalid-action handling policy
- `LocalPygameRunner` delegates to service (thin wrapper).

### Verification
- Runner tests pass.
- No UI behavior changes required in this phase.

### Exit criteria
- Runner no longer owns policy logic directly.
- Seam is available for UI cleanup in later phases.

---

## Phase 4 — UI workflow extraction (small slices)

### Goal
Break `PygameApp` god-object into workflow-focused modules without changing UX.

### Deliverables (in multiple PRs)
1. Extract menu state transition logic.
2. Extract tournament setup/event handling.
3. Extract training setup/progress handling.
4. Keep rendering calls and event loop orchestration stable while extracting pure handlers.

### Verification
- UI characterization tests remain green.
- No new direct imports from UI to deep core internals.

### Exit criteria
- `app.py` significantly smaller.
- Each extracted workflow has isolated tests.

---

## Phase 5 — Engine decomposition behind stable API

### Goal
Reduce complexity of `engine.py` while preserving external API.

### Deliverables
- Move action handlers into categorized modules (setup, turn, robber, trade, dev-cards).
- Keep `get_legal_actions` / `apply_action` public signatures stable.
- Replace long dispatch chain incrementally with table/registry if safe.

### Verification
- Engine matrix + invariants tests unchanged and passing.
- No external caller updates required (or only mechanical imports).

### Exit criteria
- `engine.py` orchestrates, handler modules implement details.
- Complexity and file size reduced with no behavior drift.

---

## 5) First three branch-sized tasks (immediate next actions)

## Branch 1: `test/engine-dispatch-matrix`

### Changes
- Add parameterized tests covering all action classes through `apply_action` pathways.
- Add invariant checks after state transitions.

### Size target
- ~150–300 LOC test-only changes.

### Risk
- Very low (tests only).

### Done when
- Tests fail on intentional dispatch break and pass on current main.

---

## Branch 2: `test/controller-contract-suite`

### Changes
- Add shared contract test fixture applied to all heuristic controllers.
- Verify legal-action compliance and core choice invariants.

### Size target
- ~150–300 LOC test-only changes.

### Risk
- Very low (tests only).

### Done when
- Contract suite runs for all heuristic variants and passes.

---

## Branch 3: `refactor/local-runner-service-seam`

### Changes
- Add application service module for tick policy.
- Update `LocalPygameRunner` to delegate to service.
- Keep behavior and signatures stable.

### Size target
- ~80–220 LOC mixed production + tests.

### Risk
- Low–medium (small production refactor guarded by tests).

### Done when
- Runner tests unchanged/green; no observed behavior changes.

---

## 6) PR template for this cleanup track

Every cleanup PR should include:
1. **What behavior is frozen by tests?**
2. **What internal structure changed?**
3. **Why is this step safe and reversible?**
4. **What is intentionally deferred to next PR?**

---

## 7) Stop conditions (when to pause and reassess)

Pause the refactor track if any occurs:
- Characterization tests reveal undocumented existing inconsistencies.
- A refactor PR needs >~400 LOC production changes to stay coherent.
- More than one subsystem (UI + engine + controllers) must change together.

If triggered, split scope and return to smaller branch units.

---

## 8) Definition of success for this plan

- High-risk files are no longer single points of fragile change.
- Critical behavior is protected by contract/characterization tests.
- New features can be added via seams rather than deep cross-layer edits.
- Refactors remain incremental, reviewable, and revertable.
