---
id: ADR-026
title: Governed Content Release Gate
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-9
audience:
  - developer
  - maintainer
  - operator
created: "2026-04-13"
updated: "2026-04-13"
tags:
  - io-iii
  - adr
  - phase-9
  - api
  - content-safety
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
---

# ADR-026 — Governed Content Release Gate

## 1. Context

ADR-003 and ADR-025 establish a content-safety invariant for the IO-III API surface:
no model output, prompt text, persona content, or memory values appear in any API
response body or SSE event.

This invariant protects against unintended data exposure in multi-tenant, logged, or
audited deployments. It is the correct default posture.

However, in operator-controlled deployments where the API surface is the primary user
interface (e.g. the self-hosted web UI from M9.5), the invariant renders the system
non-functional as a dialogue tool: users cannot see model responses.

This ADR introduces a **governed, opt-in content release gate** that allows operators to
explicitly enable model response surfacing at the API boundary. The gate is off by default.
All other content-safety invariants remain unchanged.

---

## 2. Decision

A new `content_release` key is added to `runtime.yaml`. It is `false` by default.

```yaml
# runtime.yaml
content_release: false   # set to true to enable model response in API responses
```

When `content_release: true`:

- The `/run` endpoint includes a `response` field in its JSON response body containing
  the model's output text.
- The `/session/{id}/turn` endpoint includes a `response` field in its JSON response body.
- All other content-safety invariants remain in force: `prompt`, `persona_content`,
  `value`, `logging_policy` are never surfaced. SSE event payloads remain structural
  metadata only.

When `content_release: false` (default):

- Behaviour is identical to ADR-025: `message` is stripped from all responses.
- No model output appears anywhere in the API surface.

---

## 3. Response Field Contract

The released field is named `response`, not `message`.

Rationale: `message` is an internal engine key. `response` is the explicit, operator-
approved API contract name. This distinction makes the release intentional and auditable.

Field value: the raw model output string as produced by the execution engine.

Field presence: only present when `content_release: true` AND the execution succeeded
and produced output. Absent (not null) when disabled or when no output was produced.

---

## 4. Gate Mechanics

The gate is evaluated per-request at the API boundary by reading the `runtime` section
of the loaded configuration. It is not cached at process startup, so operators can change
the setting without a server restart.

Implementation path:

```
runtime.yaml: content_release: true/false
    ↓
io_iii.api.app._content_release_enabled()   # reads config per-request
    ↓
_extract_response(result, enabled)           # conditionally adds response field
    ↓
JSONResponse(content=result)                 # response field present or absent
```

The gate does not bypass `_strip_content()`. The strip runs first; the `response` field
is then added back explicitly only when the gate is open.

---

## 5. Invariants Preserved

This ADR amends ADR-003 and ADR-025 for the `response` field only. All other invariants
are unchanged:

| Invariant | Status |
|---|---|
| `prompt` never in API response | Preserved |
| `persona_content` never in API response | Preserved |
| `value` (memory) never in API response | Preserved |
| `logging_policy` never in API response | Preserved |
| SSE events contain structural metadata only | Preserved |
| Content release is operator opt-in (off by default) | New invariant |
| `response` absent unless gate explicitly opened | New invariant |

---

## 6. Operational Guidance

Operators enabling `content_release: true` accept responsibility for:

- Ensuring the API is not exposed to untrusted clients without authentication.
- Understanding that model output will appear in API response logs.
- Reviewing their data retention and logging policy before enabling.

The IO-III runtime does not enforce access control. That is the operator's concern.

---

## 7. Non-Goals

This ADR does not:

- Enable prompt text in API responses.
- Enable memory values in API responses.
- Enable SSE event content release.
- Add per-request content release control (operator-level only).
- Introduce authentication or access control.

---

## 8. Supersedes / Amends

- Amends ADR-003 §3 (logging policy) — `response` field is explicitly released when gate open.
- Amends ADR-025 §1 (content-safety) — adds governed exception for `response` field.