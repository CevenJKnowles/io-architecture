---
id: ADR-033
title: Context Assembly Extension — File Input Lane
type: adr
status: accepted
version: v1.1
canonical: true
scope: io-iii-phase-10
audience:
  - developer
  - maintainer
  - operator
created: "2026-05-01"
updated: "2026-05-01"
tags:
  - io-iii
  - adr
  - phase-10
  - context-assembly
  - file-upload
  - content-safety
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-033 — Context Assembly Extension — File Input Lane

## Status

Accepted

---

## 1. Context

ADR-010 defines the context assembly contract: the structured process by which the
execution engine assembles a prompt from the session state, memory packs, and direct
user input before each provider call. The input lanes defined in ADR-010 are:

1. Persona contract (system-level framing)
2. Memory pack content (bounded records from ADR-022)
3. Direct prompt text (user input)

ADR-029 introduces server-side file upload. File-derived content must enter context
assembly in a governed, bounded, and content-safe manner. It cannot be injected as
raw text appended to the prompt string without a formal contract, as doing so would
bypass the token budget enforcement, content safety invariants, and execution bounds
established in ADR-010 and ADR-009.

This ADR formally amends ADR-010 to introduce a fourth input lane: file-derived content.

---

## 2. Decision

### §1 New input lane — file content

A fourth input lane is added to context assembly: **file content**. This lane is
populated when a `file_ref` is present in the execution context, resolved to the
extracted text of the uploaded file at context assembly time.

The assembly order is:

1. Persona contract
2. Memory pack content
3. File content (this ADR)
4. Direct prompt text

File content is injected between memory pack content and the direct prompt text.
This ordering ensures the model receives background context (memory packs), then
document context (file), then the user's specific question or instruction (prompt).

### §2 Token budget

File content has its own token budget, separate from the memory pack budget. The
budget is configurable via a new `file_content_limit_chars` sub-key in `runtime.yaml`.
If absent, the file content budget defaults to 50% of the total `context_limit_chars`
ceiling.

If extracted file content exceeds the budget, it is truncated at a sentence or
paragraph boundary with a structural notice appended:
`[File content truncated at context limit — {n} characters shown of {total}]`

Truncation is logged as a metadata event with `file_truncated: true`. No file
content appears in the log field.

### §3 Content safety invariant — INV-006

A new invariant is introduced:

**INV-006: File content safety**

File-derived text must never appear in any log field, metadata record, or
`ExecutionResult.meta` payload. This invariant is enforced by extending
`assert_no_forbidden_keys` in `core/content_safety.py` to treat file-derived
content identically to prompt text.

The `file_ref` identifier (a UUID) may appear in metadata. The resolved file
content may not.

### §4 Execution context extension

`ExecutionContext` is extended with an optional `file_ref: str | None` field.
When present, context assembly resolves the `file_ref` to extracted text via the
session file store and injects it per §1. When absent, context assembly proceeds
as defined in ADR-010 without modification.

### §5 File store interface

A minimal file store is introduced at `io_iii/core/file_store.py`:

- `store(session_id, content, filename) -> file_ref` — stores extracted text,
  returns a UUID `file_ref`
- `resolve(session_id, file_ref) -> str` — retrieves stored text; raises
  `FileRefNotFound` if the `file_ref` is absent (see §7)
- `delete(session_id)` — deletes all files associated with a session

Storage is in-memory for Phase 10 (dict-backed). No persistence to disk is
introduced. This is an intentional scope constraint; see §7 for consequences
and required handling.

### §6 Session cleanup — explicit call sites

`DialogueSession` (`core/dialogue_session.py`, Phase 8) does not expose an
internal close hook or finaliser. The `SESSION_STATUS_CLOSED` value exists as
a status string and can be set on the `DialogueSession` dataclass, but no
`close_session()` function is defined in that module. File store cleanup cannot
be wired to a non-existent hook.

`file_store.delete(session_id)` must therefore be called explicitly at two
surfaces:

**CLI:** `cli/_session_shell.py:cmd_session_close()` — invoked when the user
runs `python -m io_iii session close`. After setting session status to
`SESSION_STATUS_CLOSED` and calling `save_session()`, `cmd_session_close` must
call `file_store.delete(session_id)`.

**HTTP API:** `api/_handlers.py` handler for `DELETE /session/{id}` — after
removing the session from the active session registry, the handler must call
`file_store.delete(session_id)`.

Both call sites own their cleanup. If a session reaches `at_limit` status or
is abandoned without an explicit close, the in-memory store retains the file
content until server restart. This is acceptable for Phase 10 scope.

### §7 Server restart coherence

`save_session()` persists session metadata to disk and `load_session()` can
reload a session across server restarts (Phase 8 contract). The in-memory file
store does not survive a restart. A reloaded session may therefore carry a
`file_ref` that no longer resolves.

This coherence gap is handled as follows: when context assembly calls
`file_store.resolve()` and the `file_ref` is absent, context assembly raises a
structured failure with code `FILE_REF_EXPIRED` rather than a generic exception.
The CLI and API surfaces catch this failure and surface a plain-language message:

```
File reference expired — the server was restarted since this file was uploaded.
Please re-upload the file to continue.
```

This event is logged with `error_code: FILE_REF_EXPIRED`. No file content
appears in any log field. The failure is treated as a recoverable user error
(exit code 1 at the CLI surface) and does not terminate the session.

### §8 Engine boundary

`engine.py` is not modified. `ExecutionContext` construction at the CLI and API
boundary layers is extended to include `file_ref` when present in the request.
Context assembly (`context_assembly.py`) is the only module that reads and
resolves the `file_ref`. The provider layer, routing layer, and telemetry layer
are unaffected.

### §9 Invariant contract

The following existing invariants are explicitly extended to cover file content:

- ADR-003: file-derived content is treated as prompt-equivalent for all logging
  purposes
- ADR-009 bounded execution: file content injection is single-pass, single-input,
  no iteration
- ADR-010 context assembly: this ADR is an amendment; the ADR-010 contract remains
  authoritative for the persona, memory, and prompt lanes

---

## 3. Consequences

- `context_assembly.py` gains a file content resolution path with `FILE_REF_EXPIRED`
  failure handling.
- `ExecutionContext` gains an optional `file_ref: str | None` field.
- `core/content_safety.py` is extended to enforce INV-006.
- `core/file_store.py` is introduced as a new module.
- `cli/_session_shell.py:cmd_session_close()` is extended to call
  `file_store.delete(session_id)`.
- `api/_handlers.py` DELETE handler is extended to call
  `file_store.delete(session_id)`.
- A new invariant (INV-006) is added to the invariant test suite.
- A new failure code (`FILE_REF_EXPIRED`) is added to the failure model.
- `engine.py`, `routing.py`, and `telemetry.py` are not modified.

---

## 4. Relationship to future ADRs

When Phase 11 implements RAG (ADR-031), a fifth input lane will be added via a
new ADR amending both ADR-010 and this record. File content (session-scoped,
user-uploaded) and retrieval content (corpus-indexed, cross-session) are distinct
lanes with separate contracts.

If Phase 11 introduces persistent file storage, an amendment to this ADR is
required, as §5 and §7 would no longer hold.

---

## 5. Non-goals

- This ADR does not introduce persistent file storage.
- This ADR does not implement OCR or binary format parsing.
- This ADR does not introduce a retrieval or embedding layer.
- This ADR does not modify `engine.py`, `routing.py`, or `telemetry.py`.
- This ADR does not change the persona, memory pack, or direct prompt lanes
  as defined in ADR-010.
- This ADR does not add an internal close hook to `DialogueSession`.