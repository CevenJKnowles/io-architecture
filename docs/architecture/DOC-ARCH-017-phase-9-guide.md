---
id: DOC-ARCH-017
title: Phase 9 Guide | API & Integration Surface
type: architecture
status: complete
version: v0.2
canonical: true
scope: phase-9
audience: developer
created: "2026-04-12"
updated: "2026-04-12"
tags:
- io-iii
- phase-9
- architecture
- api
- http
- integration
roles_focus:
- executor
- governance
provenance: io-iii-runtime-development
---

# Phase 9 Guide | API & Integration Surface

## Purpose

Phase 9 wraps the existing CLI and session layer in a thin, content-safe HTTP
surface.

No new execution semantics are introduced. All Phase 1–8 invariants are
preserved. The API is a **transport adapter only** — it routes requests to
the existing session and execution layers without modifying them.

---

## Phase Prerequisite

Phase 9 depends on Phase 8 being complete and tagged.

Specifically:

- the dialogue session layer (`DialogueSession`, `run_turn()`, session shell CLI)
  must be stable — Phase 9 wraps these, it does not replace them
- the session persistence contract (`save_session` / `load_session`) must be
  stable — Phase 9 API endpoints rely on it for state management between requests
- `pytest` and invariant validator both passing at Phase 8 close

No Phase 9 code may be written until Phase 8 is tagged `v0.8.0`.

---

## Invariants That Must Remain True

- deterministic routing (ADR-002)
- bounded execution (ADR-009: max 1 audit pass, max 1 revision pass)
- content-safe output — no prompts, no model output, no memory values in any
  API response payload (ADR-003 extended to HTTP surface)
- session loop bounded by hard `SESSION_MAX_TURNS` ceiling
- steward gate evaluated at each turn boundary (ADR-024 §5.3)
- no execution bypass through the API — all requests must route through the
  session layer; no direct engine calls
- memory writes never triggered automatically (ADR-022 §7)
- `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 9
- all Phase 1–8 invariants preserved in full

---

## What Phase 9 May Add

- a thin HTTP API layer over the existing session and run surfaces
- Server-Sent Events for streaming turn output (content-safe event schema)
- webhook callbacks for `SESSION_COMPLETE`, `RUNBOOK_COMPLETE`, and
  `STEWARD_GATE_TRIGGERED` lifecycle events (content-safe payloads)
- structured JSON output and machine-readable exit codes for the CLI
- a self-hosted web UI as a thin frontend over the M9.1 API and M9.2 SSE stream

---

## What Phase 9 Must Not Add

- new execution semantics below the API layer — the session and engine layers
  are frozen
- raw model output in any API response or SSE event payload
- API endpoints that bypass the session layer (no direct engine endpoints)
- autonomous session creation or turn execution without an explicit client request
- authentication or authorisation systems (out of scope for this phase)
- cloud deployment infrastructure or SaaS-mode operation

---

## Key Design Constraint — Transport Adapter Only

The API must not introduce any execution logic that is not already present in
the session layer.

Every HTTP endpoint maps to an existing CLI operation:

| HTTP endpoint | CLI equivalent |
|---|---|
| `POST /run` | `python -m io_iii run` |
| `POST /runbook` | `python -m io_iii run --runbook` |
| `POST /session/start` | `python -m io_iii session start` |
| `POST /session/{id}/turn` | `python -m io_iii session continue` |
| `GET /session/{id}/state` | `python -m io_iii session status` |
| `DELETE /session/{id}` | `python -m io_iii session close` |

If a new capability is needed in the API, it must first be implemented in the
session layer and CLI, then exposed via the transport adapter. The API is never
the primary implementation site for runtime behaviour.

---

## Content Safety Extension to HTTP

ADR-003 content-safety invariants apply to all HTTP response bodies and SSE
event payloads:

**Never include in any response:**
- prompt text (user or system)
- model output or completion content
- persona definition content
- memory record values
- config file paths or model names

**Safe to include:**
- session identifiers
- turn counts and status codes
- latency metrics
- error codes (from ADR-013 taxonomy)
- structural field values (`session_mode`, `persona_mode`, `route_id`)
- content-safe telemetry (token counts as integers, not as prompt references)

---

## Milestones

### M9.0 — Phase 9 ADR and Milestone Definition ✓

Author ADR governing the API-as-transport-adapter contract.
Confirm Phase 8 is tagged `v0.8.0` before proceeding.
Define all Phase 9 milestones formally in SESSION_STATE.md.

**Delivered:** `ADR/ADR-025-api-integration-surface.md`

---

### M9.1 — HTTP API Layer ✓

Introduces the core REST surface over the existing session and run operations.

#### M9.1 Endpoints

| Method | Path | Maps to |
|---|---|---|
| `POST` | `/run` | Single-turn execution via `engine.run()` |
| `POST` | `/runbook` | Runbook execution via `orchestrator.run()` |
| `POST` | `/session/start` | `new_session()` + optional first turn |
| `POST` | `/session/{id}/turn` | `run_turn()` on existing session |
| `GET` | `/session/{id}/state` | `session_status_summary()` |
| `DELETE` | `/session/{id}` | `session.status = closed` + `save_session()` |

#### M9.1 Properties

- all responses are content-safe JSON (ADR-003)
- error responses use the ADR-013 failure code taxonomy
- no stateful session data stored server-side beyond what `save_session()` already
  persists — the API is stateless at the HTTP layer
- steward gate pause surfaced as a structured response payload, not an HTTP error

---

### M9.2 — Event Streaming ✓

Server-Sent Events on `/session/{id}/stream` for real-time turn feedback.

#### M9.2 Properties

- content-safe event schema: event types carry structural metadata only
- no raw model output in any event payload
- event types mirror the lifecycle taxonomy from ADR-003 and the runbook runner:
  `turn_started`, `turn_completed`, `steward_gate_triggered`, `session_closed`
- clients that do not consume the stream receive the same content-safe JSON
  response from `POST /session/{id}/turn` — streaming is opt-in
- stream terminates cleanly on `session_closed` or `SESSION_AT_LIMIT`

---

### M9.3 — External Integration Contracts ✓

Webhook callbacks on governed lifecycle events.

#### M9.3 Webhook Events

| Event | Trigger |
|---|---|
| `SESSION_COMPLETE` | Session status transitions to `closed` |
| `RUNBOOK_COMPLETE` | `RunbookResult.status` is `completed` |
| `STEWARD_GATE_TRIGGERED` | `PauseState` emitted by `StewardGate` |

#### M9.3 Properties

- webhook payloads are content-safe — same constraints as API response bodies
- webhook destination is declared in `runtime.yaml`; absent = no webhooks fired
- webhook delivery is best-effort; no retry queue introduced in this milestone
- no webhook payload contains prompt text, model output, or memory values

---

### M9.4 — CLI Surface Improvements ✓

Machine-readable output and structured exit codes for shell pipeline and CI/CD
integration.

#### M9.4 Additions

- `--output json` flag on all primary CLI commands: `run`, `session start`,
  `session continue`, `session status`, `session close`
- structured exit codes: `0` (success), `1` (execution error), `2`
  (configuration error), `3` (steward gate pause requiring action)
- `--output json` output schema follows the same content-safe constraints as
  M9.1 API responses

---

### M9.5 — Self-Hosted Web UI ✓

A thin frontend over the M9.1 API and M9.2 SSE streaming.

#### M9.5 Properties

- chat-style session interface driven entirely by the M9.1 API
- all requests route through the session layer — no execution bypass permitted
- UI displays content-safe session metadata only: session ID, turn count,
  session mode, status, latency; never raw model output
- model responses are surfaced to the user through the UI only after passing
  through the session layer's content-safe output path
- self-contained static build; no external dependencies or cloud services
- governed entry point only: session must be explicitly started before
  any turn can be submitted

---

## Definition of Done

Phase 9 is complete when:

- [x] Phase 9 governing ADR accepted and indexed
- [x] M9.1–M9.5 milestones delivered
- [x] all API responses and SSE event payloads pass content-safety review (ADR-003)
- [x] no endpoint bypasses the session layer — verified by test suite
- [x] steward gate pause correctly surfaced through HTTP layer
- [x] `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 9
- [x] `pytest` passing (1046 passing, 19 pre-existing failures)
- [x] invariant validator passing
- [x] SESSION_STATE.md updated with phase close state
- [x] repository tagged `v0.9.0`