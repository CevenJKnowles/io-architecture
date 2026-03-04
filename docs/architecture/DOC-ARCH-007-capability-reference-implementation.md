# DOC-ARCH-007 — Capability Reference Implementation

This document defines the **Phase 3 reference capability implementation** shipped with IO-III.

The purpose is to provide a concrete example of:

- explicit capability ID invocation
- deterministic registry wiring
- bounded payload/output enforcement
- structured results attached to `ExecutionResult.meta["capability"]`
- content-safe behavior (no prompt/output logging)

This capability is not intended as a “tool system”. It is a bounded architectural fixture.

---

## Reference capability: `cap.echo_json`

### Intent

`cap.echo_json` is a **content-safe structural summariser** for JSON payloads.

It demonstrates end-to-end capability invocation without exposing payload content.

### Invocation

Use the CLI:

```bash
python -m io_iii run executor --prompt "Return one word." \
  --capability-id cap.echo_json \
  --capability-payload-json '{"example": true, "n": 2}'
```

### Output contract

The capability returns:

- `ok: true`
- `output.summary` fields:
  - `payload_bytes` — approximate JSON-serialized size
  - `payload_type` — Python type name at invocation boundary
  - `top_level_keys` — number of keys if payload is a mapping
  - `top_level_len` — length if payload is a list/tuple/set

It does **not** return the payload itself.

---

## Registry wiring

The reference runtime ships a deterministic built-in registry:

- `io_iii/capabilities/builtins.py`
- `builtin_registry()` returns a `CapabilityRegistry` with declared built-ins

The engine does not auto-discover capabilities. Invocation remains **explicit-only**.

---

## Bounds

The capability is declared with conservative bounds:

- `max_calls = 1`
- `timeout_ms = 50`
- `max_input_chars = 4096`
- `max_output_chars = 1024`

The engine enforces payload/output bounds in the explicit invocation surface.

---

## Non-goals

This reference capability does not introduce:

- tool selection
- multi-capability orchestration
- recursion surfaces
- autonomous behavior
- side effects
