---
id: DOC-RUN-005
title: IO-III Execution Trace Schema (ExecutionResult.meta.trace)
type: runtime
status: active
version: v1.0
canonical: true
scope: io-iii
audience: engineers
created: "2026-03-04"
updated: "2026-03-04"
tags:
  - runtime
  - observability
  - trace
  - schema
roles_focus:
  - executor
  - challenger
provenance: human
---

# IO-III Execution Trace Schema (ExecutionResult.meta.trace)

---

## Purpose

This document defines the canonical schema for the **content-safe execution trace** attached to:

- `ExecutionResult.meta["trace"]`

The trace provides structural observability (timings and stage ordering) without logging content.

---

## Core Principle: Content-Safe Only

The trace must never contain:

- user prompts
- assembled prompts
- model outputs
- drafts or revisions
- capability payloads or outputs

Only structural metadata is allowed.

---

## Schema Versioning

Every trace object MUST include:

- `schema`: fixed identifier string
- `schema_version`: semantic version string

Forward compatibility rule:

- new optional fields may be added without breaking v1
- required fields must not be removed without a major version bump

---

## Trace Object (v1.0)

Required fields:

| Field | Type | Description |
|---|---|---|
| `schema` | string | fixed identifier: `io-iii-execution-trace` |
| `schema_version` | string | e.g. `v1.0` |
| `trace_id` | string | stable identifier (typically equals `request_id`) |
| `started_at_ms` | integer | epoch milliseconds (trace start) |
| `steps` | array | ordered list of trace steps |

---

## Trace Step (v1.0)

Each entry in `steps` MUST be an object with:

| Field | Type | Description |
|---|---|---|
| `stage` | string | stage identifier (enumerated by engine integration) |
| `started_at_ms` | integer | epoch milliseconds (step start) |
| `duration_ms` | integer | elapsed time for the step |
| `meta` | object | small structural metadata (content-safe) |

`meta` guidelines:

- allowed values: strings, numbers, booleans, null
- keep the object small
- do not include any free-form text derived from prompts or outputs

---

## Stage Identifiers

Stage identifiers are stable strings.

Current canonical stages (v1.0):

- `capability_invoke`
- `context_assembly`
- `provider_inference`
- `challenger_audit`
- `revision_inference`
- `provider_run` (null provider path)

---

## Example

```json
{
  "schema": "io-iii-execution-trace",
  "schema_version": "v1.0",
  "trace_id": "1719829123-12345",
  "started_at_ms": 1719829123123,
  "steps": [
    {
      "stage": "context_assembly",
      "started_at_ms": 1719829123124,
      "duration_ms": 8,
      "meta": {"route_id": "executor"}
    },
    {
      "stage": "provider_inference",
      "started_at_ms": 1719829123132,
      "duration_ms": 842,
      "meta": {"provider": "ollama", "model": "qwen3:8b"}
    }
  ]
}
```

---

## Acceptance Criteria

M3.8 is complete when:

1. Engine attaches `meta.trace` for all execution paths.
2. Trace objects follow this schema.
3. Tests enforce schema stability and absence of forbidden content keys.