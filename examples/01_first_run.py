"""
examples/01_first_run.py: Minimal working example

Runs a single prompt through Io³ and prints the result.

Prerequisites:
  - Ollama running locally with at least one model pulled
  - routing_table.yaml configured for the 'executor' mode
  - content_release: true in runtime.yaml (needed to surface model output via Python API)
  - `pip install -e ".[dev]"` from repo root

Run from repo root:
  python examples/01_first_run.py
"""

import subprocess
import sys

# The simplest way to invoke Io³ is through the CLI.
# This is equivalent to running the command directly in your terminal.
result = subprocess.run(
    [
        sys.executable, "-m", "io_iii",
        "run", "executor",
        "--raw",
        "--prompt", "Explain deterministic routing in one sentence.",
    ],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print(result.stdout.strip())
else:
    # Io³ writes errors to stderr. Exit code 1 = execution error.
    print("Error:", result.stderr.strip(), file=sys.stderr)
    sys.exit(result.returncode)
