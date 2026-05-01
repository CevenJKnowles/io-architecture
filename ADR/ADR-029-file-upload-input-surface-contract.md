---
id: ADR-029
title: File Upload Input Surface Contract
type: adr
status: accepted
version: v1.0
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
  - api
  - file-upload
  - context-assembly
  - content-safety
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-029 — File Upload Input Surface Contract

## Status

Accepted

---

## 1. Context

The Phase 9 web UI (`api/static/index.html`) provides a text prompt input only. Users
who wish to provide document content to the runtime must paste text manually, which is
impractical for any file of meaningful length and impossible for binary formats such as
PDF and DOCX.

Two implementation approaches were evaluated:

**Option A — Client-side injection.** The browser reads the file via the FileReader API
and appends its text content to the prompt string before the HTTP request is sent. No
new API endpoint. No server involvement. Supported types limited to plain text formats.
PDF and DOCX are not supported.

**Option B — Server-side pipeline.** A new `POST /upload` endpoint accepts multipart
form data. The server extracts text content, stores it session-scoped, and assigns a
`file_ref` identifier. The `file_ref` is injected into context assembly as a bounded
input lane. Supports PDF (text-based) and DOCX via extraction libraries.

Option A was rejected as insufficient. PDF and DOCX are the dominant document formats
in professional and enterprise contexts. A file upload feature that excludes them
provides materially less value and does not justify the implementation cost relative
to what it enables. Option B is adopted for Phase 10.

---

## 2. Decision

### §1 The server-side pipeline

Phase 10 implements Option B. A `POST /upload` endpoint is added to the Phase 9 API
layer. The endpoint accepts multipart form data, extracts text content from the
uploaded file, stores it session-scoped, and returns a `file_ref` identifier to the
client.

The endpoint is a transport adapter only, consistent with ADR-025. It does not introduce
new execution semantics. All Phase 1–9 invariants are preserved.

### §2 Supported file types

Phase 10 supports the following file types:

| Type | Extension | Extraction method |
| --- | --- | --- |
| Plain text | `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.py` | Direct read, UTF-8 |
| PDF | `.pdf` | `pypdf` text extraction |
| Word document | `.docx` | `python-docx` text extraction |

Files of any other type are rejected with a structured error response:
`{"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "..."}}`.

Binary PDFs where text extraction yields no content (image-only / scanned documents)
are rejected with `{"error": {"code": "FILE_NO_EXTRACTABLE_TEXT", "message": "..."}}`.
OCR is explicitly out of scope for Phase 10 and Phase 11.

### §3 File size and retention

Maximum file size: 2MB. Files exceeding this limit are rejected with
`{"error": {"code": "FILE_TOO_LARGE", "message": "..."}}`.

Storage is session-scoped. Files are deleted when the session closes or expires.
No file content is persisted across sessions. No persistent file store is introduced.

### §4 Content safety

File-derived content is subject to the same content safety invariants that govern
prompt text and memory values (ADR-003, ADR-022):

- File-derived text never appears in any log field or metadata record.
- File content is not surfaced in API responses except as part of the model response
  (governed by ADR-026 `content_release` gate).
- File content is not stored beyond the session boundary.

This invariant is enforced structurally in the context assembly layer per ADR-033.

### §5 Context assembly injection

File content enters the execution pipeline exclusively through context assembly. The
`file_ref` is resolved at context assembly time, and the extracted text is injected as
a bounded input lane with its own token budget. The contract for this lane is defined
in ADR-033.

### §6 Dependencies introduced

Two new dependencies are added to `pyproject.toml`:

- `pypdf>=4.0` — PDF text extraction
- `python-docx>=1.0` — DOCX text extraction

These are production dependencies, not development-only. Both are pure Python and
introduce no OS-level binary requirements.

### §7 Web UI

The Phase 9 web UI is extended with a file attachment control adjacent to the prompt
input. The UI displays the attached filename with a dismiss control. On submit the
`file_ref` is included in the request payload alongside the prompt text. The client-side
Option A path (FileReader injection) is not implemented; the server-side path is the
only upload mechanism.

### §8 Phase 11 path

Phase 11 may extend this contract to support:

- Persistent file storage across sessions
- Larger file size limits
- Additional binary formats
- OCR for scanned PDF content

Any such extension requires a new ADR amending this record.

---

## 3. Consequences

- Two new production dependencies (`pypdf`, `python-docx`) are introduced.
- A new `POST /upload` endpoint is added to the API layer.
- Context assembly is extended per ADR-033 to accept a file input lane.
- A new content safety invariant (INV-006) is introduced covering file-derived content.
- `engine.py`, `routing.py`, and `telemetry.py` are not modified.

---

## 4. Non-goals

- This ADR does not implement OCR for scanned or image-based PDFs.
- This ADR does not introduce persistent file storage.
- This ADR does not support formats beyond those listed in §2.
- This ADR does not modify the execution engine, routing layer, or telemetry.
- This ADR does not introduce client-side Option A as a fallback or alternative path.