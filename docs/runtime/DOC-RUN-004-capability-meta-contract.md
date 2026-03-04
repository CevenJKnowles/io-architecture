---
id: "DOC-RUN-004"
title: "Capability Result Metadata Contract"
type: "runtime"
status: "active"
version: ""
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-04"
updated: "2026-03-04"
tags:
  - "runtime"
  - "capabilities"
  - "metadata"
roles_focus:
  - "executor"
  - "challenger"
provenance: "mixed"
---

# Capability Result Metadata Contract

## Purpose

When a capability is explicitly invoked, the engine attaches a structured object at:

- `ExecutionResult.meta["capability"]`

This document defines the **shape**, **content-safety requirements**, and **bounds** for that object.

---

## Contract

### Required top-level keys

`meta["capability"]` MUST be a mapping containing:

- `capability_id` (string)
- `version` (string)
- `ok` (boolean)

### Optional keys

- `error` (string) — present only when `ok=false`
- `output` (object) — present only when `ok=true` and output is available

### Forbidden content

The capability meta object MUST NOT include any of the forbidden content keys (directly or nested):

- `prompt`
- `completion`
- `draft`
- `revision`
- `content`

It also MUST NOT contain raw LLM transcripts or other user content.

---

## Bounds

The capability layer is **single-shot** and bounded.

Engine and capability implementations MUST enforce:

- payload size ≤ `CapabilityBounds.max_input_chars`
- output size ≤ `CapabilityBounds.max_output_chars`
- call count ≤ `CapabilityBounds.max_calls` (must remain 1 for v0)

If bounds are exceeded, the engine should:
- fail the invocation deterministically
- return `ok=false` with a short, non-content error message

---

## Example (content-safe)

```json
{
  "capability_id": "text.normalize",
  "version": "v0",
  "ok": true,
  "output": {
    "changes": 3,
    "strategy": "nfkc"
  }
}
```

Example error:

```json
{
  "capability_id": "text.normalize",
  "version": "v0",
  "ok": false,
  "error": "payload exceeds max_input_chars"
}
```

---

## Logging guidance

The capability meta object may be included in metadata logs **only if** it remains content-safe and respects the forbidden key guard rules.

If in doubt:
- log only `{capability_id, version, ok, error}` and omit `output`.