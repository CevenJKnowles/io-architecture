# IO-III Architecture

IO-III is a local LLM control-plane runtime: a Python layer that sits between you and a language model and governs how that interaction behaves. Where most LLM tooling is
permissive by default, IO-III is restrictive by design. Execution limits are hard-coded.
Content boundaries are enforced recursively at the logging level. Every significant
architectural decision is documented in an ADR before it is implemented. The system
knows what it will not do, and that refusal is structural rather than conventional.

Built over nine design generations. Phase 9 complete.
Latest stable phase tag: `v0.9.0`.

---

## Architecture Principles

IO-III follows a small set of architectural principles that guide all design decisions.

**Determinism First**
All routing and execution behaviour must be predictable and reproducible. No dynamic routing or autonomous behaviour is introduced.

**Bounded Execution**
All control flows have explicit limits (audit passes, revision passes, capability invocation). The system rejects recursive or unbounded execution paths.

**Architecture Before Implementation**
Structural changes require an Architecture Decision Record (ADR) before code changes.

**Governance by Design**
Operational constraints (audit limits, routing discipline, invariants) are enforced structurally in the runtime rather than through convention.

**Minimal Reference Implementation**
The Python runtime intentionally demonstrates the architecture without expanding into a full orchestration framework.

---

## Project Status

| **Phase** | **Description** | **Status** | **Tag** |
| --- | --- | --- | --- |
| 1 | Control Plane | Complete | — |
| 2 | Structural Consolidation | Complete | — |
| 3 | Capability Layer | Complete | — |
| 4 | Context Architecture Formalisation | Complete | `v0.4.0` |
| 5 | Runtime Observability & Optimisation | **Complete** | `v0.5.0` |
| 6 | Memory Architecture | **Complete** | `v0.6.0` |
| 7 | Open-Source Initialisation Layer | **Complete** | `v0.7.0` |
| 8 | Governed Dialogue Layer | **Complete** | `v0.8.0` |
| 9 | API & Integration Surface | **Complete** | `v0.9.0` |

IO-III prioritises **determinism, governance discipline, and architectural clarity** over
feature velocity.

---

## Why This Architecture Matters

Most local LLM projects optimise for capability breadth.

IO-III treats runtime governance as the primary systems problem: deterministic routing, bounded execution, explicit failure semantics, immutable lineage, and recoverable continuity.

The result is a runtime architecture that remains inspectable under failure, reproducible across milestones, and portable as a governed control-plane substrate.

```text
runbook → checkpoint → failure
                    ├── replay → step 0
                    └── resume → failed_step_index
```

---

## Structural Guarantees

Unlike feature-driven AI frameworks, IO-III focuses on structural guarantees:

- deterministic routing
- bounded execution
- explicit audit gates
- invariant-protected runtime behaviour
- architecture-first governance

The repository contains:

1. a formal architecture specification layer (ADRs, invariants, contracts, governance rules)
2. a minimal reference implementation of the runtime control plane

---

## Non-Goals

IO-III is intentionally **not**:

- an agent framework
- a dynamic tool orchestrator
- a workflow engine
- an autonomous AI system
- a recursive reasoning pipeline

The runtime behaves as a **deterministic control-plane execution engine**. These
exclusions are structural, not conventional.

---

## Request Lifecycle

```mermaid
sequenceDiagram
participant User
participant CLI as cli.py
participant Routing as routing.py
participant Engine as engine.py
participant Context as context_assembly.py
participant Provider
participant Challenger
User->>CLI: run executor prompt
CLI->>CLI: load configuration
CLI->>Routing: resolve_route()
Routing-->>CLI: provider + model
CLI->>Engine: engine.run()
Engine->>Engine: create SessionState
Engine->>Engine: create ExecutionContext
Engine->>Context: assemble_context()
Context-->>Engine: structured prompt
Engine->>Provider: generate()
Provider-->>Engine: draft response
alt audit enabled
Engine->>Challenger: audit draft
Challenger-->>Engine: verdict
end
Engine-->>CLI: final output
CLI-->>User: display result
```

---

## System Layer Architecture

```mermaid
flowchart TB
subgraph Interface
CLI["CLI Interface"]
end
subgraph ControlPlane["Control Plane"]
ENGINE["Execution Engine"]
CTX["ExecutionContext"]
ASSEMBLY["Context Assembly"]
end
subgraph Runtime
PROVIDER["Provider Adapter"]
end
subgraph Governance
CHALLENGER["Challenger Layer"]
end
CLI --> ENGINE
ENGINE --> CTX
CTX --> ASSEMBLY
ASSEMBLY --> PROVIDER
PROVIDER --> CHALLENGER
```

---

## Python Module Architecture

```mermaid
flowchart LR
subgraph CLI
    ID_CLI["io_iii/cli.py"]
end
subgraph Core
    ID_ENGINE["core/engine.py"]
    ID_SESSION["core/session_state.py"]
    ID_CTX["core/execution_context.py"]
    ID_ASSEMBLY["core/context_assembly.py"]
end
subgraph Routing
    ID_ROUTING["routing.py"]
end
subgraph Providers
    ID_OLLAMA["providers/ollama_provider.py"]
    ID_NULLP["providers/null_provider.py"]
end
subgraph Config
    ID_CONFIG["config loader"]
    ID_RUNTIMECFG["runtime/config/*.yaml"]
end
ID_CLI --> ID_CONFIG
ID_CLI --> ID_ROUTING
ID_CLI --> ID_ENGINE
ID_CONFIG --> ID_RUNTIMECFG
ID_ENGINE --> ID_SESSION
ID_ENGINE --> ID_CTX
ID_ENGINE --> ID_ASSEMBLY
ID_ENGINE --> ID_OLLAMA
ID_ENGINE --> ID_NULLP
ID_ROUTING --> ID_OLLAMA
ID_ROUTING --> ID_NULLP
```

---

## Quick Run
```bash
python -m io_iii run executor --prompt "Explain deterministic routing in one sentence."
```
Expected behaviour:

- the CLI loads runtime configuration
- deterministic routing selects the provider
- the execution engine runs the prompt pipeline
- the challenger optionally audits the output (if enabled)

---

## Architecture Validation

Run the invariant validator:
```bash
python architecture/runtime/scripts/validate_invariants.py
```
Run the full test suite:
```bash
pytest
```
Both commands verify that the system satisfies its core architectural invariants.

---

## Capability Invocation (Phase 3)

Capabilities are introduced in Phase 3 as bounded runtime extensions.
|  **Capabilities are:** |  They do **not** introduce: |
|---|---|
|  - explicitly invoked |  - autonomous behaviour |
|  - registry-controlled |  - tool selection |
|  - single-execution only |  - recursive execution |
|  - payload-bounded |  - workflow orchestration |
|  - output-bounded |   |

```mermaid
sequenceDiagram
participant CLI
participant Engine
participant Registry
participant Capability
participant Result
CLI->>Engine: run(capability_id)
Engine->>Registry: resolve capability
Registry-->>Engine: capability spec
Engine->>Capability: invoke(payload)
Capability-->>Engine: CapabilityResult
Engine-->>Result: ExecutionResult.meta["capability"]
```

---

## Core Invariants

IO-III enforces the following system-level guarantees:
- deterministic routing only
- challenger enforcement internal to the engine
- audit execution explicitly user-toggled
- bounded audit passes (`MAX_AUDIT_PASSES = 1`)
- bounded revision passes (`MAX_REVISION_PASSES = 1`)
- no recursion loops
- no multi-pass execution chains
- single unified final output

These are treated as contract-level invariants enforced by the test suite and invariant validator, not by convention.

---

## Governance Model

All structural changes follow an ADR-first development model.

Any modification affecting:
- control-plane design
- routing logic or fallback policy
- provider or model selection
- audit gate behaviour
- persona binding or runtime governance
- memory or persistence layers
- cross-model interaction

requires a new Architecture Decision Record inside `ADR/` before implementation begins.

The repository functions as the source of truth for IO-III architectural boundaries.

---

## Control-Plane Reference Implementation

The Python implementation is deliberately minimal. Its purpose is to demonstrate boundary
discipline and deterministic control-plane structure under governance constraints.

Core modules:
| Module | Responsibility |
|---|---|
| `config.py` | runtime config loading |
| `routing.py` | deterministic route resolution |
| `core/engine.py` | execution engine |
| `core/context_assembly.py` | context assembly (ADR-010) |
| `core/session_state.py` | control-plane state container |
| `core/execution_context.py` | engine-local runtime container |
| `core/preflight.py` | token pre-flight estimator (M5.1) |
| `core/telemetry.py` | execution telemetry metrics (M5.2) |
| `core/constellation.py` | constellation integrity guard (M5.3) |
| `core/portability.py` | portability validation pass (M7.4) |
| `providers/null_provider.py` | null provider adaptor |
| `providers/ollama_provider.py` | Ollama provider adaptor |
| `cli.py` | CLI entrypoint |

Execution path:

`CLI → Engine.run() → ExecutionContext → Context Assembly → Provider → Challenger (optional)`

---

## Documentation Structure

```
DOC-OVW   system overview documents
DOC-ARCH  architecture definitions
DOC-IMPL  implementation documentation
DOC-RUN   runtime configuration documentation
DOC-GOV   governance documentation
ADR       architectural decision records
```

Primary entry points:
```
docs/overview/DOC-OVW-001-architecture-overview-index.md
docs/architecture/DOC-ARCH-001-runtime-architecture.md
```

---

## Repository Layout

```
ADR/                       architecture decision records

docs/
  overview/                high-level system documentation
  architecture/            architecture definitions
  governance/              governance rules and lifecycle policies
  runtime/                 runtime metadata and execution contracts

architecture/
  runtime/
    config/                canonical runtime configuration
    tests/                 invariant fixtures
    scripts/               invariant validator

io_iii/                    reference runtime implementation
  core/                    engine components
  providers/               provider adapters
  routing.py               deterministic routing
  cli.py                   CLI interface
```

---

## Milestones

### Phase 1 - Control Plane Stabilisation

- deterministic routing
- challenger enforcement (ADR-008)
- bounded audit gate contract (ADR-009)
- invariant validation suite
- regression enforcement

### Phase 2 - Structural Consolidation

- SessionState v0 implemented
- execution engine extracted
- CLI to engine boundary established
- context assembly integrated (ADR-010)
- ExecutionContext introduced
- challenger ownership consolidated inside the engine
- provider injection seams implemented
- tests passing (pytest)
- invariant validator passing

### Phase 3 - Capability Layer

Bounded capability extensions introduced inside the execution engine. Capabilities remain
deterministic, explicitly invoked, registry-controlled, and single-execution only. No
autonomous behaviour or dynamic routing introduced.

### Phase 4 - Context Architecture Formalisation

Phase 4 extends bounded runbook execution into deterministic continuity semantics.

Implemented guarantees:

- run identity and immutable lineage
- checkpoint persistence contracts
- replay from checkpoint snapshot
- resume from first incomplete or failed step
- checkpoint integrity validation before execution
- new `run_id` per replay/resume invocation
- `source_run_id` preserved for lineage traceability

Execution continuity now remains bounded, deterministic, and structurally governed.

### Phase 5 - Runtime Observability & Optimisation

Phase 5 introduces measurement and governance signals into the runtime without expanding its execution surface. The Phase 1–4 execution stack remains frozen throughout.

Delivered capabilities:

- **M5.1 Token Pre-flight Estimator** — heuristic character-count estimator enforcing a configurable context limit ceiling before every provider call; prerequisite for Phase 6 M6.4
- **M5.2 Execution Telemetry Metrics** — `ExecutionMetrics` dataclass attached to `ExecutionResult.meta["telemetry"]`; Ollama native token counts (`prompt_eval_count`, `eval_count`) surfaced; content-safe projection to `metadata.jsonl`
- **M5.3 Constellation Integrity Guard** — config-time validation detecting role-model collapse, missing role bindings, and call chain bound violations before execution begins; `CONSTELLATION_DRIFT` failure code; `--no-constellation-check` bypass flag

Phase 5 is complete. Tag: `v0.5.0`.

### Phase 6 - Memory Architecture

Phase 6 introduced governed, deterministic memory as a bounded input to context assembly. The execution stack remained frozen throughout. No retrieval autonomy, no persistent session state, no dynamic routing.

Delivered capabilities:

- **M6.1 Memory Store** — atomic, scoped, versioned records; local file store under configurable root
- **M6.2 Memory Pack System** — named bundles declared in `memory_packs.yaml`; deterministic resolution
- **M6.3 Memory Retrieval Policy** — route and capability allowlists; sensitivity-gated access
- **M6.4 Memory Injection** — bounded injection into `ExecutionContext` via context assembly; budget-enforced; declaration-order deterministic
- **M6.5 Memory Safety Invariants** — INV-005 enforces content-safe logging via invariant validator; `python_requires_pattern` and `python_forbids_pattern` assertion types added
- **M6.6 Memory Write Contract** — user-confirmed atomic single-record write; `MEMORY_WRITE_FAILED` on any failure; no value logged
- **M6.7 Session Snapshot Export/Import** — portable control-plane artefact; `SNAPSHOT_SCHEMA_INVALID` on validation failure; prerequisite for Phase 8 M8.3

Phase 6 is complete. Tag: `v0.6.0`.

Governing document: `docs/architecture/DOC-ARCH-014-phase-6-guide.md`.

### Phase 7 - Open-Source Initialisation Layer

Phase 7 makes the IO-III runtime self-initialising for external users. The goal: clone → configure → run, without modifying structural code.

Delivered capabilities:

- initialisation contract defining the minimum required user configuration (M7.1)
- `python -m io_iii init` command and `python -m io_iii validate` command (M7.2, M7.4)
- neutral template files: `persona.yaml`, `chat_session.yaml` bounded session template (M7.3)
- portability validation pass with `PORTABILITY_CHECK_FAILED` failure code (M7.4)
- clean config/structural separation confirmed by Phase 7 audit (M7.0)
- Work Mode / Steward Mode ADR-024 — governance prerequisite for Phase 8 M8.1 (M7.5)

Phase 7 is complete. Tag: `v0.7.0`.

Governing document: `docs/architecture/DOC-ARCH-015-phase-7-guide.md`.

---
