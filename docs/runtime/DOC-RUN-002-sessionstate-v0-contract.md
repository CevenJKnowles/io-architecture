---
id: "DOC-RUN-002"
title: "SessionState v0 Contract"
type: "runtime"
status: "active"
version: "v0.1"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-04"
updated: "2026-03-04"
tags:
 - "runtime"
 - "sessionstate"
 - "contract"
roles_focus:
 - "executor"
provenance: "mixed"
---

# IO-III SessionState v0 Contract

---

## Purpose

SessionState is the **single, bounded runtime record** for one IO-III execution.

It exists to:
- make execution deterministic and inspectable
- provide a stable structure for logging and test fixtures
- support governance enforcement (audit bounds, cloud-disabled-by-default) without introducing autonomy

---

## Scope

This document defines **v0 only**, matching the current runtime implementation:

- `io_iii/core/session_state.py`
- used by the execution pipeline via `io_iii/core/engine.py`

---

## Non-goals (v0)

SessionState v0 does **not** include:
- persistent memory
- retrieval / RAG
- tool invocation traces
- multi-model arbitration
- dynamic routing state
- prompt or output content storage

---

## Data model (v0)

SessionState v0 is a **frozen, typed record** (dataclasses) with a small number of nested structures.

### Required fields

These fields are required to identify the run, bind it to the deterministic configuration, and report governance-relevant metadata.

- `request_id: str`
  - unique identifier for the run

- `started_at_ms: int`
  - Unix epoch milliseconds captured at run start

- `mode: str`
  - selected execution mode (e.g. `executor`, `challenger`)

- `config_dir: str`
  - the runtime config root used to load:
    - `architecture/runtime/config/routing_table.yaml`
    - `architecture/runtime/config/providers.yaml`
    - `architecture/runtime/config/logging.yaml`

- `provider: str`
  - resolved provider name selected by deterministic routing

- `route_id: str`
  - resolved route identifier from the routing table

- `audit: AuditGateState`
  - bounded audit counters and toggle state

- `status: str`
  - terminal run status
  - permitted values: `ok`, `error`

- `logging_policy: dict`
  - resolved logging policy snapshot (metadata on, content off by default)

### Optional fields

These fields may be absent in successful minimal runs, but are part of the v0 structure.

- `latency_ms: int | None`
  - end-to-end runtime latency

- `model: str | None`
  - resolved model identifier (provider-level detail)

- `persona_contract_version: str | None`
  - version string for the active persona contract

- `persona_id: str | None`
  - persona reference identifier (binding reference only)

- `route: RouteInfo | None`
  - optional snapshot of resolved routing information
  - must remain **non-dynamic** (no mid-run mutation)

- `error_code: str | None`
  - required if and only if `status == "error"`

---

## AuditGateState (v0)

AuditGateState records the bounded audit counters and whether audit is enabled.

Governance constraints:
- counters must never exceed:
  - `MAX_AUDIT_PASSES = 1`
  - `MAX_REVISION_PASSES = 1`
- audit remains **toggle-based** and must not self-enable

---

## Invariants

The following must hold for any valid v0 SessionState:

1) **Determinism**
   - `provider` and `route_id` are final outputs of deterministic routing.

2) **Bounded execution**
   - audit counters are hard-bounded and enforced at runtime.

3) **No content retention by default**
   - SessionState does not store prompts or generated outputs.

4) **No cloud activation**
   - SessionState must not introduce any mechanism that enables cloud providers.

---

## Compatibility and evolution

- v0 is intentionally minimal.
- Any additions that affect behaviour or execution boundaries require:
  - an ADR (if governance-impacting)
  - an invariant update (if enforceable)
  - explicit Phase-3 scope approval