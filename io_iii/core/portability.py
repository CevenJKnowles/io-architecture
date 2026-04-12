# io_iii/core/portability.py
#
# Portability validation pass — Phase 7 M7.4 / ADR-023 §6
#
# Confirms the runtime is correctly initialised before first execution.
# All failure summaries are content-safe: no model names, paths, or persona
# content appear in any check detail or failure message.

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    """
    Outcome of a single portability check.

    Content-safety contract:
    - `name`   — check identifier; safe to log
    - `passed` — boolean
    - `detail` — reason for failure; identifies the structural issue only;
                 never includes model names, file values, or persona content
    """
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class PortabilityReport:
    """
    Aggregated result of the full portability validation pass.

    Content-safety contract: all fields are safe to log or print.
    """
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def check_count(self) -> int:
        return len(self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)


# ---------------------------------------------------------------------------
# Required config filenames (ADR-023 §3.1)
# ---------------------------------------------------------------------------

_REQUIRED_FILES = [
    "providers.yaml",
    "routing_table.yaml",
    "memory_packs.yaml",
    "persona.yaml",
]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_required_files(config_dir: Path) -> List[CheckResult]:
    """Check 1 — required config files present and parseable (ADR-023 §6.2)."""
    results: List[CheckResult] = []
    for filename in _REQUIRED_FILES:
        path = config_dir / filename
        name = f"config_file_present:{filename}"
        if not path.exists():
            results.append(CheckResult(name=name, passed=False, detail=f"{filename} not found in config dir"))
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                results.append(CheckResult(name=name, passed=False, detail=f"{filename} is not a YAML mapping"))
                continue
        except Exception:
            results.append(CheckResult(name=name, passed=False, detail=f"{filename} could not be parsed as YAML"))
            continue
        results.append(CheckResult(name=name, passed=True))
    return results


def _check_provider_declared(config_dir: Path) -> CheckResult:
    """Check 2 — provider base_url declared and non-empty (ADR-023 §6.2)."""
    name = "provider_base_url_declared"
    path = config_dir / "providers.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="providers.yaml not found")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        providers = data.get("providers") or {}
        ollama = providers.get("ollama") or {}
        base_url = (ollama.get("base_url") or "").strip()
        if not base_url:
            return CheckResult(name=name, passed=False, detail="providers.ollama.base_url is empty or missing")
        return CheckResult(name=name, passed=True)
    except Exception:
        return CheckResult(name=name, passed=False, detail="providers.yaml could not be read")


def _check_model_name_declared(config_dir: Path) -> CheckResult:
    """Check 3 — at least one role has a non-empty model name (ADR-023 §6.2)."""
    name = "model_name_declared"
    path = config_dir / "routing_table.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="routing_table.yaml not found")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        routing_table = data.get("routing_table") or {}
        models: Dict[str, Any] = routing_table.get("models") or {}
        for role, role_cfg in models.items():
            if isinstance(role_cfg, dict):
                model_name = (role_cfg.get("name") or "").strip()
                if model_name:
                    return CheckResult(name=name, passed=True)
        return CheckResult(name=name, passed=False, detail="no role in routing_table.yaml has a non-empty model name")
    except Exception:
        return CheckResult(name=name, passed=False, detail="routing_table.yaml could not be read")


def _check_persona_present(config_dir: Path) -> CheckResult:
    """Check 4 — persona.yaml present and persona.name non-empty (ADR-023 §6.2)."""
    name = "persona_name_declared"
    path = config_dir / "persona.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="persona.yaml not found")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        persona = data.get("persona") or {}
        persona_name = (persona.get("name") or "").strip()
        if not persona_name:
            return CheckResult(name=name, passed=False, detail="persona.name is empty or missing in persona.yaml")
        return CheckResult(name=name, passed=True)
    except Exception:
        return CheckResult(name=name, passed=False, detail="persona.yaml could not be read")


def _check_storage_root_declared(config_dir: Path) -> CheckResult:
    """Check 5 — storage_root declared and non-empty (ADR-023 §6.2)."""
    name = "storage_root_declared"
    path = config_dir / "memory_packs.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="memory_packs.yaml not found")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        storage_root = (data.get("storage_root") or "").strip()
        if not storage_root:
            return CheckResult(name=name, passed=False, detail="storage_root is empty or missing in memory_packs.yaml")
        return CheckResult(name=name, passed=True)
    except Exception:
        return CheckResult(name=name, passed=False, detail="memory_packs.yaml could not be read")


def _check_storage_root_writable(config_dir: Path) -> CheckResult:
    """Check 6 — storage_root path exists and is writable (ADR-023 §6.2)."""
    name = "storage_root_writable"
    path = config_dir / "memory_packs.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="memory_packs.yaml not found; cannot resolve storage_root")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        storage_root_str = (data.get("storage_root") or "").strip()
        if not storage_root_str:
            return CheckResult(name=name, passed=False, detail="storage_root is empty; cannot check writability")

        # Resolve relative to config_dir's parent (repo root)
        storage_root = Path(storage_root_str)
        if not storage_root.is_absolute():
            storage_root = (config_dir.parent.parent.parent / storage_root_str).resolve()

        if not storage_root.exists():
            try:
                storage_root.mkdir(parents=True, exist_ok=True)
            except Exception:
                return CheckResult(name=name, passed=False, detail="storage_root does not exist and could not be created")

        if not os.access(storage_root, os.W_OK):
            return CheckResult(name=name, passed=False, detail="storage_root exists but is not writable")

        return CheckResult(name=name, passed=True)
    except Exception:
        return CheckResult(name=name, passed=False, detail="storage_root writability check failed unexpectedly")


def _check_constellation(config_dir: Path) -> CheckResult:
    """Check 7 — M5.3 constellation integrity guard passes (ADR-023 §6.2)."""
    name = "constellation_integrity"
    path = config_dir / "routing_table.yaml"
    if not path.exists():
        return CheckResult(name=name, passed=False, detail="routing_table.yaml not found; constellation check skipped")
    try:
        with path.open("r", encoding="utf-8") as f:
            routing_cfg = yaml.safe_load(f) or {}
        from io_iii.core.constellation import check_constellation
        check_constellation(routing_cfg)
        return CheckResult(name=name, passed=True)
    except ValueError as e:
        msg = str(e)
        # Strip the CONSTELLATION_DRIFT: prefix for the detail field; keep it content-safe
        detail = msg.split(":", 1)[1].strip() if ":" in msg else msg
        return CheckResult(name=name, passed=False, detail=f"constellation check failed: {detail}")
    except Exception:
        return CheckResult(name=name, passed=False, detail="constellation check failed unexpectedly")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_portability_checks(config_dir: Optional[Path] = None) -> PortabilityReport:
    """
    Run all portability validation checks and return a PortabilityReport.

    Does not raise on failure — callers inspect report.passed or report.failed_checks.

    Content-safety contract: all check details are safe to print or log.
    No model names, file values, or persona content appear in any result field.
    """
    from io_iii.config import default_config_dir
    cfg_dir = config_dir or default_config_dir()

    checks: List[CheckResult] = []

    # Check 1 — required files
    checks.extend(_check_required_files(cfg_dir))

    # Check 2 — provider base_url
    checks.append(_check_provider_declared(cfg_dir))

    # Check 3 — model name
    checks.append(_check_model_name_declared(cfg_dir))

    # Check 4 — persona name
    checks.append(_check_persona_present(cfg_dir))

    # Check 5 — storage root declared
    checks.append(_check_storage_root_declared(cfg_dir))

    # Check 6 — storage root writable
    checks.append(_check_storage_root_writable(cfg_dir))

    # Check 7 — constellation guard
    checks.append(_check_constellation(cfg_dir))

    return PortabilityReport(checks=checks)


def validate_portability(config_dir: Optional[Path] = None) -> PortabilityReport:
    """
    Run all portability checks and raise ValueError on any failure.

    Raises:
        ValueError: message begins with 'PORTABILITY_CHECK_FAILED:' followed by a
            content-safe summary of the first failed check name and its detail.

    Returns PortabilityReport on success (all checks passed).
    """
    report = run_portability_checks(config_dir)
    if not report.passed:
        failed = report.failed_checks[0]
        raise ValueError(
            f"PORTABILITY_CHECK_FAILED: check '{failed.name}' failed — {failed.detail}"
        )
    return report
