---
id: ADR-030
title: Cloud LLM API Transport Adapter
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
  - phase-11
  - api
  - cloud-llm
  - transport
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-030 — Cloud LLM API Transport Adapter

## Status

Accepted — implementation deferred to Phase 11. This ADR is a gate document written
in Phase 10 to govern Phase 11 implementation. No code is produced under this ADR
in Phase 10.

---

## 1. Context

The Phase 9 HTTP API exposes I0³-native endpoints (`POST /run`, `POST /session/start`,
etc.). Users and organisations already using cloud LLM provider SDKs or compatible
client libraries cannot point their existing code at I0³ without rewriting their API
calls to the I0³ request shape.

A transport adapter endpoint that accepts an established cloud LLM API request format
would allow drop-in adoption: existing client code, tooling, and integrations can
target I0³ without modification. The `POST /v1/chat/completions` surface is the
appropriate initial target. Although it originated with one provider, it has since
been adopted as a de facto interchange format across the broader ecosystem — including
Mistral, Groq, Together AI, Ollama, and others — making it a vendor-neutral transport
standard in practice.

Other cloud provider API shapes (for example Anthropic's `/v1/messages` or Google's
Gemini API) are in scope for subsequent phases. Phase 11 implements the
`/v1/chat/completions` surface as the first adapter; further adapters follow the same
transport-only contract and require their own supplementary ADR before implementation.

The endpoint is architecturally viable as a transport adapter only. The execution
semantics, governance invariants, and content safety rules established in Phases 1–9
are not affected by the shape of the incoming request. Any supported cloud LLM API
request format is translated into the existing I0³ session and engine pipeline at the
API boundary.

The implementation is deferred to Phase 11 because it pairs naturally with cloud
provider adapter delivery (ADR-028 Phase 11, Option C). Shipping the compatibility
endpoint in Phase 10 without a real cloud provider backend would require users to
already have Ollama configured — limiting the adoption benefit. Phase 11 delivers
both simultaneously: an operator can point an existing cloud LLM client at I0³ backed
by either Ollama or a real cloud provider adapter.

---

## 2. Decision

### §1 Phase 11 implementation scope

Phase 11 introduces `POST /v1/chat/completions` as the first transport adapter
endpoint in the Phase 9 API layer. The endpoint:

- Translates the `messages` array into an assembled prompt string
- Maps the `model` field to an I0³ routing mode via `cloud_llm_model_map` in
  `runtime.yaml`
- Routes the request through the existing session and engine layer
- Returns a response in the `/v1/chat/completions` response shape

The endpoint is a transport adapter only. It does not introduce new execution
semantics, bypass governance invariants, or duplicate engine logic at the HTTP layer.
ADR-025 (API-as-Transport-Adapter Contract) governs this endpoint in full.

Additional adapter formats (for example Anthropic `/v1/messages`, Gemini) may be
added in later phases. Each additional adapter requires a supplementary ADR before
implementation begins.

### §2 Supported fields — `/v1/chat/completions` adapter

The following fields are supported in Phase 11:

- `model` — mapped to routing mode via `cloud_llm_model_map`
- `messages` — assembled into a structured prompt string
- `stream` — boolean; when true, response is streamed via the existing SSE layer

All other request fields are rejected with a structured error:
`{"error": {"type": "unsupported_field", "message": "..."}}`

Silent ignore of unsupported fields is explicitly prohibited.

### §3 Model mapping

A new `cloud_llm_model_map` key in `runtime.yaml` maps incoming model identifier
strings to I0³ routing modes. The map is provider-agnostic: any model string from
any supported cloud provider API can be listed. Example:

```yaml
cloud_llm_model_map:
  gpt-4o: executor
  gpt-3.5-turbo: fast
  mistral-large-latest: executor
  claude-3-5-sonnet-20241022: executor
  gemini-2.0-flash: fast
  default: executor
```

If no mapping is found and no `default` is set, the request is rejected with:
`{"error": {"type": "model_not_mapped", "message": "..."}}`.

### §4 Content release requirement

`content_release: true` must be set in `runtime.yaml` for the endpoint to surface
model output in the response body. ADR-026 governs content release. The operator
accepts responsibility for API access control and log retention when enabling this.

### §5 Phase 10 posture

No implementation occurs in Phase 10. The Phase 9 API is not modified. No stub
endpoint is added. The `cloud_llm_model_map` key is not added to `runtime.yaml`
in Phase 10.

### §6 Phase 11 gate conditions

Phase 11 implementation of this endpoint may not begin until:

- Phase 10 is complete and tagged `v1.0.0`
- ADR-028 Phase 11 cloud provider adapters are in progress or complete
- A Phase 11 ADR supplements this record with streaming contract details if the
  SSE response shape for the active adapter format diverges from the existing M9.2
  SSE contract

---

## 3. Consequences

- No code change in Phase 10.
- Phase 11 planning has a clear contract to implement against.
- The transport adapter constraint (ADR-025) is explicitly extended to cover this
  endpoint, preventing future drift toward execution semantics at the HTTP layer.
- The model map key is renamed from `openai_compat_model_map` to `cloud_llm_model_map`
  to reflect provider-agnostic intent. Any Phase 11 implementation must use the new key.

---

## 4. Non-goals

- This ADR does not implement function calling, tool use, or assistants API compatibility.
- This ADR does not implement embeddings, fine-tuning, or legacy completions endpoints
  for any provider.
- This ADR does not implement vision or multimodal input.
- This ADR does not modify the execution engine, routing layer, or telemetry.
- This ADR does not govern provider-specific authentication or credential management;
  that is in scope for ADR-028.

---

## 5. Changelog

| Version | Date       | Change                                                                 |
|---------|------------|------------------------------------------------------------------------|
| v1.0    | 2026-05-01 | Initial gate document, scoped to OpenAI-compatible surface             |
| v1.1    | 2026-05-01 | Generalised to cloud LLM API transport adapter; renamed model map key  |