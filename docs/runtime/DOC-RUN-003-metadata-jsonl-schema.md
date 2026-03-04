---
id: DOC-RUN-003
title: IO-III Metadata Log Schema (metadata.jsonl)
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
  - logging
  - metadata
roles_focus:
  - executor
  - challenger
provenance: human
---

# IO-III Metadata Log Schema (metadata.jsonl)

---

## Purpose

This document defines the canonical schema for IO-III runtime metadata logs:

- `architecture/runtime/logs/metadata.jsonl`

The metadata log provides **content-safe observability** for IO-III executions.

It exists to support:
- deterministic auditability
- debugging of routing and governance decisions
- performance monitoring (latency)
- invariant-aligned enforcement of “content OFF” logging

---

## Core Principle: Metadata Only

The metadata log must never contain:
- user prompts
- assembled prompts
- model outputs
- revisions
- tool inputs/outputs
- any free-form text derived from content

Any entry that includes content is a **logging policy violation**.

---

## File Format

- JSON Lines (JSONL): one JSON object per line
- UTF-8 encoding
- Append-only
- Each entry represents exactly one IO-III run (one request_id)

---

## Schema Versioning

Each entry MUST include:

- `schema`: string, fixed identifier for the logging schema
- `schema_version`: semantic version string (e.g. `v1.0`)

Forward compatibility rule:
- new optional keys may be added without breaking v1
- required keys must not be removed without a major version bump

---

## Required Fields (v1.0)

Each log entry MUST include these keys.

| Field | Type | Description |
|---|---|---|
| `schema` | string | e.g. `io-iii-metadata-jsonl` |
| `schema_version` | string | e.g. `v1.0` |
| `timestamp_ms` | integer | Unix epoch milliseconds captured at log-write time |
| `request_id` | string | unique identifier for the run |
| `mode` | string | execution mode (e.g. `executor`) |
| `route_id` | string | resolved route identifier |
| `provider` | string | resolved provider name (`null`, `ollama`) |
| `model` | string \| null | resolved model identifier (if applicable) |
| `audit_enabled` | boolean | explicit toggle state |
| `audit_passes` | integer | bounded by ADR-009 |
| `revision_passes` | integer | bounded by ADR-009 |
| `audit_verdict` | string \| null | `pass` \| `needs_work` \| null |
| `revised` | boolean | whether a revision occurred |
| `latency_ms` | integer \| null | end-to-end runtime latency |
| `prompt_hash` | string \| null | deterministic hash of assembled prompt (content-safe) |

---

## Optional Fields (v1.0)

Optional keys may be included to support debugging and governance traceability.

| Field | Type | Description |
|---|---|---|
| `fallback_used` | boolean | route fallback indicator |
| `fallback_reason` | string \| null | short enumerated reason (no content) |
| `logging_policy` | object | resolved logging policy snapshot (content-off) |
| `provider_host` | string \| null | host used for provider (safe infrastructure metadata) |
| `error_code` | string \| null | stable error code if status is error |
| `status` | string \| null | `ok` \| `error` |
| `capability_id` | string \| null | explicit capability ID (if invoked) |
| `capability_ok` | boolean \| null | capability invocation success flag (summary only) |
| `capability_version` | string \| null | capability version (summary only) |
| `capability_duration_ms` | integer \| null | capability invocation duration in ms (summary only) |
| `capability_error_code` | string \| null | capability error code (summary only; no messages) |
| `trace_steps` | integer \| null | number of recorded execution trace steps |
| `trace_total_ms` | integer \| null | sum of trace step durations |

---

## Forbidden Keys / Patterns

The following keys must never appear in metadata.jsonl entries:

- `prompt`
- `user_prompt`
- `system_prompt`
- `assembled_prompt`
- `message`
- `output`
- `completion`
- `draft`
- `revision`
- `content`
- any field containing raw free-form text derived from user/model content

If a future feature requires logging content, it must be implemented under a separate file and policy, and must be disabled by default.

---

## Security and Privacy Constraints

- Content must remain disabled by default (ADR-003 / logging policy).
- Log retention and export policy must remain governed by ADRs.
- Metadata.jsonl is considered safe for internal debugging but must still be treated as sensitive system telemetry.

---

## Acceptance Criteria (v1.0)

M3.4 is complete when:

1. This schema exists as a canonical document.
2. Runtime metadata logging code produces entries that comply with the schema.
3. Tests enforce:
   - presence of required keys
   - absence of forbidden content keys (recursive scan; nested structures included)
   - bounded audit fields remain within contract limits

---

## Summary

`metadata.jsonl` is a content-safe observability channel for IO-III.

It records deterministic runtime facts:
- what route was selected
- what provider/model was used
- whether audit/revision occurred (bounded)
- how long execution took
- a safe prompt hash for traceability

It must never store user or model content.