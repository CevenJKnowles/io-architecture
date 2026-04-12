"""
CLI commands: validate, init (Phase 7 M7.2 / M7.4 / ADR-023).
"""
from __future__ import annotations

from io_iii.core.portability import run_portability_checks

from ._shared import _get_cfg_dir, _print


def cmd_validate(args) -> int:
    """
    Run the portability validation pass (Phase 7 M7.4 / ADR-023 §6).

    Command surface:
        python -m io_iii validate

    Runs all portability checks and prints a content-safe summary.
    Returns 0 when all checks pass, 1 when any check fails.

    Content-safety contract: no model names, config values, or persona content
    appear in any output field.
    """
    cfg_dir = _get_cfg_dir(args)
    report = run_portability_checks(cfg_dir)

    check_results = [
        {"check": c.name, "passed": c.passed, "detail": c.detail if not c.passed else ""}
        for c in report.checks
    ]

    payload = {
        "status": "ok" if report.passed else "failed",
        "checks_total": report.check_count,
        "checks_passed": report.passed_count,
        "checks_failed": report.check_count - report.passed_count,
        "results": check_results,
    }

    _print(payload)
    return 0 if report.passed else 1


def cmd_init(args) -> int:
    """
    Guided initialisation surface (Phase 7 M7.2 / ADR-023 §4).

    Command surface:
        python -m io_iii init

    Displays the M7.1 required configuration surface, shows the presence state of
    each required file, then runs the portability validation pass (M7.4).
    Does not modify any structural artefact.

    Properties:
    - Read-only: inspects config files; never writes to them
    - Runs portability validation on completion
    - Produces a human-readable summary of what is configured and what remains
    """
    import sys

    cfg_dir = _get_cfg_dir(args)

    _required_files = [
        ("providers.yaml",          "Ollama base URL and provider enablement"),
        ("routing_table.yaml",      "Model name bindings per role"),
        ("memory_packs.yaml",       "Storage root path and memory pack definitions"),
        ("persona.yaml",            "Persona identity and mode definitions"),
    ]
    _optional_files = [
        ("memory_retrieval_policy.yaml", "Memory retrieval allowlists (optional — absence is safe)"),
        ("runtime.yaml",                 "Context limit override (optional — default 32000 chars)"),
    ]

    print("\nIO-III Initialisation Surface (ADR-023 §3)")
    print("=" * 52)
    print(f"Config directory: {cfg_dir}\n")

    print("Required configuration files:")
    any_missing = False
    for filename, purpose in _required_files:
        path = cfg_dir / filename
        status = "PRESENT" if path.exists() else "MISSING"
        if not path.exists():
            any_missing = True
        print(f"  [{status:7s}] {filename}")
        print(f"             {purpose}")

    print("\nOptional configuration files:")
    for filename, purpose in _optional_files:
        path = cfg_dir / filename
        status = "PRESENT" if path.exists() else "absent "
        print(f"  [{status:7s}] {filename}")
        print(f"             {purpose}")

    if any_missing:
        print("\nSetup instructions:")
        print("  1. Copy the template files from:")
        print(f"     {cfg_dir / 'templates'}")
        print("  2. Edit each required file — replace placeholder values with your own.")
        print("  3. Re-run: python -m io_iii init")
        print()

    print("\nRunning portability validation...")
    print("-" * 40)

    report = run_portability_checks(cfg_dir)

    for c in report.checks:
        icon = "PASS" if c.passed else "FAIL"
        line = f"  [{icon}] {c.name}"
        if not c.passed:
            line += f"\n         {c.detail}"
        print(line)

    print("-" * 40)
    if report.passed:
        print(f"Validation: PASSED ({report.passed_count}/{report.check_count} checks)")
        print("\nRuntime is correctly initialised. Run a session with:")
        print("  python -m io_iii run executor --prompt \"your prompt here\"")
        print("  python -m io_iii runbook architecture/runtime/config/templates/chat_session.json")
    else:
        failed_names = [c.name for c in report.failed_checks]
        print(f"Validation: FAILED ({report.passed_count}/{report.check_count} checks passed)")
        print(f"Failed checks: {', '.join(failed_names)}")
        print("\nResolve the issues listed above and re-run: python -m io_iii init")
    print()

    return 0 if report.passed else 1
