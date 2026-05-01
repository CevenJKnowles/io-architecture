# Contributing

Io³ is a governance-first deterministic AI runtime. It is intentionally minimal and bounded. Contributions are welcome within those constraints.

---

## Before you write any code: the ADR-first rule

Any change affecting control-plane design, routing logic, provider selection, audit gate behaviour, memory or persistence layers, or API surface requires a new Architecture Decision Record before implementation begins.

The ADR goes in `ADR/` and follows the existing numbering and format. Write it, commit it, and reference it in the PR. If you are unsure whether your change needs an ADR, it almost certainly does; the existing 26 records give you a clear picture of what falls within scope.

Changes that do not require an ADR: documentation updates, test fixes for pre-existing gaps, dependency bumps, and cosmetic refactors that do not alter observable behaviour.

---

## What Io³ will not accept

Io³ will not accept contributions that introduce autonomous behaviour, dynamic routing, output-driven model selection, tool planning, recursive orchestration, multi-step agent loops, or any execution path that does not have a hard bound. These are structural non-goals, each governed by an ADR.

---

## Local development

**Requirements:** Python 3.11+, pip.

```bash
git clone https://github.com/CevenJKnowles/io-architecture.git
cd io-architecture
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Verification suite

Run all three passes before raising a PR:

```bash
pytest
python architecture/runtime/scripts/validate_invariants.py
python -m io_iii capabilities --json
```

The invariant validator checks structural guarantees independently of the test suite. Both must pass. `capabilities --json` confirms the capability registry is consistent.

Known pre-existing failures: 40 Phase 9 test failures are documented in the project's Notion phase plan and are not caused by Phase 10 work. Do not treat them as regressions introduced by your change.

---

## Logging policy

Logs must never contain prompts, completions, drafts, revisions, or any content derived from model input or output. This is a hard invariant (INV-001 through INV-005), not a convention.

Permitted log fields include: `prompt_hash`, `latency`, `provider`, `model`, `route`, `request_id`, capability metadata, and audit metadata. If you are adding a log field, verify it against the content safety invariants before committing.

---

## Adding a provider adapter

1. Write an ADR covering the adapter contract, fallback behaviour, and any new config surface.
2. Create `io_iii/providers/<provider>_provider.py` implementing the `Provider` protocol from `provider_contract.py`.
3. Add the provider to `providers.yaml` with `enabled: false` as the default.
4. Add tests in `tests/test_provider_<provider>.py`.
5. Update [docs/user-guide/MODELS.md](docs/user-guide/MODELS.md) with any hardware or setup requirements.

Do not modify `routing.py`, `engine.py`, or `telemetry.py`. These are frozen.

---

## Pull requests

Keep changes minimal and bounded. Reference the governing ADR in the PR description. Update documentation when behaviour or architecture changes. Preserve all passing invariants: a PR that causes new invariant failures will not be merged.
