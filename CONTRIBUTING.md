# Contributing

---

## Scope and constraints

IO-III is a governance-first deterministic LLM runtime.
It is intentionally minimal and bounded.
It is not an agent system.

Non-goals include:
- autonomous behaviour
- tool planning
- recursive orchestration
- dynamic routing
- multi-step agent loops

---

## Local development

### Requirements

- Python 3.12+
- pip

### Install

```bash
pip install -e ".[dev]"
```

---

## Verification

Run the full verification suite:

```bash
python -m pytest
python architecture/runtime/scripts/validate_invariants.py
python -m io_iii capabilities --json
```

---

## Logging policy

Logs must never contain prompts or model output.

Forbidden fields:
- prompt
- completion
- draft
- revision
- content

Allowed examples:
- prompt_hash
- latency
- provider
- model
- route
- capability metadata
- audit metadata

---

## Pull requests

- Keep changes minimal and bounded.
- Do not introduce agent behaviour.
- Preserve ADR invariants.
- Update docs when behaviour or architecture changes.
