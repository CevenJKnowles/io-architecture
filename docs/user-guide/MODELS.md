# Model Configuration

This document covers tested configurations by hardware tier, how the routing table works, and how to add a new model.

---

## How Io³ maps modes to models

Every request specifies a mode (e.g. `executor`, `fast`, `data`). The routing layer resolves that mode to exactly one `provider:model` entry in `routing_table.yaml`. There is no dynamic selection, no fallback chain based on output, and no arbitration between models.

The relevant file is `architecture/runtime/config/routing_table.yaml`. Entries under `modes:` use the format `local:<ollama-model-name>`. The `local:` prefix maps to the Ollama provider adapter.

---

## Minimum single-model setup

If you only have one model pulled, point every mode at it:

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
  steward:
    primary: "local:mistral:latest"
```

Replace `mistral:latest` with any name from `ollama list`.

---

## Tested configurations

The configurations below have been tested against the invariant suite. Smaller models reduce VRAM demand but may produce weaker challenger audits.

### High-end (24 GB+ VRAM)

Tested on Nvidia RTX 4090 / RTX 3090.

| Mode | Model |
|---|---|
| executor | `qwen2.5:14b-instruct` |
| challenger | `qwen2.5:14b-instruct` |
| drafter | `qwen2.5:14b-instruct` |
| fast | `qwen2.5:7b-instruct` |
| data | `qwen2.5:14b-instruct` |
| steward | `qwen2.5:7b-instruct` |

### Mid-range (8–16 GB VRAM)

Tested on Nvidia RTX 3070 / Apple M2 Pro.

| Mode | Model |
|---|---|
| executor | `mistral:latest` |
| challenger | `mistral:latest` |
| drafter | `mistral:latest` |
| fast | `phi3:mini` |
| data | `mistral:latest` |
| steward | `phi3:mini` |

### CPU / low-memory (no GPU, 16 GB RAM)

Expect slower responses. The `fast` and `steward` modes matter most here.

| Mode | Model |
|---|---|
| executor | `phi3:mini` |
| challenger | `phi3:mini` |
| drafter | `phi3:mini` |
| fast | `phi3:mini` |
| data | `phi3:mini` |
| steward | `phi3:mini` |

---

## Pulling a model

```bash
ollama pull qwen2.5:14b-instruct
ollama pull mistral:latest
ollama pull phi3:mini
```

Confirm it is available:

```bash
ollama list
```

The name in the `ollama list` output is what you put in `routing_table.yaml`. If they do not match exactly, Io³ will return `PROVIDER_OLLAMA_FAILED: HTTP Error 404`.

---

## Adding a new model

1. Pull it: `ollama pull <model-name>`
2. Open `architecture/runtime/config/routing_table.yaml`
3. Update the mode(s) you want to use it for: `primary: "local:<model-name>"`
4. Run `python -m io_iii validate` to confirm the config is consistent
5. Run `pytest` to confirm no invariant regressions

No code changes are required. The routing table is the only file that needs updating.

---

## Cloud providers

`providers.yaml` lists OpenAI, Anthropic, and Google as entries. No adapter code exists for any of them in this release; they are stubs that raise `NotImplementedError`. Enabling them in `providers.yaml` without an adapter will produce a clear error at startup. Cloud adapter implementation is planned for Phase 11 (ADR-028).
