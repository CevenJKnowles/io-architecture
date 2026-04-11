---
id: ADR-022
title: Memory Architecture Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-6
audience:
  - developer
  - maintainer
created: "2026-04-12"
updated: "2026-04-12"
tags:
  - io-iii
  - adr
  - phase-6
  - memory
  - memory-pack
  - context-assembly
  - snapshot
roles_focus:
  - executor
  - challenger
  - governance
provenance: io-iii-runtime-development
milestone: M6.0
---

# ADR-022 — Memory Architecture Contract

## Status

Accepted

---

## Context

Phase 5 is complete. All three Phase 5 milestones are implemented and tested:

- M5.1 (token pre-flight estimator) is active — the prerequisite for Phase 6 M6.4 is
  satisfied
- M5.2 (execution telemetry) is active
- M5.3 (constellation integrity guard) is active

The execution stack is frozen at the M4.11 / M5.3 boundary. The repository is tagged
`v0.5.0`.

Phase 6 introduces governed, deterministic memory into the IO-III runtime. The existing
execution stack — routing, engine, context assembly, capability registry, runbook runner,
and replay/resume — remains frozen. Memory is introduced as a governed input to context
assembly, not as a new execution layer.

The purpose of this phase is to allow curated, scoped context to be injected into
execution without introducing retrieval autonomy, persistent session state, or dynamic
routing.

---

## Decision

IO-III introduces a memory architecture under Phase 6. All seven milestones (M6.1–M6.7)
are governed by this ADR. The frozen Phase 1–5 execution stack is not modified by this
ADR or any milestone it governs.

Memory is:

- **deterministic** — lookup is by key or pack name, never by search or ranking
- **bounded** — injection is constrained by the M5.1 token budget
- **governed** — access requires explicit allowlist entries; writes require explicit user
  confirmation
- **content-safe** — memory values never appear in any log field

---

## 1. Governance Freeze Boundary

### 1.1 Frozen surface

The following components are frozen for the duration of Phase 6. No Phase 6 milestone
may modify them:

- `io_iii/routing.py` — routing resolution logic
- `io_iii/core/engine.py` — execution engine (execution flow, audit gates, revision paths)
- `io_iii/core/runbook.py` — runbook definition
- `io_iii/core/runbook_runner.py` — bounded runner
- `io_iii/core/replay_resume.py` — replay/resume execution layer
- `io_iii/core/preflight.py` — token pre-flight estimator (read from Phase 6; not modified)
- `io_iii/core/telemetry.py` — execution telemetry (read from Phase 6; not modified)
- `io_iii/core/constellation.py` — constellation integrity guard
- All ADR-002, ADR-008, ADR-009, ADR-010, ADR-013, ADR-014, ADR-016, ADR-017,
  ADR-020, ADR-021 contracts

### 1.2 Permissible surfaces

Phase 6 milestones may add to or read from:

- `io_iii/core/context_assembly.py` — memory injection in M6.4; memory subset is
  assembled into `ExecutionContext.memory` before the provider call; the assembly
  contract (ADR-010) is not otherwise modified
- `io_iii/core/execution_context.py` — a new `memory` field is added to the dataclass
  to carry the bounded memory subset; all existing fields unchanged
- `io_iii/core/session_state.py` — a `snapshot_path` field may be added for M6.7
  artefact tracking; all existing fields unchanged
- `architecture/runtime/config/` — `memory_packs.yaml`, `memory_retrieval_policy.yaml`,
  and updates to `providers.yaml` for storage root declaration
- `io_iii/memory/` — new module; all memory subsystem code lives here
- `io_iii/cli.py` — to expose `memory write` subcommand (M6.6) and `session export`
  subcommand (M6.7); no modification to existing subcommands

---

## 2. Memory Store Architecture (M6.1)

### 2.1 Record structure

Each memory record is a discrete, versioned unit with the following fields:

| Field | Type | Notes |
| --- | --- | --- |
| `key` | `str` | stable, human-readable identifier; unique within a scope |
| `scope` | `str` | scope identifier; determines access boundaries |
| `value` | `str` | record content; never logged |
| `version` | `int` | monotonically increasing; starts at 1 |
| `provenance` | `str` | one of: `human`, `llm:<slug>`, `mixed` |
| `created_at` | `str` | ISO 8601 timestamp |
| `updated_at` | `str` | ISO 8601 timestamp |
| `sensitivity` | `str` | sensitivity tier: `standard`, `elevated`, `restricted` |

### 2.2 Store properties

- **Atomic** — each write is a single-record operation; no multi-record transactions
- **Scoped** — records are bound to a declared scope identifier; cross-scope access is
  not permitted without an explicit allowlist entry
- **Deterministic lookup** — retrieval is by key within a scope; no search, no ranking,
  no embedding
- **Local-only** — the store is a local file store under the configured storage root;
  no remote persistence

### 2.3 Storage root

The storage root is declared in `architecture/runtime/config/memory_packs.yaml` as a
configurable path. No hardcoded repository path is permitted. This satisfies the Phase 7
portability prerequisite (DOC-ARCH-015 §M6.2 portability note).

---

## 3. Memory Pack System (M6.2)

### 3.1 Pack definition

A memory pack is a named, versioned collection of memory record keys. Packs are declared
in `architecture/runtime/config/memory_packs.yaml`.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `str` | stable pack identifier; e.g. `pack.io_iii.session_resume` |
| `version` | `str` | semantic version string |
| `description` | `str` | human-readable purpose; never logged as a value |
| `scope` | `str` | scope identifier for all records in the pack |
| `keys` | `list[str]` | ordered list of memory record keys |

### 3.2 Pack properties

- Packs are author-controlled — not runtime-generated
- Pack resolution is deterministic from pack `id`
- A pack may not reference keys from multiple scopes
- Packs may be nested (a pack may include all keys from another pack by reference);
  maximum nesting depth is 1; no recursive pack resolution
- An empty pack (zero keys) is valid and resolves to an empty memory subset

### 3.3 Pack example

```yaml
- id: pack.io_iii.session_resume
  version: "1.0"
  description: "Curated context for session continuation"
  scope: io_iii
  keys:
    - session.last_intent
    - session.last_runbook_id
    - session.active_governance_mode
```

---

## 4. Memory Retrieval Policy (M6.3)

### 4.1 Default stance

No memory record is accessible by default. Access is opt-in and declared.

### 4.2 Policy fields

The retrieval policy is declared in `architecture/runtime/config/memory_retrieval_policy.yaml`.

| Field | Type | Notes |
| --- | --- | --- |
| `route_allowlist` | `list[str]` | routes permitted to access memory |
| `capability_allowlist` | `list[str]` | capabilities permitted to access memory |
| `sensitivity_allowlist` | `dict[str, list[str]]` | maps sensitivity tier to permitted routes |

### 4.3 Allowlist rules

- A route not in `route_allowlist` receives an empty memory subset — no error
- A capability not in `capability_allowlist` may not trigger memory access — the
  capability receives no memory context
- Records at `elevated` sensitivity require an explicit entry in
  `sensitivity_allowlist["elevated"]`; records at `restricted` require an explicit entry
  in `sensitivity_allowlist["restricted"]`; `standard` records are accessible to any
  allowlisted route
- Allowlist evaluation is deterministic and config-driven; no runtime modification of
  allowlists is permitted

### 4.4 Policy absence

If no retrieval policy file is present, memory injection is skipped for all routes.
This is not a failure — it is the safe default.

---

## 5. Memory Injection via Context Assembly (M6.4)

**Requires:** M5.1 (token pre-flight estimator) complete and active.

### 5.1 Injection pipeline

```text
memory store
  -> retrieval policy (M6.3): allowlist check
  -> selector: pack id or explicit key list
  -> bounded subset: token budget enforced via M5.1 estimator
  -> ExecutionContext.memory: list[MemoryRecord]
  -> context assembly (ADR-010): memory section appended to assembled prompt
  -> provider call
```

### 5.2 Contract

- Injection occurs after routing resolution and before the provider call
- The memory subset is assembled as part of context assembly (ADR-010); the assembly
  layer is extended, not bypassed
- Subset size is bounded by the token budget derived from `runtime.context_limit_chars`
  (M5.1); records are included in declaration order until the budget is exhausted;
  excluded records are dropped silently (no error)
- If no memory is configured for the current route, injection is skipped and
  `ExecutionContext.memory` is an empty list
- Memory injection does not affect routing, audit gate behaviour, or revision passes
- Memory injection runs identically on first-run, replay, and resume executions

### 5.3 Context assembly extension

The context assembly layer appends a `### Memory` section to the assembled system prompt
when `ExecutionContext.memory` is non-empty. The section contains the key and value of
each injected record in declaration order. The section is omitted when the list is empty.

### 5.4 Content safety

No memory value appears in any log field. The injection step logs:

```text
memory_keys_released: [key1, key2, ...]
memory_records_count: N
memory_total_chars: N
pack_id: <pack_id or "explicit">
```

---

## 6. Memory Safety Invariants (M6.5)

### 6.1 Allowed memory log fields

The following fields are permitted in any log event relating to memory:

```text
memory_keys_released
memory_records_count
memory_total_chars
pack_id
```

### 6.2 Forbidden log fields

The following are never permitted in any log field, at any lifecycle stage:

```text
memory values
record content
free-text record fields (value, description)
```

### 6.3 Invariant validator integration

These invariants are added to the invariant validator suite
(`architecture/runtime/scripts/validate_invariants.py`). The validator asserts:

- no field named `memory_value`, `record_content`, or `record_value` in any log schema
- `ExecutionContext.memory` records are not projected to `metadata.jsonl`
- snapshot artefacts (M6.7) contain no memory values

---

## 7. Memory Write Contract (M6.6)

### 7.1 Write properties

- All writes require explicit user confirmation — the write path is a CLI subcommand
  (`memory write`), not an automatic or runtime-initiated operation
- Writes are atomic: single record, single operation
- The write path is separate from the execution path — no writes may occur during a run
- A successful write produces a stable record identifier (`<scope>/<key>`) for subsequent
  retrieval

### 7.2 Write CLI surface

```text
python -m io_iii memory write --scope <scope> --key <key> --value <value>
    [--sensitivity standard|elevated|restricted]
    [--provenance human|llm:<slug>|mixed]
```

User confirmation is required before the write is committed. The confirmation prompt
displays the key, scope, and sensitivity tier — never the value.

### 7.3 Failure contract

Write failures raise a `RuntimeFailure` under ADR-013:

| Field | Value |
| --- | --- |
| `kind` | `contract_violation` |
| `code` | `MEMORY_WRITE_FAILED` |
| `retryable` | `False` |
| `summary` | key, scope, and error reason — no value content |

### 7.4 Content safety

No memory value is logged on write. The write log records key, scope, sensitivity tier,
and confirmation status only.

---

## 8. SessionState Snapshot Export (M6.7)

### 8.1 Purpose

The snapshot export provides a portable, self-describing artefact that carries workflow
position and memory pack state. It enables cross-machine session continuity without
requiring a shared file system. It is the portability primitive required by Phase 8
M8.3 (`session continue`).

### 8.2 Export properties

- Export is user-initiated via CLI subcommand (`session export`) — no automatic or
  runtime-triggered exports
- Export is a single JSON file; default path is `<storage_root>/<run_id>.snapshot.json`;
  path is user-overridable via `--output`

### 8.3 Artefact schema

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `str` | semantic version; current: `"1.0"` |
| `run_id` | `str` | UUIDv4; the run this snapshot captures |
| `workflow_position` | `int` | index of the last completed runbook step (0-indexed) |
| `active_memory_pack_ids` | `list[str]` | pack ids active at export time |
| `governance_mode` | `str` | governance mode at export time |
| `exported_at` | `str` | ISO 8601 timestamp |

The artefact never contains memory values, model output, or prompt content.

### 8.4 Import contract

- Import validates `schema_version` and all required fields before restoring state
- An import that fails schema validation raises a `RuntimeFailure`:

| Field | Value |
| --- | --- |
| `kind` | `contract_violation` |
| `code` | `SNAPSHOT_SCHEMA_INVALID` |
| `retryable` | `False` |
| `summary` | field name and reason — no artefact content |

### 8.5 CLI surface

```text
python -m io_iii session export [--output <path>]
python -m io_iii session import --snapshot <path>
```

### 8.6 Cross-phase dependency

This milestone is a prerequisite for Phase 8 M8.3 (session shell `continue` command).
The session shell requires a portable session object to resume from. No Phase 8 M8.3
code may be written until M6.7 is implemented and tested.

---

## 9. New Failure Codes

This ADR extends the ADR-013 failure taxonomy with the following new codes under the
`contract_violation` kind:

| Code | Milestone | Condition |
| --- | --- | --- |
| `MEMORY_WRITE_FAILED` | M6.6 | Memory write operation failed (store error, permission, or conflict) |
| `SNAPSHOT_SCHEMA_INVALID` | M6.7 | Snapshot artefact fails schema validation on import |

Both codes are `retryable = False`. Both are content-safe: no memory value, model
output, or prompt content appears in any failure field.

---

## 10. Explicit Non-Goals

### Not in scope for this ADR

- Python implementation of M6.1–M6.7
- Tests
- Retrieval systems (embedding-based search or ranking)
- Open-ended memory search
- Cross-session memory without an explicit scope contract
- Autonomous memory writes
- Memory systems that alter routing or step execution order
- Output-driven or telemetry-driven routing
- Dynamic context selection

### Out of scope permanently for Phase 6

- Phase 7 portability layer (init contract, init command, templates)
- Phase 7 M7.5 Work Mode / Steward Mode ADR
- Phase 8 session shell
- Any modification to ADR-002, ADR-008, ADR-009, ADR-010, ADR-014, or ADR-020

---

## 11. Scope Boundary

This ADR covers:

- the Phase 6 governance freeze boundary and permissible surfaces (§1)
- the memory store architecture: record structure, store properties, storage root (§2)
- the memory pack system: pack definition, properties, example (§3)
- the memory retrieval policy: default stance, allowlist rules, policy absence (§4)
- memory injection via context assembly: pipeline, contract, extension, content safety (§5)
- memory safety invariants: allowed and forbidden log fields, validator integration (§6)
- the memory write contract: properties, CLI surface, failure contract, content safety (§7)
- the SessionState snapshot export: purpose, artefact schema, import contract, CLI
  surface, cross-phase dependency (§8)
- new failure codes extending ADR-013 (§9)

This ADR does **not** cover:

- implementation of any milestone
- Phase 7 or Phase 8 contracts
- any modification to the frozen execution stack

---

## 12. Relationship to Other ADRs

- **ADR-003** — content safety. All memory log fields, failure summaries, and snapshot
  artefacts must comply in full. Memory values are forbidden in every log surface.
- **ADR-007** — memory persistence and drift control. ADR-007 establishes the governance
  principles for what IO-III may persist and the provenance labelling requirement.
  ADR-022 implements those principles as a concrete memory architecture. ADR-007 is not
  superseded — it remains the governing provenance and drift-control policy.
- **ADR-009** — audit gate contract. Frozen. Memory injection does not affect audit gate
  behaviour or bounded pass counts.
- **ADR-010** — context assembly layer. Extended by M6.4 to include a `### Memory`
  section. The assembly contract is not otherwise modified.
- **ADR-013** — failure semantics. Extended by §9 with two new `contract_violation`
  codes. All existing failure contracts unchanged.
- **ADR-014** — bounded runbook layer contract. Frozen. Memory injection runs
  identically inside and outside runbook steps.
- **ADR-020** — replay/resume execution contract. Frozen. Memory injection applies
  identically to first-run, replay, and resume executions.
- **ADR-021** — runtime observability contract. M5.1 pre-flight estimator is consumed
  by M6.4 as the token budget mechanism. ADR-021 is not modified.

---

## 13. Consequences

### Positive

- Curated, scoped context can be injected into execution without retrieval autonomy or
  dynamic routing — determinism is preserved.
- The M5.1 token budget ensures memory injection cannot silently overflow the context
  window.
- The retrieval policy's opt-in stance means an unconfigured route receives no memory
  context — the safe default requires no action.
- The write path's user-confirmation requirement and execution-path separation prevent
  any autonomous memory modification.
- The snapshot export artefact (M6.7) is content-safe by construction and provides a
  portable, machine-readable primitive for Phase 8 session continuity.

### Negative

- Memory pack declaration adds a config maintenance surface. Pack authors must keep
  declared keys in sync with the store.
- The bounded subset drop-on-overflow behaviour (M6.4) means large packs on
  context-constrained routes will silently drop records. Pack authors should declare
  packs sized for the target route's budget.
- The write CLI path requires an interactive confirmation step, which is not compatible
  with non-interactive pipeline use. This is intentional — unconfirmed writes are not
  permitted.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III introduces a governed memory architecture under Phase 6. Memory records are
atomic, scoped, and deterministically retrieved by key — never by search or embedding.
Named memory packs bundle curated record sets declared in config. A retrieval policy
gated by route and capability allowlists controls access; no record is accessible by
default. Bounded memory injection via the context assembly layer (ADR-010) uses the
M5.1 token budget to constrain subset size. Memory values are forbidden in all log
fields at every lifecycle stage. The write path requires explicit user confirmation and
is separated from the execution path. A governed snapshot export artefact carries
session position and active pack state as a portable, content-safe JSON file — the
prerequisite for Phase 8 M8.3. Two new failure codes (`MEMORY_WRITE_FAILED`,
`SNAPSHOT_SCHEMA_INVALID`) extend the ADR-013 taxonomy. The frozen Phase 1–5 execution
stack is not modified.