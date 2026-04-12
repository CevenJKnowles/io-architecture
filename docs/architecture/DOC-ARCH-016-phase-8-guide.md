---
id: DOC-ARCH-016
title: Phase 8 Guide | Governed Dialogue Layer
type: architecture
status: complete
version: v1.0
canonical: true
scope: phase-8
audience: developer
created: "2026-04-12"
updated: "2026-04-12"
tags:
- io-iii
- phase-8
- architecture
- dialogue
- session
- steward-mode
roles_focus:
- executor
- governance
provenance: io-iii-runtime-development
---

# Phase 8 Guide | Governed Dialogue Layer

## Purpose

Phase 8 makes IO-III conversational.

It introduces a bounded dialogue loop above the frozen execution stack, using
all prior infrastructure (memory, session snapshots, replay/resume, telemetry)
as its substrate. The execution stack is not modified. The engine freeze boundary
established across Phases 1–7 is preserved in full.

The primary additions are:

- a session loop with a hard turn ceiling
- steward governance mode with configurable threshold gates
- a session shell CLI for start / continue / status / close
- conditional runbook branches evaluated against structural fields only
- session continuity via memory on `session continue`

---

## Phase Prerequisite

Phase 8 depends on two Phase 7 deliverables:

- **M7.3** — `chat_session.yaml` runbook template demonstrating the intended
  dialogue entry point
- **M7.5** — ADR-024 (Work Mode / Steward Mode) accepted and indexed. This ADR
  is the governance prerequisite for M8.1. No Phase 8 code may be written until
  ADR-024 is accepted.

---

## Invariants That Must Remain True

- deterministic routing (ADR-002)
- bounded execution (ADR-009: max 1 audit pass, max 1 revision pass)
- content-safe logging — no prompts, no model output, no memory values (ADR-003)
- session loop is bounded — hard `SESSION_MAX_TURNS` ceiling; no unbounded loops
- mode transitions are user-initiated only — no autonomous mode switching
- memory writes never triggered automatically (ADR-022 §7)
- all execution through `orchestrator.run()` — never `engine.run()` directly
- `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 8
- all Phase 1–7 invariants preserved in full

---

## What Phase 8 May Add

- a `SessionMode` type (`work` | `steward`) and a `StewardGate` that evaluates
  configurable thresholds at each turn boundary
- a `DialogueSession` container and `TurnRecord` type for bounded, content-safe
  per-turn tracking
- a `run_turn()` function that drives one bounded turn through the orchestrator
- session persistence (load / save to `.io_iii/sessions/`)
- a session shell CLI (`session start`, `session continue`, `session status`,
  `session close`)
- conditional runbook branches (`when:` conditions evaluated against structural
  session fields only — `session_mode` and `persona_mode`)
- session continuity memory: `pack.io_iii.session_resume` auto-loaded on
  `session continue`; counts and key names only — never values

---

## What Phase 8 Must Not Add

- new execution layers below the dialogue session — the engine stack is frozen
- output-driven control flow — no branching on model output content
- automatic mode transitions — steward mode is user-initiated only
- autonomous memory writes — ADR-022 §7 prohibition applies throughout
- nested conditional runbook branches — max 1 branch level, structurally enforced
  by the type system (`RunbookStep.task_spec` is typed as `TaskSpec`, not
  `ConditionalRunbook`)
- memory values in any persisted or logged field

---

## Key Design Constraint — Engine Freeze

The execution engine (`engine.py`) is frozen from Phase 1. Phase 8 introduces
its dialogue layer *above* the engine, not inside it.

All session turns route through `orchestrator.run()`. The orchestrator
calls `engine.run()` as it always has. The dialogue session layer sits above
this boundary.

One consequence: memory injection into the model context via
`ExecutionContext.memory` is deferred. Phase 8 M8.6 establishes the
session-layer read path — records are loaded, counted in
`TurnRecord.memory_keys_loaded`, and threaded through
`DialogueTurnResult.memory_context` — but direct injection into the model
context awaits the engine freeze lifting in a future phase.

---

## Milestones

### M8.0 — Phase 8 ADR and Milestone Definition

Confirm ADR-024 (Work Mode / Steward Mode) accepted.
Define all Phase 8 milestones formally in SESSION_STATE.md.
No implementation before ADR-024 is accepted.

---

### M8.1 + M8.4 — Work Mode / Steward Mode + Steward Approval Gates

Combined milestone: full steward governance cycle.

**New module:** `io_iii/core/session_mode.py`

#### M8.1 Types

| Symbol | Description |
|---|---|
| `SessionMode` | Closed two-value enum: `WORK` \| `STEWARD` (ADR-024 §1) |
| `DEFAULT_SESSION_MODE` | `SessionMode.WORK` — default at session start |
| `StewardThresholds` | Frozen dataclass: `step_count`, `token_budget`, `capability_classes` |
| `load_steward_thresholds` | Loads `steward_thresholds` key from `runtime.yaml`; absent = safe |
| `PauseState` | Content-safe pause summary: threshold key, step/total, mode, run_id |
| `ModeTransitionEvent` | Content-safe telemetry record for work ↔ steward transitions |
| `transition_mode` | User-initiated-only mode switch; returns `(SessionMode, ModeTransitionEvent)` |
| `evaluate_thresholds` | Pure threshold evaluator at step boundary; returns fired key or None |
| `StewardGate` | Gate class: evaluates thresholds at step boundaries; holds mutable mode |

#### M8.4 Contract

Steward threshold pause surfaces a content-safe `PauseState` and waits for
explicit user action. Valid actions: `approve` (resume), `redirect` (prompt
revision), `close` (terminate session). No execution proceeds past a threshold
without explicit user action.

`PauseState` carries threshold key name only — never threshold values, model
names, prompt content, or config paths.

**SessionState extension:** `session_mode: SessionMode` field added.

---

### M8.2 + M8.3 — Bounded Session Loop + Session Shell CLI

Combined milestone: session loop and CLI surface.

**New module:** `io_iii/core/dialogue_session.py`

#### M8.2 Types

| Symbol | Description |
|---|---|
| `SESSION_MAX_TURNS` | Hard turn ceiling (default 50); configurable via `runtime.yaml` |
| `TurnRecord` | Frozen, content-safe per-turn record: `turn_index`, `run_id`, `status`, `persona_mode`, `latency_ms`, `error_code` |
| `DialogueSession` | Mutable session container: `session_id`, `session_mode`, `turn_count`, `max_turns`, `status`, `turns` |
| `DialogueTurnResult` | Frozen result of one turn: updated session, turn record, `SessionState`, `ExecutionResult`, optional `PauseState` |
| `new_session` | Factory: fresh session with unique ID; resolves `max_turns` from runtime config |
| `run_turn` | One bounded turn: checks limits → builds `TaskSpec` → `orchestrator.run()` → steward gate |
| `save_session` / `load_session` | Content-safe JSON persistence to `.io_iii/sessions/` |

#### M8.3 CLI Surface

**New module:** `io_iii/cli/_session_shell.py`

| Command | Description |
|---|---|
| `session start` | Initialise a new session; optionally run the first turn |
| `session continue` | Load a session and run one turn; handles pause flow |
| `session status` | Print content-safe session status summary |
| `session close` | Terminate session; retain file for audit |

#### M8.3 Turn Loop Contract

- exactly one `orchestrator.run()` call per turn
- bounded by `SESSION_MAX_TURNS`; raises `SESSION_AT_LIMIT` when reached
- steward gate evaluated at each turn boundary (ADR-024 §5.3)
- no prompt or output content in `TurnRecord` or session JSON
- no output-driven control flow

---

### M8.5 — Conditional Runbook Branches

Config-declared `when:` conditions on runbook steps. Conditions evaluate
structural session fields only. Max 1 branch level structurally enforced.

**Extensions to `io_iii/core/runbook.py`:**

| Symbol | Description |
|---|---|
| `WHEN_CONDITION_ALLOWED_KEYS` | `frozenset({"session_mode", "persona_mode"})` |
| `WHEN_CONDITION_ALLOWED_OPS` | `frozenset({"eq", "neq"})` |
| `WhenCondition` | Frozen config-declared predicate: `key`, `value`, `op` |
| `RunbookStep` | Frozen wrapper: `task_spec: TaskSpec` + `when: Optional[WhenCondition]` |
| `ConditionalRunbook` | Frozen ordered list of `RunbookStep`; same `RUNBOOK_MAX_STEPS` ceiling |

**Extensions to `io_iii/core/runbook_runner.py`:**

| Symbol | Description |
|---|---|
| `WhenContext` | Frozen structural context for evaluation: `session_mode`, `persona_mode` |
| `evaluate_when` | Pure predicate evaluator: `WhenCondition × WhenContext → bool` |
| `run_with_context` | Executes a `ConditionalRunbook`; skips steps whose `when` is False |
| `runbook_step_skipped` | New lifecycle event; `_RUNBOOK_LIFECYCLE_EVENTS` now 7 (was 6) |
| `RunbookResult.steps_skipped` | Count of skipped steps (default 0; backward-compatible) |

#### M8.5 Safety Invariants

- conditions evaluate `session_mode` and `persona_mode` only — never model output
- max 1 branch level: nesting structurally impossible by type (`RunbookStep.task_spec`
  is `TaskSpec`, not `ConditionalRunbook`)
- skipped steps emit `runbook_step_skipped` with `task_spec_id` + `step_index` only

---

### M8.6 — Session Continuity via Memory

Cross-turn context as bounded memory records. `pack.io_iii.session_resume`
auto-loaded on `session continue`. Memory writes never triggered automatically.

**New module:** `io_iii/memory/session_continuity.py`

| Symbol | Description |
|---|---|
| `SESSION_CONTINUITY_PACK_ID` | `"pack.io_iii.session_resume"` |
| `SessionMemoryContext` | Frozen, content-safe record of memory loaded for a turn |
| `load_session_memory()` | Policy-gated pack loader; absent pack → `([], None)` safe default |

`SessionMemoryContext` fields (all structural — no values):
`pack_id`, `scope`, `keys_declared`, `keys_loaded`, `keys_missing`, `policy_route`

#### M8.6 Engine Freeze Consequence

Memory injection into the model context via `ExecutionContext.memory` is
deferred — `engine.py` is frozen. M8.6 establishes the session-layer read path
only. Records are loaded, counted, and threaded through `DialogueTurnResult.memory_context`
for future use. Actual model-context injection awaits engine freeze lift.

#### M8.6 Contract

- absent pack is the safe default — not an error
- retrieval policy applied before records returned (ADR-022 §4)
- no `MemoryRecord` values in any persisted field (`TurnRecord`, session JSON)
- memory writes never triggered automatically (ADR-022 §7)
- `keys_missing` counts keys declared in pack but absent from store (distinct
  from records dropped by policy)

---

## Definition of Done

Phase 8 is complete when:

- ADR-024 (Work Mode / Steward Mode) accepted and indexed ✓
- M8.1+M8.4, M8.2+M8.3, M8.5, M8.6 milestones delivered ✓
- session loop bounded by hard `SESSION_MAX_TURNS` ceiling ✓
- steward gate evaluated at each turn boundary ✓
- conditional runbook branches limited to 1 level by the type system ✓
- session continuity memory loaded on `session continue`; values never logged ✓
- `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 8 ✓
- content-safe invariants satisfied across all new types ✓
- `pytest` passing — 916 tests ✓
- invariant validator passing ✓
- SESSION_STATE.md updated with phase close state ✓
- repository tagged `v0.8.0` ✓