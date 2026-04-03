---
id: "DOC-RUN-002"
title: "SessionState v1 Contract"
type: "runtime"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-04"
updated: "2026-04-03"
tags:
 - "runtime"
 - "sessionstate"
 - "contract"
roles_focus:
 - "executor"
provenance: "mixed"
supersedes: "DOC-RUN-002 v0.1"
---

# IO-III SessionState v1 Contract

---

## Purpose

SessionState is the **single, bounded runtime record** for one IO-III execution.

It exists to:
- make execution deterministic and inspectable
- provide a stable structure for logging and test fixtures
- support governance enforcement (audit bounds, cloud-disabled-by-default) without introducing autonomy
- carry a binding reference to the upstream TaskSpec that initiated execution

---

## Scope

This document defines **v1**, matching the current runtime implementation:

- `io_iii/core/session_state.py`
- used by `io_iii/core/engine.py`, `io_iii/core/orchestrator.py`, and `io_iii/cli.py`

The file retains its historical `...v0-contract.md` filename for continuity during the v1 promotion. The document body and metadata are canonical.

---

## Migration from v0

v1 adds two fields to v0:

| Field | Type | Change |
|-------|------|--------|
| `schema_version` | `str = "v1"` | NEW — version sentinel; validated by `validate_session_state` |
| `task_spec_id` | `Optional[str] = None` | NEW — binding reference to upstream TaskSpec |

All existing construction sites gain `schema_version="v1"` automatically via the default.
CLI paths that do not use a `TaskSpec` remain valid with `task_spec_id=None`.
The orchestrator passes `task_spec.task_spec_id` explicitly.

---

## Non-goals (v1)

SessionState v1 does **not** include:
- persistent memory
- retrieval / RAG
- tool invocation traces
- multi-model arbitration
- dynamic routing state
- prompt or output content storage
- execution lifecycle states (those belong to `ExecutionTrace`)

---

## Field classification

SessionState fields are classified as either **write-once** or **engine-mutable**.

### Write-once fields
Set at construction. Must not be changed by the engine or orchestrator.

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | `str` | Contract version sentinel; must be `"v1"` |
| `request_id` | `str` | Unique run identity |
| `started_at_ms` | `int` | Epoch ms at run start; timing anchor |
| `mode` | `str` | Selected execution mode (`executor`, `capability`, etc.) |
| `config_dir` | `str` | Runtime config root path |
| `route` | `Optional[RouteInfo]` | Deterministic routing snapshot (frozen) |
| `task_spec_id` | `Optional[str]` | Binding reference to upstream TaskSpec; `None` for CLI paths |
| `persona_id` | `Optional[str]` | Persona binding reference; identifier only, no payload |
| `persona_contract_version` | `Optional[str]` | Active persona contract version |
| `logging_policy` | `Dict[str, Any]` | Logging configuration snapshot |
| `route_id` | `str` | Resolved route identifier |

### Engine-mutable fields
Defaults set at construction. Engine rebuilds these post-execution via `_replace()`.

| Field | Type | Pre-execution | Post-execution |
|-------|------|--------------|----------------|
| `latency_ms` | `Optional[int]` | `None` | Computed end-to-end latency |
| `status` | `str` | `"ok"` | `"ok"` or `"error"` |
| `provider` | `str` | From routing | Confirmed by engine on result path |
| `model` | `Optional[str]` | `None` | Resolved model (ollama path) |
| `audit` | `AuditGateState` | Initial state | Rebuilt with pass counts and verdict |
| `error_code` | `Optional[str]` | `None` | Set if `status == "error"` |

---

## Data model (v1)

SessionState v1 is a **frozen, typed record** (dataclasses) with a small number of nested structures.

### Required fields (no default)

- `request_id: str` — unique identifier for the run
- `started_at_ms: int` — Unix epoch milliseconds captured at run start

### Optional fields with defaults

- `schema_version: str = "v1"` — version sentinel; must be `"v1"` to pass validation
- `latency_ms: Optional[int] = None` — end-to-end runtime latency; set by engine at completion
- `mode: str = "executor"` — selected execution mode
- `config_dir: str` — runtime config root
- `route: Optional[RouteInfo] = None` — routing decision snapshot
- `audit: AuditGateState` — bounded audit gate counters and toggle state
- `status: str = "ok"` — terminal run status; `"ok"` or `"error"`
- `provider: str = "null"` — resolved provider name
- `model: Optional[str] = None` — resolved model identifier (provider-level detail)
- `route_id: str = "executor"` — resolved route identifier from the routing table
- `persona_contract_version: Optional[str] = None` — version string for the active persona contract
- `persona_id: Optional[str] = None` — persona reference identifier (binding reference only)
- `task_spec_id: Optional[str] = None` — binding reference to the upstream TaskSpec; `None` for CLI paths
- `error_code: Optional[str] = None` — required if and only if `status == "error"`
- `logging_policy: Dict[str, Any]` — resolved logging policy snapshot

---

## AuditGateState (v1)

AuditGateState records the bounded audit counters and whether audit is enabled.

Governance constraints:
- counters must never exceed:
  - `MAX_AUDIT_PASSES = 1`
  - `MAX_REVISION_PASSES = 1`
- audit remains **toggle-based** and must not self-enable

---

## Invariants

The following must hold for any valid v1 SessionState:

1) **Schema version**
   - `schema_version` must be `"v1"`.

2) **Determinism**
   - `provider` and `route_id` are final outputs of deterministic routing.

3) **Bounded execution**
   - audit counters are hard-bounded and enforced at runtime.

4) **No content retention by default**
   - SessionState does not store prompts or generated outputs.

5) **No cloud activation**
   - SessionState must not introduce any mechanism that enables cloud providers.

6) **task_spec_id discipline**
   - `task_spec_id` carries only the identifier, never the TaskSpec payload.
   - `None` is valid (CLI paths that do not use a TaskSpec).
   - If set, must be a non-empty string.

---

## Construction paths

| Caller | task_spec_id | Notes |
|--------|-------------|-------|
| `orchestrator.run()` | `task_spec.task_spec_id` | Full orchestrator path; always set |
| `cli.py:cmd_run` | `None` (default) | Direct CLI path; no TaskSpec |
| `cli.py:cmd_capability` | `None` (default) | Capability-only path; no TaskSpec |
| `engine._run_challenger` | `None` (default) | Internal challenger path; no TaskSpec |

---

## Compatibility and evolution

- v1 is backwards-compatible with v0 for all construction sites (all new fields have defaults).
- Any additions that affect behaviour or execution boundaries require:
  - an ADR (if governance-impacting)
  - an invariant update (if enforceable)
  - explicit Phase scope approval