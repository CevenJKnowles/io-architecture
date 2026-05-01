"""
examples/04_runbook.py: Two-step runbook with checkpoint

A runbook is an ordered, bounded list of TaskSpec steps. Each step is
deterministic and independently replayable. If execution stops partway
through (network error, steward pause), you can resume from the last
successful checkpoint.

This example defines a two-step runbook via the CLI's runbook subcommand.
The runtime executes both steps sequentially and writes a checkpoint after
each one.

Prerequisites: Ollama running with the 'executor' mode configured.

Run from repo root:
  python examples/04_runbook.py
"""

import json
import subprocess
import sys
import tempfile
import pathlib

# Define the runbook as a YAML file.
# Each step is a TaskSpec: a mode + prompt + optional capabilities.
# The runbook has a hard step ceiling of 20 (RUNBOOK_MAX_STEPS).
RUNBOOK_YAML = """\
runbook_id: "example-runbook-01"
steps:
  - task_spec_id: "step-01"
    mode: executor
    prompt: "In one sentence, what is the main benefit of deterministic routing?"
  - task_spec_id: "step-02"
    mode: executor
    prompt: "In one sentence, what is the main risk of non-deterministic routing?"
"""

# Write the runbook to a temporary file to pass to the CLI.
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".yaml", delete=False, prefix="io3_runbook_"
) as f:
    f.write(RUNBOOK_YAML)
    runbook_path = f.name

print(f"Runbook written to: {runbook_path}")
print("Running two-step runbook...\n")

result = subprocess.run(
    [
        sys.executable, "-m", "io_iii",
        "runbook", "run",
        "--file", runbook_path,
        "--output", "json",
    ],
    capture_output=True,
    text=True,
)

# Clean up the temp file.
pathlib.Path(runbook_path).unlink(missing_ok=True)

if result.returncode != 0:
    print("Error:", result.stderr.strip(), file=sys.stderr)
    sys.exit(result.returncode)

data = json.loads(result.stdout)

print("=== Runbook result ===")
print(f"  Runbook ID   : {data.get('runbook_id', '(not set)')}")
print(f"  Steps run    : {data.get('steps_completed', '(not set)')}")
print(f"  Status       : {data.get('status', '(not set)')}")

# Each step result is logged structurally. Content is gated by content_release.
for i, step in enumerate(data.get("steps", []), start=1):
    print(f"\n  Step {i}: {step.get('task_spec_id', '?')}")
    print(f"    Mode     : {step.get('mode', '?')}")
    print(f"    Provider : {step.get('provider', '?')}")
    if step.get("response"):
        print(f"    Response : {step['response']}")
