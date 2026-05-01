---
id: ADR-031
title: Knowledge Extension and RAG Architecture Boundary
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
  - phase-11
  - memory
  - rag
  - context-assembly
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-031 — Knowledge Extension and RAG Architecture Boundary

## Status

Accepted — this ADR defines the boundary of current knowledge injection capabilities
and acts as the gate document for Phase 11 RAG implementation. No retrieval
infrastructure is introduced in Phase 10.

---

## 1. Context

A common question from operators and users is: how do I give I0³ access to knowledge
beyond the model's training cutoff, or to domain-specific information not present in
the base model?

The Phase 6 memory architecture (ADR-022) provides memory packs: named bundles of
structured records injected into context assembly before each provider call. Memory
packs are the correct current-phase answer for bounded, manually maintained domain
knowledge. They are deterministic, auditable, and governed by the existing retrieval
policy (ADR-022 §4).

Retrieval-Augmented Generation (RAG) — embedding-based similarity search over a
document corpus, retrieving relevant chunks at query time and injecting them into
context — is a categorically different capability. It requires:

- A new retrieval adapter interface (not present in the current architecture)
- A vector store integration (no such integration exists)
- An embedding provider or local embedding model
- A new context assembly input lane (amending ADR-010)
- New content safety invariants covering retrieval-derived content
- New bounded execution contracts governing retrieval call counts and output volume

Implementing RAG without these structural prerequisites would require ad-hoc
workarounds that circumvent the ADR-010 context assembly contract and the bounded
execution invariants established in ADR-009 and ADR-012. This is not permitted.

---

## 2. Decision

### §1 Phase 10 posture — memory packs as the knowledge extension mechanism

The Phase 6 memory pack system (ADR-022) is the supported and complete mechanism for
knowledge injection in Phase 10. Operators who need domain-specific or recent
knowledge available to the runtime should use memory packs. The GETTING_STARTED.md
and MODELS.md documentation explains how to author and register memory packs.

No ad-hoc retrieval workarounds — direct vector database calls, embedding injections,
or external knowledge fetch hooks — are permitted within the Phase 10 codebase. Any
such addition requires a new ADR.

### §2 RAG deferred to Phase 11

Retrieval-Augmented Generation is formally deferred to Phase 11. Phase 11
implementation requires the following ADRs before any code is written:

- ADR-033: RAG Retrieval Adapter Contract — defines the retrieval adapter interface,
  how retrieved chunks enter context assembly as a new bounded input lane, and the
  invariant constraints that govern retrieval behaviour
- ADR-034: Embedding Provider Contract — defines which vector stores are supported,
  how embeddings are generated, and how the retrieval adapter is registered

These ADRs must be accepted before Phase 11 RAG implementation begins.

### §3 Boundary conditions for Phase 11 RAG

When Phase 11 implements RAG, the following constraints apply and are established
here as governing intent:

- Retrieved content enters context assembly as a new bounded input lane, not as a
  modification to the prompt string or the memory pack lane
- Retrieval is triggered explicitly and deterministically — no autonomous retrieval
  based on model output or dynamic query rewriting
- Retrieved content is subject to the same content safety invariants as prompt text
  and memory values (ADR-003): retrieved content never appears in log fields or
  metadata records
- Retrieval call counts are bounded per execution context, consistent with ADR-009
  and ADR-012 bounded execution semantics
- `engine.py`, `routing.py`, and `telemetry.py` are not modified to support RAG

### §4 Recommended Phase 11 vector store

Chroma is the recommended reference implementation for Phase 11 RAG. It is local-
first, requires no external service, is MIT licensed, and has a pure Python client.
This recommendation is advisory only and does not bind the Phase 11 ADR.

---

## 3. Consequences

- Phase 10 ships with memory packs as the complete knowledge injection story. This
  is communicated clearly in user-facing documentation.
- No vector database dependencies are introduced in Phase 10.
- Phase 11 RAG implementation has a clear governance prerequisite (ADR-033, ADR-034)
  and a set of boundary conditions to design against.
- Operators who attempt to add retrieval workarounds within Phase 10 are explicitly
  blocked by this ADR.

---

## 4. Non-goals

- This ADR does not implement RAG in any form.
- This ADR does not introduce vector database dependencies.
- This ADR does not introduce embedding models or embedding provider adapters.
- This ADR does not modify context assembly, the engine, or the routing layer.
- This ADR does not specify OCR or document ingestion pipelines.