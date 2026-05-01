# Getting Started

This guide covers installation, first run, model configuration, the available modes, and common error messages.

---

## Prerequisites

- Python 3.11 or later
- [Ollama](https://ollama.com) installed and running locally
- At least one model pulled into Ollama (see [MODELS.md](MODELS.md))

---

## Installation

```bash
git clone https://github.com/CevenJKnowles/io-architecture.git
cd io-architecture
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the install:

```bash
python -m io_iii validate
python -m io_iii about
```

`validate` checks that your config directory is complete and readable. If it reports missing files, run `python -m io_iii init` to generate defaults.

---

## First run

```bash
python -m io_iii run executor --prompt "Explain deterministic routing in one sentence."
```

Add `--raw` to suppress metadata and print only the model response:

```bash
python -m io_iii run executor --raw --prompt "Explain deterministic routing."
```

Add `--audit` to run the challenger gate on the draft before output is released:

```bash
python -m io_iii run executor --audit --prompt "Draft a product announcement."
```

---

## Model configuration

Io³ routes every request through `architecture/runtime/config/routing_table.yaml`. Each mode maps to a specific model name. The name must exactly match what Ollama has installed.

Check what you have:

```bash
ollama list
```

Open `routing_table.yaml` and update each entry under `modes:` to match a model from that list. Example minimal setup using a single model for every mode:

```yaml
modes:
  executor:
    primary: "local:mistral:latest"
  challenger:
    primary: "local:mistral:latest"
  drafter:
    primary: "local:mistral:latest"
  fast:
    primary: "local:mistral:latest"
  data:
    primary: "local:mistral:latest"
```

See [MODELS.md](MODELS.md) for tested configurations by hardware tier and instructions for adding a new model.

---

## Enabling model output in the web UI and API

The HTTP API and web UI surface no model output by default; this is the content-safe baseline (ADR-026). To enable it, add or confirm this line in `architecture/runtime/config/runtime.yaml`:

```yaml
content_release: true
```

This is an operator opt-in. You accept responsibility for access control and log retention when this is enabled.

---

## Modes

Each mode maps to a different routing slot in `routing_table.yaml`. You choose a mode at invocation time; the runtime resolves exactly one provider and model.

**executor**: general single-turn execution. The default mode for `run`.

**challenger**: the audit gate model. Used internally when `--audit` is passed. Can also be invoked directly for standalone auditing.

**drafter**: optimised for long-form generation (reports, summaries, structured output).

**fast**: optimised for low-latency responses. Suitable for brief queries or interactive use.

**data**: optimised for structured data tasks (JSON extraction, tabular analysis, transformation).

**steward**: used in steward-mode sessions. The steward model evaluates session state at gate thresholds.

---

## Multi-turn sessions

Sessions maintain conversation history across turns and support human supervision via steward mode.

**Start a session:**

```bash
python -m io_iii session start --mode work
```

Copy the `session_id` UUID from the output.

**Continue:**

```bash
python -m io_iii session continue --session-id <uuid> --prompt "Follow-up question."
```

**Check status:**

```bash
python -m io_iii session status --session-id <uuid>
```

**Close:**

```bash
python -m io_iii session close --session-id <uuid>
```

In **steward mode**, the session pauses at configurable thresholds (step count, token budget, capability class). When paused, the CLI exits with code 3 and the next `session continue` prompts for approval. Configure thresholds in `runtime.yaml` under `steward_thresholds:`.

---

## Web UI

```bash
python -m io_iii serve                          # 127.0.0.1:8080
python -m io_iii serve --host 0.0.0.0 --port 9000
```

Open the address in a browser. Requires `content_release: true` in `runtime.yaml` to display model responses.

---

## Architecture validation

Run these after any config change:

```bash
python architecture/runtime/scripts/validate_invariants.py
pytest
python -m io_iii capabilities --json
```

---

## Common errors

**`ProviderError: PROVIDER_OLLAMA_FAILED: HTTP Error 404: Not Found`**
The model name in `routing_table.yaml` does not match any installed Ollama model. Run `ollama list` to see what is available, then update the relevant mode entry in the routing table.

**`PROVIDER_UNREACHABLE`**
Ollama is not running. Start it with `ollama serve` (or via your system service manager) and retry.

**`CONSTELLATION_DRIFT`**
Your config files are inconsistent: a model referenced in one config is absent from another. Run `python -m io_iii validate` to identify the mismatch.

**`PORTABILITY_CHECK_FAILED`**
A config file contains a local absolute path or a field that will not work on another machine. Run `python -m io_iii validate` for detail.

**`context_limit_chars` exceeded**
The assembled prompt exceeds the character ceiling in `runtime.yaml`. Raise `context_limit_chars` or reduce memory pack size.
