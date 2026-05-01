# Changelog

All structural milestones for Io³. Detailed architecture documentation lives in `docs/architecture/`.

---

## v0.9.0: Phase 9, API & Integration Surface

Thin, content-safe HTTP surface wrapping the existing CLI and session layer. No new execution semantics. All Phase 1–8 invariants preserved.

- **ADR-025** transport adapter contract: endpoint-to-CLI mapping, content safety extension, SSE contract, webhook contract, structured exit codes, web UI contract
- **M9.1** HTTP API: `POST /run`, `POST /runbook`, `POST /session/start`, `POST /session/{id}/turn`, `GET /session/{id}/state`, `DELETE /session/{id}`
- **M9.2** Server-Sent Events on `GET /session/{id}/stream`: `turn_started`, `turn_output`, `turn_completed`, `steward_gate_triggered`, `turn_error`
- **M9.3** Webhook dispatcher: best-effort delivery on `SESSION_COMPLETE`, `RUNBOOK_COMPLETE`, `STEWARD_GATE_TRIGGERED`; content-safe payloads; silent failure
- **M9.4** CLI: `--output json` flag; `serve` subcommand; structured exit codes (0/1/2/3)
- **M9.5** Self-hosted web UI: single static HTML file, no external dependencies, steward pause controls
- **ADR-026** Governed content release gate: `content_release: true` in `runtime.yaml` surfaces model output in API responses

Governing document: `docs/architecture/DOC-ARCH-017-phase-9-guide.md`

---

## v0.8.0: Phase 8, Governed Dialogue Layer

Multi-turn session governance with human supervision capability. Engine stack unchanged throughout.

- **M8.1 + M8.4** Work mode and steward mode (`SessionMode`); `StewardGate` evaluating configurable thresholds; session pause state contract
- **M8.2 + M8.3** Session persistence (`save_session` / `load_session`); snapshot import/export
- **M8.5** Session shell CLI: `session start`, `session continue`, `session status`, `session close`; exit code 3 for steward pause
- **M8.6** Dialogue session test suite (916 tests at phase close)

Governing document: `docs/architecture/DOC-ARCH-016-phase-8-guide.md`

---

## v0.7.0: Phase 7, Open-Source Initialisation Layer

Runtime made self-initialising for external users. Clone → configure → run without modifying structural code.

- `python -m io_iii init` and `python -m io_iii validate` commands
- Neutral template files: `persona.yaml`, `chat_session.yaml`
- Portability validation pass with `PORTABILITY_CHECK_FAILED` failure code
- ADR-024: Work Mode / Steward Mode governance prerequisite for Phase 8

Governing document: `docs/architecture/DOC-ARCH-015-phase-7-guide.md`

---

## v0.6.0: Phase 6, Memory Architecture

Governed, deterministic memory as a bounded input to context assembly. No retrieval autonomy, no dynamic routing.

- **M6.1** Memory store: atomic, scoped, versioned records
- **M6.2** Memory pack system: named bundles declared in `memory_packs.yaml`
- **M6.3** Memory retrieval policy: route and capability allowlists; sensitivity-gated access
- **M6.4** Memory injection: bounded injection via context assembly; budget-enforced
- **M6.5** Memory safety invariants: INV-005 enforces content-safe logging
- **M6.6** Memory write contract: user-confirmed atomic single-record write
- **M6.7** Session snapshot export/import

Governing document: `docs/architecture/DOC-ARCH-014-phase-6-guide.md`

---

## v0.5.0: Phase 5, Runtime Observability & Optimisation

Measurement and governance signals added without expanding execution surface.

- **M5.1** Token pre-flight estimator: configurable context ceiling before every provider call
- **M5.2** Execution telemetry: `ExecutionMetrics` dataclass; content-safe projection to `metadata.jsonl`
- **M5.3** Constellation integrity guard: config-time validation; `CONSTELLATION_DRIFT` failure code

Governing document: `docs/architecture/DOC-ARCH-013-phase-5-guide.md`

---

## v0.4.0: Phase 4, Context Architecture Formalisation

Bounded runbook execution with deterministic continuity semantics.

- ADR-018: run identity and immutable lineage
- ADR-019: checkpoint persistence contracts
- ADR-020: replay from checkpoint; resume from first incomplete step
- `source_run_id` preserved for lineage traceability

Governing document: `docs/architecture/DOC-ARCH-012-phase-4-guide.md`

---

## Phase 3: Capability Layer

Bounded capability extensions inside the execution engine. Deterministic, explicitly invoked, registry-controlled, single-execution only. No autonomous behaviour or dynamic routing.

---

## Phase 2: Structural Consolidation

- `SessionState` v0 implemented
- Execution engine extracted from CLI
- CLI-to-engine boundary established
- `ExecutionContext` introduced
- Context assembly integrated (ADR-010)
- Challenger ownership consolidated inside the engine

---

## Phase 1: Control Plane Stabilisation

- Deterministic routing (ADR-002)
- Challenger enforcement (ADR-008)
- Bounded audit gate contract (ADR-009)
- Invariant validation suite
- Regression enforcement
