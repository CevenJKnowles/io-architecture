---
id: ADR-025
title: API-as-Transport-Adapter Contract (Phase 9)
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-9
audience:
  - developer
  - maintainer
created: "2026-04-13"
updated: "2026-04-13"
tags:
  - io-iii
  - adr
  - phase-9
  - api
  - http
  - transport
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M9.0
---

# ADR-025 — API-as-Transport-Adapter Contract (Phase 9)

## Status

Accepted

---

## Context

Phases 1–8 deliver a governed, deterministic LLM control-plane runtime with CLI-only access.
Phase 9 introduces an HTTP surface so that the runtime can be driven programmatically over a
network without requiring shell access.

The risk: every previous API surface added to a CLI-first runtime has drifted toward adding
new execution semantics at the transport layer — custom routing logic, result filtering, or
stateful management that duplicates or bypasses what the CLI layer enforces.

IO-III cannot afford this drift. All execution semantics, governance invariants, and
content-safety rules live in the session and engine layers (Phases 1–8). These layers are
the only place those rules exist; duplicating them in the HTTP layer would create a
maintenance split, and bypassing them would break every invariant established in ADR-001
through ADR-024.

---

## Decision

### §1 The Transport-Adapter Rule

The Phase 9 HTTP API is a **transport adapter only**.

Every HTTP endpoint is a thin wrapper that:
1. Deserialises the HTTP request body into the same arguments accepted by the corresponding
   CLI command function (`cmd_run`, `cmd_runbook`, `cmd_session_start`, etc.).
2. Delegates execution to that CLI command function (or, equivalently, the domain functions
   it calls).
3. Serialises the command's structured output as the HTTP response.

No endpoint may:
- Add new execution semantics not already present in the CLI layer.
- Bypass, short-circuit, or replace the session/engine execution path.
- Expose raw prompt text, model output, persona content, or memory values in any response
  or log field (ADR-003 content-safety rules apply without relaxation).
- Own state that duplicates or conflicts with `DialogueSession` or `SessionState`.

### §2 Route-to-Command Mapping

| HTTP endpoint                        | Wrapped CLI function         |
|--------------------------------------|------------------------------|
| `POST /run`                          | `cmd_run`                    |
| `POST /runbook`                      | `cmd_runbook`                |
| `POST /session/start`                | `cmd_session_start`          |
| `POST /session/{id}/turn`            | `cmd_session_continue`       |
| `GET  /session/{id}/state`           | `cmd_session_status`         |
| `DELETE /session/{id}`               | `cmd_session_close`          |
| `GET  /session/{id}/stream`          | SSE event bus (see §4)       |
| `GET  /`                             | Static web UI (see §5)       |
| `GET  /health`                       | Liveness probe (no exec)     |

### §3 Invocation Mechanism

The API layer calls CLI command functions by constructing an `argparse.Namespace` from the
request body fields, then calling the function directly. Stdout is captured via
`contextlib.redirect_stdout` + `io.StringIO`. The captured JSON output is parsed and returned
as the HTTP response body. Exit code 0 → HTTP 200; exit code 1 → HTTP 422 (unprocessable)
or HTTP 500 (runtime error), preserving the structured error payload.

This mechanism ensures:
- Every API call passes through exactly the same code path as the CLI.
- Monkeypatching and integration tests applied to the CLI layer remain valid for the API.

### §4 SSE Event Stream (M9.2)

`GET /session/{id}/stream` yields Server-Sent Events. Events are content-safe (ADR-003):
they carry structural metadata only (session_id, turn_index, status, latency_ms) — never
prompt text, model output, or memory values.

Defined event types:

| event type               | when fired                                      |
|--------------------------|-------------------------------------------------|
| `session_state`          | immediately on stream connect (current state)   |
| `turn_started`           | before `cmd_session_continue` runs              |
| `turn_completed`         | after `cmd_session_continue` returns            |
| `steward_gate_triggered` | when session status transitions to `paused`     |
| `session_closed`         | when session status transitions to `closed`     |
| `keepalive`              | every 30 s while no other event is pending      |

The SSE stream is read-only. It observes; it does not drive execution.

### §5 Static Web UI (M9.5)

`GET /` serves a single static HTML file. The UI communicates with the API exclusively
through the HTTP endpoints defined in §2. It does not add execution semantics, bypass
the session layer, or expose content-unsafe data. All API calls made by the UI follow
the same content-safety constraints as any other client.

### §6 Webhook Dispatch (M9.3)

The server may fire a configurable webhook URL (`runtime.yaml: webhook_url`) on the
following events: `SESSION_COMPLETE`, `RUNBOOK_COMPLETE`, `STEWARD_GATE_TRIGGERED`.
Webhooks are fire-and-forget (non-blocking). Payloads are content-safe: structural
metadata only, no prompt text or model output (ADR-003).

### §7 CLI Serve Command

A `serve` subcommand is added to the IO-III CLI:

```
python -m io_iii serve [--host HOST] [--port PORT]
```

Default: `0.0.0.0:8080`. The serve command starts the HTTP server. It does not modify
any existing CLI command behaviour.

### §8 --output json Flag (M9.4)

All commands that produce structured output (`run`, `runbook`, `session start`,
`session continue`, `session status`, `session close`) gain a formal `--output json`
flag. Since all commands already emit JSON, this flag is a declaration of machine-readable
contract rather than a behaviour change. Structured exit codes: 0 = success, 1 = error.

### §9 Invariant Preservation

All invariants established in ADR-001 through ADR-024 apply without modification to the
Phase 9 API surface. The HTTP layer introduces zero new execution invariants.

---

## Consequences

### Positive
- Remote programmatic access to IO-III without requiring shell access.
- All governance, audit, and content-safety rules enforced uniformly across CLI and API.
- Minimal implementation surface: endpoints are thin; no duplicated logic.
- SSE stream enables real-time monitoring without polling.
- Webhook dispatch enables integration with external systems.
- Web UI enables direct browser interaction with the runtime.

### Negative / Trade-offs
- Invocation-via-redirect-stdout is an unconventional integration seam; it requires that
  CLI command functions remain stdout-based rather than return-value-based.
- SSE stream is poll-based internally (event log with cursor); not push-optimised.
- Single-process server: concurrent SSE streams and turn execution share a threadpool;
  not designed for high concurrency.

### Risks
- **Transport drift**: future contributors must not add execution semantics in
  `io_iii/api/`. The Transport-Adapter Rule (§1) must be enforced at review time.
- **Content-safety regression**: any addition of prompt/output fields to API responses
  or SSE events violates ADR-003 and must be rejected.

---

## Compliance

| Rule                                 | Enforced by                                  |
|--------------------------------------|----------------------------------------------|
| Transport-adapter only (§1)          | Code review; no exec logic in api/           |
| Route-to-command mapping (§2)        | `app.py` route handlers                      |
| Content-safe responses (ADR-003)     | No `message`/`prompt` in response bodies     |
| Content-safe SSE events (§4)         | Event schema: structural metadata only       |
| Content-safe webhook payloads (§6)   | Payload schema: structural metadata only     |
| Invariant preservation (§9)          | All ADR-001–ADR-024 remain in force          |