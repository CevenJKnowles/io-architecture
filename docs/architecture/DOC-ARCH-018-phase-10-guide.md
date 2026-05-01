---
id: DOC-ARCH-018
title: Phase 10 Guide | Public Release Preparation and Surface Extension
type: architecture
status: draft
version: v0.1
canonical: true
scope: phase-10
audience:
  - developer
  - maintainer
  - operator
created: "2026-05-01"
updated: "2026-05-01"
tags:
  - phase-10
  - architecture
  - release
  - documentation
  - ux
  - docker
  - openai-compat
provenance: io-iii-runtime-development
---

# Phase 10 Guide | Public Release Preparation and Surface Extension

---

## Purpose

Phase 10 prepares the IO-III runtime for public open-source release and extends its
surface in three directions: container deployment, file input, and OpenAI transport
compatibility.

It has two structurally distinct work streams that must be understood separately:

**Stream A — Release Hardening.** Everything required before the repository becomes
public. This includes repo hygiene, project identity (rename + logo), new-user
error resilience, and the complete public documentation layer. No new execution
semantics. No new API surface. Phases 1–9 invariants preserved in full.

**Stream B — Surface Extension.** Three new capabilities that extend the project's
reach: container deployment, file upload input, and an OpenAI-compatible transport
endpoint. Each requires an accepted ADR before implementation begins.

Stream A must be complete before any public announcement. Stream B milestones may
follow after tagging `v1.0.0`, but their ADRs must be written and accepted during M10.0.

---

## Phase Prerequisite

Phase 10 depends on Phase 9 being complete and tagged `v0.9.0`.

Additionally, three non-ADR decisions must be confirmed before M10.0 can close:

- **New project name** — confirmed and final. Blocks M10.1 and all documentation.
- **Licence** — selected and final (recommended: MIT or Apache 2.0). A public repo
  without a licence is functionally all-rights-reserved.
- **File upload approach** — client-side injection or server-side pipeline (see ADR-029).
  This decision gates M10.5 entirely. If undecided, M10.5 ships as client-side only.

---

## Invariants That Must Remain True

All Phase 1–9 invariants are preserved throughout Phase 10 without exception.
Stream B additions are transport adapter extensions only — they do not modify
`engine.py`, `routing.py`, or `telemetry.py`.

Specifically:

- deterministic routing (ADR-002)
- bounded execution: max 1 audit pass, max 1 revision pass (ADR-009)
- content-safe output in all API surfaces (ADR-003, ADR-025, ADR-026)
- no autonomous behaviour, no dynamic routing, no recursive execution
- ADR-first development for all structural additions
- `engine.py`, `routing.py`, `telemetry.py` unchanged throughout Phase 10

---

## What Phase 10 May Add

**Stream A (hardening — no architectural change):**
- project rename, logo, updated identity throughout all files
- repo hygiene: removed internal artefacts, corrected `.gitignore`, clean history
- new-user error resilience: caught `ProviderError` 404, plain-language routing hint
- cloud provider resolution: stubs or removal per ADR-028
- public documentation layer: README restructure, user guide, examples directory,
  anatomical guide, CHANGELOG, CONTRIBUTING update

**Stream B (new surface — ADR-gated):**
- container deployment surface (Dockerfile + docker-compose, per ADR-032)
- file upload input surface (per ADR-029)
- OpenAI-compatible transport endpoint (per ADR-030, may be Phase 11)

---

## ADR Manifest for Phase 10

Six ADRs must be written and accepted before any implementation begins. They are
ordered by dependency, not alphabetically. ADRs that gate Stream B milestones are
noted.

Writing all six during M10.0 has two benefits: it surfaces ambiguities before they
become implementation problems, and it ensures Stream B milestones can begin
immediately after M10.1 closes without waiting for additional governance cycles.

---

### ADR-027 — Project Identity and Rename Contract

**When:** M10.0. Must be accepted before any file in the repo is modified.

**Scope:** Records the new project name, the scope of the rename (all files, package
directory, CLI entry point, pyproject.toml, all ADR and DOC headers, GitHub repo
URL), and what does not change (execution semantics, all ADR governance contracts,
all invariants). Establishes the rename as a structural identity migration, not an
architectural change.

**Key decisions this ADR must record:**
- What is the new name?
- Does the Python package name change (e.g. `io_iii` → `[new_name]`)? If so, all
  import statements change.
- Does the CLI entry point change (`python -m io_iii` → `python -m [new_name]`)?
- What happens to the GitHub repo URL — rename in place, or new repo?

**Blocks:** M10.1 entirely. No file in the repo should be renamed, modified for
identity reasons, or documented under a new name until this ADR is accepted.

---

### ADR-028 — Provider Adapter Completion and Cloud Opt-In Contract

**When:** M10.0. Must be accepted before M10.2.

**Scope:** Resolves the current ambiguity in `providers.yaml`, which lists OpenAI,
Anthropic, and Google as disabled entries with no corresponding adapter implementations.
A public user setting `enabled: true` and supplying an API key will find no code
behind the entry. This is a trust-damaging first impression.

**Decision options — choose one:**

*Option A — Implement stub adapters.* Add `openai_provider.py`,
`anthropic_provider.py` under `io_iii/providers/`. Each raises
`NotImplementedError("Cloud provider adapters are not yet implemented — see Phase 11
roadmap.")` with a link to the roadmap. The entries remain in `providers.yaml` with
a `status: stub` field. Users get a clear, honest error rather than silent failure.

*Option B — Remove cloud entries.* Delete OpenAI, Anthropic, and Google entries from
`providers.yaml` for this release. Add a `# Cloud providers: not yet available —
see ROADMAP.md` comment in their place. Simpler, but removes the signal that cloud
support is planned.

*Option C — Implement a real OpenAI adapter.* Deliver a working
`openai_provider.py` in Phase 10. Higher effort, high adoption value. Only viable
if the team has capacity.

ADR-004 remains governing policy (cloud off by default). ADR-028 records only the
resolution of the current stub gap.

**Blocks:** M10.2 cloud provider resolution task.

---

### ADR-029 — File Upload Input Surface Contract

**When:** M10.0. Must be accepted before M10.5.

**Scope:** Defines how file content enters the runtime when a user uploads a file
in the web UI.

**Decision options — choose one:**

*Option A — Client-side injection.* The browser reads the file and appends its text
content to the prompt string before the HTTP request is sent. No new API endpoint.
No new context assembly path. Content enters via the existing `POST /run` or session
turn endpoint as part of the prompt. Simplest path; ships with M10.5 as a UI-only
change. Limitation: no structured treatment of the file — it is concatenated text.

*Option B — Server-side pipeline.* A new `POST /upload` endpoint accepts multipart
form data. The server stores the content, assigns it a `file_ref` identifier, and
injects it into context assembly as a bounded input before the engine call. Requires
a new ADR for the context assembly injection contract (extending ADR-010). Structured
and auditable. Significantly more implementation work.

**Key constraint regardless of option:** file content must never appear in log fields
or metadata records. ADR-003 applies to file-derived content as it does to prompts
and completions.

**Recommended for Phase 10:** Option A. Option B is the architecturally correct
long-term path and should be scoped as M11.x, with ADR-029 explicitly naming it as
the Phase 11 extension.

**Blocks:** M10.5 entirely.

---

### ADR-030 — OpenAI-Compatible Transport Endpoint

**When:** M10.0. Must be accepted before M10.6 (or before Phase 11 planning begins
if scoped out).

**Scope:** Defines the scope, contract, and constraints of a `/v1/chat/completions`
endpoint that mimics the OpenAI Chat Completions API shape. This would allow users
to point any OpenAI SDK client at the IO-III server without changing application code.

**The architectural constraint:** this is a transport adapter only, following the
same rule as ADR-025. The `/v1/chat/completions` endpoint maps the incoming OpenAI
request shape to the existing session/engine layer. It does not introduce new
execution semantics. It does not bypass governance.

**What the ADR must decide:**
- Is this in scope for Phase 10 or Phase 11? (Recommendation: Phase 11, but the ADR
  is written now so the decision is recorded and Phase 10 does not accidentally
  constrain the implementation surface.)
- Which OpenAI fields are supported? At minimum: `model`, `messages`, `stream`.
  Unsupported fields should return a structured error, not be silently ignored.
- How does `model` in the OpenAI request map to the IO-III routing table? The
  routing table uses modes (`executor`, `explorer`, etc.), not model names. The ADR
  must define the mapping contract.
- Content-safety: `content_release: true` must be set for the endpoint to surface
  model output. The ADR should require this to be explicitly confirmed by the operator.

**Blocks:** M10.6. If scoped to Phase 11, M10.6 is dropped from Phase 10.

---

### ADR-031 — Knowledge Extension and RAG Architecture Boundary

**When:** M10.0.

**Scope:** Formally establishes what the current memory pack system can and cannot do
for knowledge extension, and defines the boundary conditions for a retrieval-augmented
generation (RAG) integration in a future phase.

This ADR does not implement RAG. It exists to give users a clear, honest answer to
"how do I add recent or domain-specific knowledge?" — and to prevent ad-hoc
workarounds from creating technical debt that a future RAG implementation must undo.

**What the ADR must record:**
- Memory packs support bounded, curated knowledge injection via context assembly.
  They are the correct current-phase answer for structured, manually maintained
  domain facts.
- Large-corpus retrieval (embedding-based similarity search, vector databases,
  document chunking) is out of scope for Phase 10. It requires a new retrieval
  adapter interface, a new context assembly input path, and new invariant contracts.
- Phase 11+ will introduce a governed retrieval adapter contract. The memory pack
  system will remain the primary injection mechanism; retrieval will be an additional
  input lane, not a replacement.
- The ADR should reference ADR-022 (memory architecture) and ADR-010 (context
  assembly) as the governing contracts this extension must not violate.

**Blocks:** Nothing in Phase 10 directly. Its value is to produce a definitive
documented answer for user-facing documentation and to prevent scope creep.

---

### ADR-032 — Container Deployment Surface Contract

**When:** M10.0. Must be accepted before M10.4.

**Scope:** Defines what the Docker container is and is not. Specifically: the
container is a packaging surface only. It runs the existing HTTP server (Phase 9)
inside an isolated environment. It does not introduce new execution semantics,
new API endpoints, or new governance rules.

**What the ADR must record:**
- The container exposes the existing Phase 9 HTTP API on a configurable port.
- `architecture/runtime/config/` is a volume mount, not baked into the image.
  This ensures users can edit `routing_table.yaml` and `providers.yaml` without
  rebuilding the image.
- `OLLAMA_HOST` is an environment variable. Users running Ollama on the host (not
  in Docker) set this to their host IP. Users running Ollama as a docker-compose
  sidecar use the service name.
- GPU passthrough for Ollama is the user's responsibility and is out of scope for
  this ADR.
- All Phase 1–9 invariants apply inside the container. The container boundary does
  not relax any governance rule.

**Blocks:** M10.4.

---

## Milestone Plan

### M10.0 — Governance Pre-flight

**Description:** Write and accept all six Phase 10 ADRs. Confirm the three non-ADR
decisions (new name, licence, file upload approach). No implementation begins until
this milestone closes.

**Deliverables:**
- ADR-027 through ADR-032 accepted and indexed in `ADR/README.md`
- New project name confirmed in writing
- Licence selected (MIT or Apache 2.0 recommended)
- File upload approach confirmed (Option A or B per ADR-029)
- OpenAI proxy phase assignment confirmed (Phase 10 or Phase 11)
- `DOC-ARCH-018` (this document) updated to reflect confirmed decisions

**Estimated scope:** 1–2 working days. Most time is thinking time, not writing time.

**Invariant check:** Not applicable — no code is written in this milestone.

**Closes when:** All six ADRs accepted. All three decisions confirmed in writing.

---

### M10.1 — Structural Identity

**Description:** Apply the confirmed new name mechanically throughout the entire
repo. Add logo. Remove all internal artefacts. This is a single coordinated pass —
not six separate commits.

**Consolidation note:** Every identity change in the repo happens in this milestone
and nowhere else. Any documentation that references the name (README, user guide,
ADR headers) must not be written before this milestone closes.

**Deliverables:**
- Package directory renamed from `io_iii/` to `[new_package_name]/`
- All import statements updated throughout `io_iii/` and `tests/`
- `pyproject.toml`: `name`, `version` (bump to `1.0.0-rc.1`), description updated
- CLI entry point updated if it changes
- All 26 ADR headers: `scope` field updated to drop `io-iii-` prefix or substitute
  new name as appropriate
- All DOC-* file headers updated
- `README.md` title and all in-file references updated
- `ARCHITECTURE.md` YAML frontmatter cleaned: `audience: portfolio` removed,
  `status` updated
- Logo file added to repo root (e.g. `logo.png` or `logo.svg`)
- Logo referenced in `README.md` header
- `SESSION_STATE.md` removed from repo root (moved to `history/` or deleted)
- `.directory` (KDE artefact) removed
- `.gitignore` verified to cover: `**/__pycache__`, `**/*.pyc`, `**/.pytest_cache`,
  `.venv`, `*.egg-info`
- `__pycache__` directories and `.pytest_cache` directories removed from git history
  if previously committed
- `history/` directory either given a `README.md` explaining it is archived
  development history, or removed from the public repo
- `docs/overview/DOC-OVW-006` and `DOC-OVW-007` (internal session snapshots)
  moved to `history/` or deleted

**Invariant check:** Run `pytest` and `validate_invariants.py` after the rename.
All 1008+ tests must pass. If tests reference the old package name directly in
import statements, update them as part of this milestone.

**Closes when:** `pytest` passes, `validate_invariants.py` passes, no file in
the repo contains the old project name except inside `history/`.

---

### M10.2 — New-User Resilience

**Description:** Fix the first-run experience for a user who does not have the
developer's exact Ollama model setup. Resolve the cloud provider ambiguity per
ADR-028. This milestone is Stream A hardening — no new features.

**Consolidation note:** All three tasks here (error handling, routing table
comments, cloud provider resolution) are the same user-facing concern: "what
happens when a new user clones this and it doesn't work?" They are implemented
together.

**Deliverables:**

*Error handling (CLI boundary):*
- Catch `ProviderError` at the `cmd_run` CLI boundary (in `cli/__init__.py`),
  not just `RuntimeError` for `PROVIDER_UNAVAILABLE`
- If the error message contains `404`, emit a plain-language error to stdout:
  ```
  Model not found in your Ollama instance.
  Run 'ollama list' to see available models, then update routing_table.yaml.
  Config path: [resolved config dir]/routing_table.yaml
  ```
- Exit with code 1 (existing convention)
- Log `error_code: PROVIDER_MODEL_NOT_FOUND` to metadata (content-safe)
- Test: `tests/test_provider_error_ux.py` — asserts the hint appears and exit
  code is 1 when a 404 ProviderError is raised

*Routing table documentation:*
- Add a comment block to `routing_table.yaml` immediately before the `models:`
  section:
  ```yaml
  # --- MODEL CONFIGURATION ---
  # Edit the model names below to match what you have installed locally.
  # To see which models are available: run 'ollama list' in your terminal.
  # Each role maps to a model name as shown in 'ollama list' output.
  # Minimum setup: you can point all roles at the same model.
  # Example: name: "llama3.2:latest"
  ```

*Cloud provider resolution (per ADR-028):*
- Implement whichever option ADR-028 selected (stub adapters, removal, or real
  adapter)
- If stub adapters: add `openai_provider.py` and `anthropic_provider.py` under
  `providers/`, each raising `NotImplementedError` with a clear message
- If removal: delete cloud entries from `providers.yaml`, add roadmap comment
- Update `CONTRIBUTING.md` to reflect the cloud provider status accurately

**Invariant check:** `pytest` passes. `validate_invariants.py` passes. No new
content appears in log fields.

**Closes when:** A user who clones the repo with no matching Ollama models sees
a plain-language error pointing to the routing table. Cloud provider ambiguity
is resolved per ADR-028.

---

### M10.3 — Public Documentation Layer

**Description:** Write the complete public-facing documentation layer. This is the
largest single milestone in Phase 10 by word count, but it is scoped to documentation
only — no code changes, with the exception of the examples directory.

**Consolidation note:** The README restructure, user guide, models doc, why doc,
examples directory, CHANGELOG, anatomical guide, and CONTRIBUTING update are all
written in this milestone as a single documentation pass. Writing them across
separate milestones would require the same conceptual context to be re-established
multiple times and would produce inconsistent voice. The examples directory is
included here — not in a separate milestone — because the process of writing a
self-contained working example is the most reliable way to discover gaps in the
getting started guide.

**Deliverables:**

*README restructure (`README.md`):*
- First screen (no scroll required) contains: project name + logo, one paragraph
  for the non-technical reader, one paragraph for the architect/engineer, and a
  "Quick Links" list pointing to Getting Started, Why [Name], Architecture, and
  Contributing.
- The "What This Is" section updated to lead with the human problem (what breaks
  without this) before the technical description.
- A "Why [Name] and not X?" section comparing: direct model calls, LangChain /
  LlamaIndex, OpenAI Assistants. One or two sentences per comparison. The answer
  in each case is the same: those systems are permissive by default; this one is
  restrictive by default.
- Mermaid architecture diagrams retained — they are communicative and should stay.
- The full milestone history section (currently ~200 lines) moved to `CHANGELOG.md`.
- The module reference table moved to `docs/architecture/` and linked from README.
- Quick start section trimmed to: install, first run, one working example command.
  The full getting started guide lives in `docs/user-guide/`.
- Target: README under 150 lines after restructure.

*`CHANGELOG.md` (new file):*
- Contains the Phase 1–9 milestone history extracted from the current README.
- Follows Keep a Changelog format (https://keepachangelog.com).
- Linked from README.

*`docs/user-guide/GETTING_STARTED.md` (new file):*
- What you need: Python 3.11+, Ollama, at least one model pulled.
- Installation: git clone, venv, pip install.
- First run: exact command, expected output, what it means.
- How to configure your models: open routing_table.yaml, run `ollama list`,
  match the names. One concrete example.
- What the modes mean: one sentence per mode (executor, explorer, challenger,
  synthesizer, visionary, fast, draft).
- How to run the web UI: exact command, what to expect.
- How to read an error: the two most common errors (Ollama not running, model
  not found) with exact error text and exact fix.
- Links to MODELS.md for advanced model configuration.

*`docs/user-guide/MODELS.md` (new file):*
- Tested model configurations with known-good combinations by hardware tier
  (low-spec: 8B models only; mid-spec: 14B reasoning; high-spec: full setup).
- How to add a new model: edit routing_table.yaml, the three fields to change,
  how to verify the route resolves (`python -m [name] route executor`).
- Notes on minimum VRAM requirements per model tier.
- Note on the null provider (for testing without Ollama).

*`docs/user-guide/WHY-[NAME].md` (new file):*
- The "why not just call the model directly?" answer in plain language.
- Concrete comparison: a direct Ollama call (10 lines of Python, no governance)
  versus an IO-III call (same result, plus deterministic routing, audit trail,
  content-safe logs, bounded execution). What you gain in the second case.
- One concrete example of what the system prevents: a model call that exceeds the
  token budget gets blocked before it reaches the provider; a direct call would not.
- Addressed to a reader who knows what an API is but not what a control plane is.

*`docs/architecture/` updates:*
- `DOC-ARCH-001` through `DOC-ARCH-007` reviewed for accuracy against v0.9.0.
  Any phase guide that references "planned" work for phases now complete should
  be updated to `status: complete`.
- Module reference table moved here as `DOC-ARCH-018-module-reference.md`
  (or renumbered appropriately — note this guide is DOC-ARCH-018, so the
  module reference should be DOC-ARCH-019 or placed within an existing doc).
- `DOC-ARCH-003` (master roadmap) updated to reflect Phase 10 scope and a
  Phase 11 placeholder.

*`CONTRIBUTING.md` update:*
- Add: ADR-first rule (no structural change without an accepted ADR).
- Add: how to run the full verification suite (`pytest`,
  `validate_invariants.py`, `capabilities --json`).
- Add: logging policy (forbidden fields, rationale).
- Add: how to add a new provider (the three files to touch, the contract to
  implement, the ADR required).
- Add: how to add a new example to `examples/`.
- Target: under 120 lines, prose not bullets.

*`examples/` directory (new):*
Each example is a standalone Python script with a comment header explaining what
it demonstrates, what to expect when you run it, and what prerequisite model is
needed.

- `examples/01_first_run.py` — minimal working example: one prompt, one response,
  prints the result. Demonstrates that the governance layer is invisible from the
  outside when everything is configured correctly.
- `examples/02_routing_explained.py` — runs `resolve_route()` for each mode,
  prints what model would be selected, and explains why. No model call made.
  Useful for verifying configuration without needing Ollama running.
- `examples/03_audit_gate.py` — runs a prompt with `--audit` flag, shows the
  challenger intercepting and returning a verdict. Demonstrates the governance
  layer becoming visible when an audit pass is requested.
- `examples/04_runbook.py` — defines and executes a two-step runbook. Demonstrates
  bounded orchestration: step 1 completes, checkpoint saved, step 2 runs.
- `examples/05_session_governance.py` — starts a steward-mode session, runs two
  turns, shows the steward gate triggering at the configured threshold. Demonstrates
  human supervision capability.
- `examples/README.md` — one paragraph per example explaining what it demonstrates
  and what IO-III property it shows. Should be the first document a new user reads
  after GETTING_STARTED.md.

**Closes when:** README is under 150 lines and passes a readability review by a
non-technical reader (the tester's concern). All `docs/user-guide/` files exist.
All five examples run cleanly against a configured local Ollama instance. No
document references the old project name.

---

### M10.4 — Container Deployment Surface

**Description:** Deliver a Docker-based deployment path per ADR-032. The container
is packaging only — no new execution semantics.

**Deliverables:**

*`Dockerfile`:*
- Base: `python:3.12-slim`
- Install: `pip install -e ".[dev]"` (or production deps only)
- Config directory: declared as `VOLUME ["/app/config"]`, mapped to
  `architecture/runtime/config/` inside the container
- `OLLAMA_HOST` declared as `ENV OLLAMA_HOST=http://host-gateway:11434`
  (sensible default for users running Ollama on the host)
- Exposes port 8080
- Entry point: `python -m [new_name] serve --host 0.0.0.0 --port 8080`

*`docker-compose.yml`:*
- `[new_name]` service: builds from Dockerfile, mounts `./architecture/runtime/config`
  as the config volume, exposes 8080.
- `ollama` sidecar service (optional, commented out by default): uses
  `ollama/ollama` image, exposes 11434. Comment block explains when to use this
  versus pointing at a host Ollama instance.
- `OLLAMA_HOST` set to the sidecar service name when sidecar is enabled.

*Documentation:*
- `docs/user-guide/DOCKER.md` (new file): three usage paths — (1) container
  with host Ollama, (2) full docker-compose with sidecar, (3) custom config
  volume. Includes a note that GPU passthrough for Ollama requires additional
  host configuration outside this project's scope.
- Docker quick start added to `GETTING_STARTED.md` (one section, three commands).
- Docker badge added to README.

**Invariant check:** `docker build` succeeds. Container runs, serves on 8080,
and correctly routes a test prompt through Ollama. `validate_invariants.py` runs
cleanly inside the container.

**Closes when:** `docker compose up` produces a working instance with Ollama
reachable from the container. Documentation is complete.

---

### M10.5 — Web UI File Upload

**Description:** Add file upload capability to the web UI per ADR-029. Phase 10
delivers the Option A (client-side) implementation. Option B (server-side pipeline)
is scoped to Phase 11 with ADR-029 as its governing contract.

**Deliverables (Option A — client-side injection):**

*`io_iii/api/static/index.html` changes:*
- Add a file attachment button (paperclip icon) adjacent to the prompt input field.
- Clicking the button opens a native file picker. Accepted types: `.txt`, `.md`,
  `.csv`, `.json`, `.yaml`, `.py` (text files only for Phase 10 — binary files
  silently rejected with a UI message).
- When a file is selected, its text content is read via the FileReader API and
  stored in local state. A small indicator shows the filename and an ×
  dismiss button.
- On submit: the file content is prepended to the prompt string in a clearly
  delimited block:
  ```
  [Attached file: filename.txt]
  ---
  [file content here]
  ---
  [User prompt here]
  ```
- The assembled string is sent as the prompt to `POST /run` or the session turn
  endpoint as normal. No new API endpoint required.
- Content safety note: file content enters the prompt string and is therefore
  subject to ADR-003 (no prompt content in logs). No change to existing behaviour.

*`docs/user-guide/GETTING_STARTED.md` update:*
- Add a short section on file upload: what it does, what file types are supported,
  the character limit (inherits from `context_limit_chars` in `runtime.yaml`).

*Test:*
- The file injection logic is client-side JavaScript. Add a brief note in
  `examples/` or the user guide explaining the character limit implication for
  large files.

**Closes when:** A user can attach a `.txt` file in the web UI and see its
content treated as part of the prompt. Non-text files are rejected with a
clear message. The character limit from `runtime.yaml` still applies.

---

### M10.6 — OpenAI-Compatible Transport Endpoint *(conditional)*

**Condition:** This milestone is only included in Phase 10 if ADR-030 scopes the
endpoint to Phase 10. If ADR-030 assigns it to Phase 11, this milestone is
dropped and the ADR stands as a Phase 11 gate.

**Description:** Add a `/v1/chat/completions` endpoint that maps the OpenAI Chat
Completions API request shape to the existing IO-III session and engine layer.
Transport adapter only, per ADR-025 and ADR-030. No new execution semantics.

**Deliverables (if in scope):**

*`io_iii/api/` additions:*
- `_openai_compat.py`: request/response shape translation. Maps `messages` array
  to an assembled prompt string. Maps `model` field to an IO-III routing mode
  via a configurable translation table in `runtime.yaml`.
- New route in `server.py` or `app.py`: `POST /v1/chat/completions`
- Supported fields: `model`, `messages`, `stream` (boolean). Unsupported
  OpenAI fields return a structured error: `{"error": {"code": "unsupported_field",
  "message": "..."}}`
- `content_release: true` must be set in `runtime.yaml` for the endpoint to
  surface model output (ADR-026 applies).

*`architecture/runtime/config/runtime.yaml` addition:*
- `openai_compat_model_map`: optional mapping from OpenAI model strings to
  IO-III routing modes. Example:
  ```yaml
  openai_compat_model_map:
    gpt-4o: executor
    gpt-3.5-turbo: fast
    default: executor
  ```

*Tests:*
- `tests/test_openai_compat_m106.py`: verifies request translation, response
  shape, unsupported field error, and that all Phase 1–9 invariants remain true
  on a request through this endpoint.

*Documentation:*
- `docs/user-guide/OPENAI-COMPAT.md`: how to point an existing OpenAI SDK client
  at IO-III. One code example. Notes on what is and is not supported.

**Closes when:** `openai` Python client can be pointed at `http://localhost:8080`
and successfully exchange a message through the IO-III runtime with all governance
invariants intact.

---

### M10.7 — Launch Verification and Tag

**Description:** Full end-to-end verification from a clean state before public
announcement. This milestone is process, not code.

**Deliverables:**

1. Run `pytest` — all tests pass. Zero deprecation warnings. Test count recorded.
2. Run `python architecture/runtime/scripts/validate_invariants.py` — all
   invariants pass.
3. Perform a clean installation test: fresh machine (or clean VM/container),
   no prior IO-III environment. Follow `GETTING_STARTED.md` verbatim. Record any
   step that fails or requires knowledge outside the document. Fix the document or
   the code until the test passes without deviation.
4. Verify `docker compose up` produces a working instance (if M10.4 complete).
5. Verify `python -m [new_name] init` and `python -m [new_name] validate` produce
   clean output against the neutral template config.
6. Confirm `LICENSE` file exists in repo root with the selected licence text.
7. Confirm no file in the public repo contains: the old project name, the developer's
   local filesystem paths, internal session state content, or the `audience: portfolio`
   tag.
8. Set repository to public.
9. Tag `v1.0.0`.
10. Post release notes referencing `CHANGELOG.md`.

**Closes when:** Repository is public, `v1.0.0` is tagged, and a person with no
prior context can follow `GETTING_STARTED.md` to a working first session without
assistance.

---

## Dependency Graph

```
M10.0 (ADRs + decisions)
  │
  ├──► M10.1 (Identity) ──────────────────────────────────────────────────┐
  │         │                                                              │
  │         ├──► M10.2 (Resilience)                                       │
  │         │                                                              │
  │         ├──► M10.3 (Documentation) ───────────────────────────────────┤
  │         │                                                              │
  │         ├──► M10.4 (Docker) [ADR-032]                                 │
  │         │                                                              │
  │         └──► M10.5 (File Upload) [ADR-029] ──────────────────────────►M10.7
  │                                                                        │
  │         M10.6 (OpenAI Compat) [ADR-030, conditional] ────────────────►│
  │                                                                        │
  └──────────────────────────────────────────────────────────────────────►M10.7
```

M10.2, M10.3, M10.4, M10.5, and M10.6 are independent of each other and can be
worked in parallel after M10.1 closes. There is no dependency between them.

M10.7 requires all other milestones to be complete (or explicitly dropped, in the
case of M10.6 if scoped to Phase 11).

---

## Estimated Scope Summary

| Milestone | Stream | Effort | Blocker |
| --- | --- | --- | --- |
| M10.0 — ADRs + decisions | A | 1–2 days | New name, licence, file upload approach |
| M10.1 — Identity | A | 0.5–1 day | M10.0 closed, new name confirmed |
| M10.2 — Resilience | A | 0.5 day | M10.1, ADR-028 |
| M10.3 — Documentation | A | 3–5 days | M10.1 |
| M10.4 — Docker | B | 1–2 days | M10.1, ADR-032 |
| M10.5 — File Upload | B | 0.5–1 day | M10.1, ADR-029 |
| M10.6 — OpenAI Compat | B | 2–3 days | M10.1, ADR-030 (conditional) |
| M10.7 — Launch Verification | A+B | 0.5 day | All prior |

Stream A total (without M10.6): approximately 5–9 days.
Stream B total (without M10.6): approximately 2–4 days parallel to Stream A.
Stream B with M10.6: approximately 4–7 days parallel to Stream A.

---

## Phase 11 Scope (Placeholder)

Phase 10 writes ADRs for the following but does not implement them. They are the
governing gate for Phase 11 planning.

- Knowledge extension via retrieval-augmented generation (ADR-031)
- OpenAI transport compatibility endpoint (ADR-030, if scoped to Phase 11)
- Server-side file upload pipeline and context assembly integration (ADR-029 §B)
- Real cloud provider adapter implementations (ADR-028, Option C)

No Phase 11 work begins without a governing DOC-ARCH document and accepted ADRs.

---

*Phase 10 governing document. Tag: v1.0.0 (target). Iteration: 01.*