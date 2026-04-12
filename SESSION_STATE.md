# SESSION_STATE

## IO-III Session State

**Project:** IO-III — Deterministic Local LLM Runtime Architecture

**Repository:** [CevenJKnowles/io-architecture](https://github.com/CevenJKnowles/io-architecture)

**Local Path:** `/home/cjk/Dev/IO-III/io-architecture`

> Phase 3–5 milestone detail archived to `history/session-states/phase-3-5-closeout.md`.

---

## Phase Status

**Current Phase:** Phase 7 — Open-Source Initialisation Layer (complete)

**Status:** Phase 7 complete. M7.0–M7.5 delivered. All invariants passing. Ready for tagging v0.7.0.

**Tag:** v0.7.0 (pending)

**Branch:** phase-7-0

---

## Runtime Guarantees

The runtime currently guarantees:

- deterministic routing
- bounded execution
- max audit passes = 1
- max revision passes = 1
- explicit capability invocation only
- no autonomous tool selection
- no recursive orchestration
- no dynamic routing
- no prompt or completion content in logs

Forbidden logging fields:

- prompt
- completion
- draft
- revision
- content

---

## Phase 6 Close State — 2026-04-12

**Phase:** 6 — Memory Architecture | **Tag:** v0.6.0

| Milestone | Module | Tests |
| --- | --- | --- |
| M6.1 — Memory Store Architecture | `io_iii/memory/store.py` | `tests/test_memory_store_m61.py` |
| M6.2 — Memory Pack System | `io_iii/memory/packs.py` | `tests/test_memory_packs_m62.py` |
| M6.3 — Memory Retrieval Policy | `io_iii/memory/policy.py` | `tests/test_memory_policy_m63.py` |
| M6.4 — Memory Injection via Context Assembly | `io_iii/core/context_assembly.py`, `io_iii/core/execution_context.py` | `tests/test_memory_injection_m64.py` |
| M6.5 — Memory Safety Invariants | `architecture/runtime/scripts/validate_invariants.py`, `architecture/runtime/tests/invariants/inv-005-memory-content-safety.yaml` | `tests/test_invariants_m65.py` |
| M6.6 — Memory Write Contract | `io_iii/memory/write.py` | `tests/test_memory_write_m66.py` |
| M6.7 — SessionState Snapshot Export | `io_iii/core/snapshot.py` | `tests/test_session_snapshot_m67.py` |

**Test trajectory:** 419 (Ph5 close) → 472 (M6.1) → 537 (M6.2+M6.3) → 565 (M6.4) → 577 (M6.5) → **603 (M6.6+M6.7)**

**Invariant validator:** 5/5 PASS (INV-001 through INV-005)

**CLI additions (Phase 6):**

- `python -m io_iii memory write --scope <scope> --key <key> --value <value>` — M6.6
- `python -m io_iii session export --run-id <id> --mode <mode> [--output <path>]` — M6.7
- `python -m io_iii session import --snapshot <path>` — M6.7

**ADR freeze boundary respected:** engine.py, routing.py, telemetry.py unchanged throughout Phase 6.

---

## Phase 7 — Open-Source Initialisation Layer (Complete)

**Governing ADR:** ADR-023 — Open-Source Initialisation Contract (accepted)

**Phase 7 Prerequisite:** Config separation audit complete. All model names live in
`routing_table.yaml`. No identity-specific values in structural artefacts. `persona.yaml`
absent — Phase 7 M7.3 deliverable.

---

### M7.0 — Phase 7 ADR and Milestone Definition ✓

ADR-023 authored and accepted. Config separation audit confirms Phase 7 prerequisite
satisfied. Phase 7 milestones formally defined in SESSION_STATE.md.

**Deliverable:** `ADR/ADR-023-open-source-initialisation-contract.md`

---

### M7.1 — Initialisation Contract ✓

Init contract formalised in ADR-023 §3. Four required config files identified;
two optional. No prerequisite extraction needed — config separation confirmed clean.

---

### M7.2 — Init Command or Setup Guide ✓

CLI `init` subcommand: displays required config surface, shows file presence state,
runs portability validation, prints human-readable summary with next steps.

**Module:** `io_iii/cli/_init.py` — `cmd_init()`

**CLI:** `python -m io_iii init`

---

### M7.3 — Default Pack and Persona Templates ✓

Neutral, non-identity-specific template files created:

- `architecture/runtime/config/persona.yaml` — default persona template (executor,
  explorer, draft modes; annotated; placeholder `persona.name = "io-user"`)
- `architecture/runtime/config/templates/chat_session.yaml` — annotated YAML template
  (human-readable; schema reference)
- `architecture/runtime/config/templates/chat_session.json` — runnable JSON version
  (3-step `intent → execute → summarise` pattern; explorer → executor → draft)

---

### M7.4 — Portability Validation ✓

Validation pass confirming correct initialisation before first execution.

**Module:** `io_iii/core/portability.py` — `run_portability_checks()`, `validate_portability()`

**Checks (7):** required config files present and parseable; provider base_url declared;
model name declared; persona name present; storage root declared; storage root writable;
constellation guard passes (M5.3).

**CLI:** `python -m io_iii validate`

**New failure code:** `PORTABILITY_CHECK_FAILED` (ADR-013 extension)

**Tests:** `tests/test_portability_m74.py` — 24 tests

---

### M7.5 — Work Mode / Steward Mode ADR ✓

ADR-024 authored and accepted. Governance contract for `work` / `steward` session modes
established as Phase 8 M8.1 prerequisite.

**Deliverable:** `ADR/ADR-024-work-mode-steward-mode-contract.md`

**Prerequisite for:** Phase 8 M8.1. No Phase 8 code until ADR-024 is accepted.

---

### Phase 7 Definition of Done

- ADR-023 accepted and indexed ✓
- M7.1–M7.5 milestones delivered ✓
- A user with no prior context can clone, follow the init surface, and execute a governed
  run without modifying structural code ✓
- `chat_session.yaml` template present and runnable ✓
- ADR-024 (Work Mode / Steward Mode) accepted and indexed ✓
- No identity-specific values in any structural artefact ✓
- `pytest` passing ✓
- Invariant validator passing ✓
- SESSION_STATE.md updated with phase close state ✓
- Repository tagged `v0.7.0` (pending)

---

---

## Phase 8 — Governed Dialogue Layer (Complete)

**Governing ADR:** ADR-024 — Work Mode / Steward Mode Contract (accepted)

**Status:** Phase 8 complete. M8.1+M8.4, M8.2+M8.3, M8.5, M8.6 delivered. All invariants passing. Ready for tagging v0.8.0.

**Tag:** v0.8.0 (pending)

**Prerequisite:** ADR-024 accepted ✓

---

### M8.1 + M8.4 — Work Mode / Steward Mode + Steward Approval Gates ✓

Combined milestone: full steward governance cycle delivered in one pass.

**New module:** `io_iii/core/session_mode.py`

| Symbol | Description |
| --- | --- |
| `SessionMode` | Closed two-value enum: `WORK` \| `STEWARD` (ADR-024 §1) |
| `DEFAULT_SESSION_MODE` | `SessionMode.WORK` — default at session start (ADR-024 §1.2) |
| `StewardThresholds` | Frozen dataclass: `step_count`, `token_budget`, `capability_classes` (ADR-024 §5) |
| `load_steward_thresholds` | Loads `steward_thresholds` key from `runtime.yaml`; absent = safe (ADR-024 §7.2) |
| `PauseState` | Content-safe pause summary: threshold key, step/total, mode, run_id (ADR-024 §6.2) |
| `ModeTransitionEvent` | Content-safe telemetry record for work ↔ steward transitions (ADR-021) |
| `transition_mode` | User-initiated-only mode switch; returns `(SessionMode, ModeTransitionEvent)` (ADR-024 §4) |
| `evaluate_thresholds` | Pure threshold evaluator at step boundary; returns fired key or None (ADR-024 §5.3) |
| `StewardGate` | Gate class: evaluates thresholds at step boundaries; holds mutable mode (ADR-024 §5–§6) |

**SessionState extension:** `session_mode: SessionMode = DEFAULT_SESSION_MODE` added as new
field (co-exists with `mode: str` persona field). `validate_session_state` updated to enforce
`SessionMode` type.

**Config extension:** `architecture/runtime/config/runtime.yaml` — `steward_thresholds` block
documented (commented); absent by default is safe (ADR-024 §5.6).

**Tests:** `tests/test_session_mode_m81_m84.py` — 72 tests

**Test trajectory:** 702 (Ph7 close) → **774 (M8.1+M8.4)**

**ADR-003 / ADR-024 content-safety invariants upheld:**

- `PauseState` carries threshold key name only — never threshold values, model names, prompt content, or config paths
- `ModeTransitionEvent` carries only direction strings and user action label
- No forbidden fields added to logging surfaces

**ADR freeze boundary respected:** `engine.py`, `routing.py`, `telemetry.py` unchanged.

---

### M8.2 + M8.3 — Bounded Session Loop + Session Shell CLI ✓

Combined milestone: session loop and CLI surface delivered together.

**New module:** `io_iii/core/dialogue_session.py`

| Symbol | Description |
| --- | --- |
| `SESSION_MAX_TURNS` | Hard turn ceiling (default: 50); configurable via `runtime.yaml` `session_max_turns` |
| `TurnRecord` | Frozen, content-safe per-turn record: `turn_index`, `run_id`, `status`, `persona_mode`, `latency_ms`, `error_code` |
| `DialogueSession` | Mutable session state: `session_id`, `session_mode`, `turn_count`, `max_turns`, `status`, `turns`, timestamps |
| `DialogueTurnResult` | Frozen result of one turn: updated session, turn record, `SessionState`, `ExecutionResult`, optional `PauseState` |
| `new_session` | Factory: fresh session with unique ID; resolves `max_turns` from runtime config or explicit arg |
| `run_turn` | One bounded turn: checks limits → builds `TaskSpec` → `orchestrator.run()` → steward gate → returns result |
| `save_session` / `load_session` | Content-safe JSON persistence to `.io_iii/sessions/` |
| `list_sessions` | Returns sorted session IDs from storage root |
| `session_status_summary` | Content-safe dict for CLI display; no prompt/output/model content |

**New CLI module:** `io_iii/cli/_session_shell.py`

| Command | CLI surface |
| --- | --- |
| `session start` | `python -m io_iii session start [--mode work\|steward] [--persona-mode executor] [--prompt TEXT] [--audit]` |
| `session continue` | `python -m io_iii session continue --session-id ID --prompt TEXT [--persona-mode executor] [--audit] [--action approve\|redirect\|close]` |
| `session status` | `python -m io_iii session status --session-id ID` |
| `session close` | `python -m io_iii session close --session-id ID` |

**Turn loop contract (ADR-012 / ADR-014 / ADR-024):**

- Exactly one `orchestrator.run()` call per turn (never `engine.run()` directly)
- Bounded by `SESSION_MAX_TURNS`; raises `SESSION_AT_LIMIT` when reached
- Steward gate evaluated at each turn boundary (ADR-024 §5.3)
- No prompt or output content stored in `TurnRecord` or session JSON
- Memory writes never triggered automatically (ADR-022 §7)
- No output-driven control flow

**Tests:** `tests/test_session_shell_m82_m83.py` — 59 tests

**Test trajectory:** 774 (M8.1+M8.4) → **833 (M8.2+M8.3)**

**ADR freeze boundary respected:** `engine.py`, `routing.py`, `telemetry.py` unchanged.

---

### M8.5 — Conditional Runbook Branches ✓

Config-declared `when:` conditions on runbook steps. Conditions evaluate structural session
fields only (never model output). Max 1 branch level structurally guaranteed by the type system.

**New types in `io_iii/core/runbook.py`:**

| Symbol | Description |
| --- | --- |
| `WHEN_CONDITION_ALLOWED_KEYS` | Frozenset of permitted condition keys: `session_mode`, `persona_mode` |
| `WHEN_CONDITION_ALLOWED_OPS` | Frozenset of permitted operators: `eq`, `neq` |
| `WhenCondition` | Frozen config-declared predicate: `key`, `value`, `op` |
| `RunbookStep` | Frozen wrapper: `task_spec: TaskSpec` + `when: Optional[WhenCondition]` |
| `ConditionalRunbook` | Frozen ordered list of `RunbookStep` objects; same RUNBOOK_MAX_STEPS ceiling |

**New types and functions in `io_iii/core/runbook_runner.py`:**

| Symbol | Description |
| --- | --- |
| `WhenContext` | Frozen structural context for evaluation: `session_mode`, `persona_mode` |
| `evaluate_when` | Pure predicate evaluator: `WhenCondition × WhenContext → bool` |
| `run_with_context` | Executes a `ConditionalRunbook`; skips steps whose `when` is False |
| `runbook_step_skipped` | New lifecycle event in `_RUNBOOK_LIFECYCLE_EVENTS` (7 total, was 6) |

**Contract invariants (ADR-003 / ADR-014):**

- Conditions evaluate `session_mode` and `persona_mode` only — never model output
- Max 1 branch level: `RunbookStep.task_spec` is always `TaskSpec`, nesting structurally impossible
- Skipped steps emit `runbook_step_skipped` lifecycle event (content-safe: `task_spec_id` + `step_index` only)
- `RunbookResult.steps_skipped` field added (default 0; backward-compatible)
- `test_runbook_m48.py` taxonomy contract updated: 7 events (was 6)

**Tests:** `tests/test_conditional_runbook_m85.py` — 56 tests

**Test trajectory:** 833 (M8.2+M8.3) → **889 (M8.5)**

**ADR freeze boundary respected:** `engine.py`, `routing.py`, `telemetry.py` unchanged.

---

### M8.6 — Session Continuity via Memory ✓

Cross-turn context as bounded memory records. `pack.io_iii.session_resume` auto-loaded
on `session continue`. Memory writes never triggered automatically (ADR-022 §7).

**New module:** `io_iii/memory/session_continuity.py`

| Symbol | Description |
| --- | --- |
| `SESSION_CONTINUITY_PACK_ID` | Default pack id: `"pack.io_iii.session_resume"` |
| `SessionMemoryContext` | Frozen, content-safe record of memory loaded for a turn |
| `load_session_memory()` | Policy-gated pack loader; absent pack → `([], None)` safe default |

**`SessionMemoryContext` fields (all structural — no values):**
`pack_id`, `scope`, `keys_declared`, `keys_loaded`, `keys_missing`, `policy_route`

**Modifications:**

| Location | Change |
| --- | --- |
| `io_iii/core/dialogue_session.py` | `TurnRecord.memory_keys_loaded: int = 0` (count only, ADR-003) |
| `io_iii/core/dialogue_session.py` | `DialogueTurnResult.memory_context: Optional[SessionMemoryContext]` |
| `io_iii/core/dialogue_session.py` | `run_turn()` accepts `session_memory` and `memory_context` params |
| `io_iii/core/dialogue_session.py` | `save_session` / `_deserialise_session` persist `memory_keys_loaded` |
| `io_iii/cli/_session_shell.py` | `cmd_session_continue()` calls `_load_continuity_memory()` before turn |
| `io_iii/cli/_session_shell.py` | `_emit_turn_result()` surfaces `memory_keys_loaded` and `memory_context` |

**Contract invariants:**

- Absent pack is the safe default (`([], None)`) — not an error
- Retrieval policy applied before records returned (ADR-022 §4)
- No MemoryRecord values in any persisted field (TurnRecord, session JSON)
- Memory writes never triggered automatically (ADR-022 §7)
- Engine injection deferred — engine.py frozen; session-layer read path complete
- `keys_missing` = keys declared in pack but absent from store (not policy-dropped)

**Tests:** `tests/test_session_continuity_m86.py` — 27 tests

**Test trajectory:** 889 (M8.5) → **916 (M8.6)**

**ADR freeze boundary respected:** `engine.py`, `routing.py`, `telemetry.py` unchanged.

---

---

## Phase 9 — API & Integration Surface (Complete)

**Governing ADR:** ADR-025 — API & Integration Surface — Transport Adapter Contract (accepted)

**Status:** Phase 9 complete. M9.0–M9.5 delivered. All invariants passing. Ready for tagging v0.9.0.

**Tag:** v0.9.0 (pending)

**Prerequisite:** Phase 8 tagged v0.8.0 ✓

---

### M9.0 — Phase 9 ADR and Milestone Definition ✓

ADR-025 authored and accepted. Transport adapter contract, content-safety extension to HTTP,
endpoint-to-CLI mapping, SSE contract, webhook contract, structured exit codes, and server
entrypoint all formalised. Phase 9 milestones defined.

**Deliverable:** `ADR/ADR-025-api-integration-surface.md`

---

### M9.1 — HTTP API Layer ✓

Thin HTTP transport adapter over the existing session and execution layers.
No new execution semantics. All execution through `orchestrator.run()` or session-layer functions.

**New package:** `io_iii/api/`

| Module | Responsibility |
| --- | --- |
| `io_iii/api/__init__.py` | Package init |
| `io_iii/api/_handlers.py` | Route handlers (map HTTP → session/orchestrator) |
| `io_iii/api/_sse.py` | SSE formatting + session stream handler (M9.2) |
| `io_iii/api/_webhooks.py` | Webhook dispatcher (M9.3) |
| `io_iii/api/server.py` | HTTPServer + request handler + `serve` CLI entrypoint |
| `io_iii/api/static/index.html` | Self-hosted web UI (M9.5) |

**Endpoints delivered:**

| Method | Path | Maps to |
| --- | --- | --- |
| `POST` | `/run` | `orchestrator.run()` — includes model output (primary surface) |
| `POST` | `/runbook` | `runbook_runner.run()` — includes step outputs (primary surface) |
| `POST` | `/session/start` | `new_session()` + optional first `run_turn()` |
| `POST` | `/session/{id}/turn` | `run_turn()` — content-safe governance metadata only |
| `GET` | `/session/{id}/state` | `session_status_summary()` |
| `DELETE` | `/session/{id}` | session close + persist |
| `GET` | `/session/{id}/stream` | SSE stream: turn execution + model output (M9.2) |
| `GET` | `/` | Self-hosted web UI (M9.5) |

**CLI addition:** `python -m io_iii serve [--host 127.0.0.1] [--port 8080]`

**ADR freeze boundary respected:** `engine.py`, `routing.py`, `telemetry.py` unchanged.

---

### M9.2 — SSE Streaming ✓

Server-Sent Events on `GET /session/{id}/stream?prompt=TEXT`.

**Event sequence:** `turn_started` → `turn_output` → `turn_completed` (or `steward_gate_triggered`)

`turn_output` carries model text (user-facing; not logged or forwarded — ADR-025 §5).
All other events are content-safe. Execution is synchronous (engine frozen — no token streaming).

**SSE event taxonomy:** `_SSE_SESSION_EVENTS` (5 events, frozen)

---

### M9.3 — Webhooks ✓

Best-effort HTTP POST callbacks on three governed lifecycle events.

**Class:** `WebhookDispatcher` in `io_iii/api/_webhooks.py`

| Event constant | Trigger |
| --- | --- |
| `WEBHOOK_SESSION_COMPLETE` | Session closed via `DELETE /session/{id}` or steward close action |
| `WEBHOOK_RUNBOOK_COMPLETE` | `POST /runbook` succeeds |
| `WEBHOOK_STEWARD_GATE_TRIGGERED` | Turn response contains pause state |

**Contract invariants:**

- Absent `webhooks:` key in `runtime.yaml` → safe default (no webhooks fired)
- Best-effort: single attempt, 5-second timeout, silent failure
- All payloads strictly content-safe — no model output, no prompt, no memory values

**Webhook event taxonomy:** `_WEBHOOK_EVENTS` (3 events, frozen)

---

### M9.4 — CLI Surface Improvements ✓

**`--output json` flag:** Added to `main()` parser. All CLI output was already JSON (`_print()`
always uses `json.dumps`). The flag formalises this as the declared contract (ADR-025 §7).

**`serve` subcommand:** `python -m io_iii serve [--host H] [--port P]` wired into `main()`.

**Structured exit codes (ADR-025 §7):**

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Execution error |
| 2 | Configuration error / server binding failure |
| 3 | Steward gate pause — session paused, awaiting human action |

Exit code 3 now returned by `cmd_session_continue()` when:

- Session is paused on load with no `--action` supplied
- A just-completed turn fires the steward gate

---

### M9.5 — Self-Hosted Web UI ✓

Single static HTML file (`io_iii/api/static/index.html`). Served at `GET /`.

- Chat-style session interface; governed entry point only
- Uses `EventSource` for SSE streaming (model output via `turn_output` event)
- Uses `fetch()` for API calls (`/session/start`, `/session/{id}/turn`, `DELETE /session/{id}`)
- Supports work/steward mode selection and steward pause actions (approve/redirect/close)
- No external JavaScript framework; no CDN dependencies
- API base derived from `window.location.origin` — no hard-coded ports

---

### Phase 9 Definition of Done

- ADR-025 accepted and indexed ✓
- M9.0–M9.5 milestones delivered ✓
- All API responses from session endpoints content-safe (ADR-003 / ADR-025 §4) ✓
- No endpoint bypasses the session layer ✓
- Webhook payloads strictly content-safe ✓
- `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 9 ✓
- `pytest` passing — 1046 tests ✓
- SESSION_STATE.md updated with phase close state ✓
- Repository tagged `v0.9.0` (pending)
