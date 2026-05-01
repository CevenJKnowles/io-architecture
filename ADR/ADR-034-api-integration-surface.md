> Renumbered from ADR-025 on 2026-05-01. Original ADR-025 number was a duplicate.

---
id: ADR-025
title: API & Integration Surface — Transport Adapter Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-9
audience:
  - developer
  - maintainer
created: "2026-04-12"
updated: "2026-04-12"
tags:
  - io-iii
  - adr
  - phase-9
  - api
  - http
  - integration
  - transport
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M9.0
---

# ADR-025 — API & Integration Surface — Transport Adapter Contract

## Status

Accepted

---

## Context

Phase 8 is complete. IO-III is conversational: it supports bounded session loops,
steward governance gates, conditional runbook branches, and session continuity via
memory. All execution passes through `orchestrator.run()` above a frozen engine stack.

Phase 9 wraps this surface in a thin HTTP transport layer. The purpose is to allow
external clients — shell scripts, CI/CD pipelines, other services, and a self-hosted
web UI — to access the existing runtime without learning the CLI interface.

Without this ADR:

- The boundary between transport concerns and execution concerns would be unspecified,
  creating risk of execution logic being introduced inside API handlers
- Content-safety invariants (ADR-003) have no explicit extension to the HTTP surface
- The relationship between HTTP endpoints and existing CLI operations would be implicit
- The webhook and SSE contracts would have no governance baseline

This ADR formalises the **transport adapter contract**, the content-safety extension to
HTTP, the endpoint-to-CLI mapping, and the constraints that govern all Phase 9 code.

---

## Decision

### §1 — Transport Adapter Principle

The API layer is a **transport adapter only**. It translates HTTP requests into calls
to the existing session and execution layer. It does not:

- introduce new execution semantics
- bypass the session layer
- store state beyond what `save_session()` already persists
- make autonomous decisions about routing, mode, or persona

Every HTTP endpoint maps to an existing CLI operation. If a capability is needed in the
API that does not exist in the CLI, it must first be implemented in the CLI, then exposed
via the transport adapter.

### §2 — Module Location

All Phase 9 code lives in `io_iii/api/`. The CLI subpackage (`io_iii/cli/`) is not
modified except for M9.4 (structured output and exit codes). The engine, routing, and
telemetry modules remain frozen.

```
io_iii/api/
  __init__.py
  server.py        — HTTPServer + request handler + `serve` CLI entrypoint
  _handlers.py     — request → session layer dispatch
  _sse.py          — SSE event format + session stream handler
  _webhooks.py     — webhook dispatcher (best-effort; no retry queue)
  static/
    index.html     — self-hosted web UI (M9.5)
```

### §3 — Endpoint-to-CLI Mapping

| Method | Path | CLI equivalent |
|--------|------|----------------|
| `POST` | `/run` | `python -m io_iii run {mode}` |
| `POST` | `/runbook` | `python -m io_iii runbook {file}` |
| `POST` | `/session/start` | `python -m io_iii session start` |
| `POST` | `/session/{id}/turn` | `python -m io_iii session continue` |
| `GET`  | `/session/{id}/state` | `python -m io_iii session status` |
| `DELETE` | `/session/{id}` | `python -m io_iii session close` |
| `GET`  | `/session/{id}/stream` | (SSE; no CLI equivalent — M9.2) |
| `GET`  | `/` | (web UI; no CLI equivalent — M9.5) |

### §4 — Content Safety on the HTTP Surface (ADR-003 Extension)

ADR-003 content-safety invariants apply to all HTTP response bodies and webhook payloads.

**Never include in machine-readable API responses or webhook payloads:**
- prompt text (user or system)
- memory record values
- persona definition content
- config file paths or model names

**Safe to include in all responses:**
- session identifiers, turn counts, status codes
- latency metrics (integer milliseconds)
- error codes from the ADR-013 taxonomy
- structural field values: `session_mode`, `persona_mode`, `route_id`
- content-safe telemetry (token counts as integers)

**`POST /run` and `POST /runbook`** are the primary execution output surfaces,
analogous to `cmd_run()` printing `result.message` to stdout. These responses
include model output because they are the direct user-facing result. The same
content is never written to `metadata.jsonl`.

**Session endpoints** (`POST /session/{id}/turn`, `GET /session/{id}/state`,
`DELETE /session/{id}`) return content-safe governance metadata only, matching the
Phase 8 session shell output contract.

**`GET /session/{id}/stream`** is the SSE output surface for session turns. SSE
events carry a mix of governance metadata events (content-safe) and a single
`turn_output` event containing the model response. The `turn_output` event is
the user-facing result, not a logged or forwarded payload.

**Webhook payloads** (M9.3) are strictly content-safe. They carry lifecycle
event metadata only — never model output, prompt text, or memory values.

### §5 — SSE Contract (M9.2)

The SSE endpoint `GET /session/{id}/stream?prompt=TEXT` executes one bounded session
turn and streams the result as a sequence of Server-Sent Events.

Event sequence:
1. `turn_started` — content-safe: `session_id`, `turn_index`, `persona_mode`
2. `turn_output` — model response text (the user-facing result)
3. `turn_completed` — content-safe governance metadata (matches `_emit_turn_result`)
4. `steward_gate_triggered` — emitted instead of `turn_completed` if gate fires

The SSE connection closes after the final event. Execution is synchronous — the
engine is frozen and does not support token streaming. Pseudo-streaming is used:
events are emitted after the full turn completes.

The `turn_output` event is NOT included in any log, webhook, or persisted field.

### §6 — Webhook Contract (M9.3)

Webhook destinations are declared in `runtime.yaml` under a `webhooks:` key.

```yaml
webhooks:
  session_complete:
    url: "http://localhost:9000/webhook"
  runbook_complete:
    url: "http://localhost:9000/webhook"
  steward_gate_triggered:
    url: "http://localhost:9000/webhook"
```

Absent `webhooks:` key is the safe default — no webhooks are fired.

Webhook delivery is best-effort: single attempt, 5-second timeout, no retry queue.
Delivery failures are silent — they do not affect execution or session state.

All webhook payloads are strictly content-safe (§4).

### §7 — Structured Exit Codes (M9.4)

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Execution error (provider failure, engine error, runtime exception) |
| 2 | Configuration error (PORTABILITY_CHECK_FAILED, CONSTELLATION_DRIFT, invalid args) |
| 3 | Steward gate pause — session paused, awaiting action |

Exit code 3 is emitted by `session continue` when the session enters a paused state
and no `--action` argument resolves it. Callers must inspect the JSON output and
supply `--action approve`, `--action redirect`, or `--action close`.

### §8 — Server Entrypoint (M9.1)

The API server is launched via:

```bash
python -m io_iii serve [--host 127.0.0.1] [--port 8080]
```

Default: `127.0.0.1:8080` (loopback only; no external binding by default).

The server uses Python stdlib `http.server` — no external framework dependency.
`PyYAML` remains the only runtime dependency.

### §9 — Web UI Contract (M9.5)

The web UI is a single static HTML file served at `GET /`. It:

- manages session lifecycle (start, turn, status, close) via the M9.1 API
- receives model output via the M9.2 SSE stream
- never issues requests that bypass the session layer
- never displays raw internal state (config paths, model names, memory values)
- requires no build step and no external JavaScript frameworks

---

## Consequences

- The API layer is safe to add without modifying the execution stack
- Content-safety invariants remain structurally enforced — no new log fields are
  introduced that could carry model output
- The `http.server` stdlib choice keeps the zero-external-dependency constraint
  outside PyYAML intact
- Webhook delivery failure does not affect runtime behaviour — no coupling
- Exit code 3 gives CI/CD consumers a stable signal for steward gate pauses
- The SSE endpoint is the only path that carries model output to a remote client;
  it is never logged or forwarded

---

## Implementation Notes

- `io_iii/api/server.py` must not import `io_iii.core.engine` directly — all
  execution must go through the handlers which call session-layer functions
- Path routing uses simple string splitting; no regex dependency
- JSON request bodies decoded with `json.loads`; malformed bodies return HTTP 400
  with `INVALID_REQUEST_BODY` error code
- The server is single-threaded (no `ThreadingMixIn`) — suitable for local
  self-hosted use; not designed for concurrent production load