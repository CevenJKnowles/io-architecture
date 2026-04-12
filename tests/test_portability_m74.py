"""
test_portability_m74.py — Phase 7 M7.4 portability validation tests (ADR-023 §6).

Verifies:

  Unit — run_portability_checks
  - returns a PortabilityReport
  - all checks pass on a fully configured temp config dir
  - missing providers.yaml → config_file_present:providers.yaml fails
  - missing routing_table.yaml → config_file_present:routing_table.yaml fails
  - missing memory_packs.yaml → config_file_present:memory_packs.yaml fails
  - missing persona.yaml → config_file_present:persona.yaml fails
  - empty providers.ollama.base_url → provider_base_url_declared fails
  - no models with name in routing_table → model_name_declared fails
  - empty persona.name → persona_name_declared fails
  - missing storage_root value → storage_root_declared fails
  - constellation collapse (executor == challenger) → constellation_integrity fails

  Unit — validate_portability
  - raises ValueError with PORTABILITY_CHECK_FAILED on first failure
  - returns report when all checks pass

  Content safety
  - no check detail contains model names or persona content
  - PortabilityReport fields are all safe to print

  CLI — cmd_validate
  - returns 0 when all checks pass
  - returns 1 when a check fails

  CLI — cmd_init
  - returns 0 when all checks pass
  - returns 1 when a check fails
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

import yaml

from io_iii.core.portability import (
    PortabilityReport,
    CheckResult,
    run_portability_checks,
    validate_portability,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROVIDERS_YAML = {
    "schema": "io-iii-providers",
    "version": "v1.0",
    "providers": {
        "ollama": {
            "enabled": True,
            "base_url": "http://localhost:11434",
        }
    },
    "policies": {
        "allow_implicit_cloud_fallback": False,
    },
}

_ROUTING_TABLE_YAML = {
    "routing_table": {
        "rules": {"selection_method": "mode"},
        "models": {
            "reasoning": {"provider": "ollama", "name": "model-a"},
        },
        "modes": {
            "executor":   {"primary": "local:model-a", "secondary": "local:model-b"},
            "explorer":   {"primary": "local:model-a", "secondary": "local:model-b"},
            "challenger": {"primary": "local:model-b", "secondary": "local:model-b"},
            "draft":      {"primary": "local:model-b", "secondary": "local:model-b"},
            "fast":       {"primary": "local:model-b", "secondary": "local:model-b"},
        },
    }
}

_MEMORY_PACKS_YAML = {
    "schema": "io-iii-memory-packs",
    "version": "v1.0",
    "storage_root": "./memory_store",
    "packs": [],
}

_PERSONA_YAML = {
    "schema": "io-iii-persona",
    "version": "v1.0",
    "persona": {
        "name": "test-user",
        "version": "1.0",
        "modes": [
            {
                "name": "executor",
                "role": "executor",
                "audit_enabled": True,
                "contract": "Test executor contract.",
            }
        ],
    },
}


def _write_config(tmp_path: Path, files: dict) -> Path:
    """Write a set of YAML config files to tmp_path and return it."""
    for filename, content in files.items():
        path = tmp_path / filename
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(content, f)
    return tmp_path


def _full_config(tmp_path: Path) -> Path:
    """Write a complete valid config set to tmp_path."""
    return _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })


# ---------------------------------------------------------------------------
# PortabilityReport unit tests
# ---------------------------------------------------------------------------

def test_portability_report_passed_when_all_checks_pass():
    report = PortabilityReport(checks=[
        CheckResult(name="a", passed=True),
        CheckResult(name="b", passed=True),
    ])
    assert report.passed is True
    assert report.failed_checks == []


def test_portability_report_failed_when_any_check_fails():
    report = PortabilityReport(checks=[
        CheckResult(name="a", passed=True),
        CheckResult(name="b", passed=False, detail="missing"),
    ])
    assert report.passed is False
    assert len(report.failed_checks) == 1
    assert report.failed_checks[0].name == "b"


def test_portability_report_counts():
    report = PortabilityReport(checks=[
        CheckResult(name="a", passed=True),
        CheckResult(name="b", passed=False, detail="x"),
        CheckResult(name="c", passed=True),
    ])
    assert report.check_count == 3
    assert report.passed_count == 2


# ---------------------------------------------------------------------------
# run_portability_checks — all pass
# ---------------------------------------------------------------------------

def test_all_checks_pass_on_valid_config(tmp_path):
    cfg_dir = _full_config(tmp_path)
    report = run_portability_checks(cfg_dir)
    failed = [(c.name, c.detail) for c in report.failed_checks]
    assert report.passed, f"Expected all checks to pass; failed: {failed}"


# ---------------------------------------------------------------------------
# run_portability_checks — missing required files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_file", [
    "providers.yaml",
    "routing_table.yaml",
    "memory_packs.yaml",
    "persona.yaml",
])
def test_missing_required_file_fails(tmp_path, missing_file):
    files = {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    }
    del files[missing_file]
    cfg_dir = _write_config(tmp_path, files)
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    failed_names = [c.name for c in report.failed_checks]
    assert f"config_file_present:{missing_file}" in failed_names


# ---------------------------------------------------------------------------
# run_portability_checks — provider base_url
# ---------------------------------------------------------------------------

def test_empty_provider_base_url_fails(tmp_path):
    providers = {
        "providers": {"ollama": {"enabled": True, "base_url": ""}},
        "policies": {"allow_implicit_cloud_fallback": False},
    }
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": providers,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "provider_base_url_declared" for c in report.failed_checks)


def test_missing_provider_key_fails(tmp_path):
    providers = {"providers": {}, "policies": {}}
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": providers,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "provider_base_url_declared" for c in report.failed_checks)


# ---------------------------------------------------------------------------
# run_portability_checks — model name
# ---------------------------------------------------------------------------

def test_no_model_name_fails(tmp_path):
    routing = {
        "routing_table": {
            "models": {"reasoning": {"provider": "ollama", "name": ""}},
            "modes": {
                "executor":   {"primary": "local:m", "secondary": "local:m"},
                "challenger": {"primary": "local:n", "secondary": "local:n"},
            },
        }
    }
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": routing,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "model_name_declared" for c in report.failed_checks)


# ---------------------------------------------------------------------------
# run_portability_checks — persona name
# ---------------------------------------------------------------------------

def test_empty_persona_name_fails(tmp_path):
    persona = {"persona": {"name": "", "version": "1.0", "modes": []}}
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": persona,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "persona_name_declared" for c in report.failed_checks)


# ---------------------------------------------------------------------------
# run_portability_checks — storage root
# ---------------------------------------------------------------------------

def test_missing_storage_root_value_fails(tmp_path):
    packs = {"schema": "io-iii-memory-packs", "version": "v1.0", "storage_root": "", "packs": []}
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": packs,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "storage_root_declared" for c in report.failed_checks)


def test_storage_root_writable_check_passes_when_dir_creatable(tmp_path):
    # Point storage_root at a subdirectory that doesn't exist yet
    store_dir = tmp_path / "store"
    cfg_subdir = tmp_path / "config"
    cfg_subdir.mkdir()
    packs = {"storage_root": str(store_dir), "packs": []}
    cfg_dir = _write_config(cfg_subdir, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": _ROUTING_TABLE_YAML,
        "memory_packs.yaml": packs,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    writable_check = next((c for c in report.checks if c.name == "storage_root_writable"), None)
    assert writable_check is not None
    assert writable_check.passed, writable_check.detail


# ---------------------------------------------------------------------------
# run_portability_checks — constellation integrity
# ---------------------------------------------------------------------------

def test_constellation_collapse_fails(tmp_path):
    # executor and challenger share the same model → constellation drift
    routing = {
        "routing_table": {
            "models": {"reasoning": {"provider": "ollama", "name": "model-a"}},
            "modes": {
                "executor":   {"primary": "local:same-model", "secondary": "local:other"},
                "challenger": {"primary": "local:same-model", "secondary": "local:other"},
                "explorer":   {"primary": "local:other", "secondary": "local:other"},
                "draft":      {"primary": "local:other", "secondary": "local:other"},
                "fast":       {"primary": "local:other", "secondary": "local:other"},
            },
        }
    }
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": routing,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    assert not report.passed
    assert any(c.name == "constellation_integrity" for c in report.failed_checks)


# ---------------------------------------------------------------------------
# validate_portability
# ---------------------------------------------------------------------------

def test_validate_portability_raises_on_failure(tmp_path):
    # No config files at all
    with pytest.raises(ValueError) as exc_info:
        validate_portability(tmp_path)
    assert "PORTABILITY_CHECK_FAILED" in str(exc_info.value)


def test_validate_portability_returns_report_on_success(tmp_path):
    cfg_dir = _full_config(tmp_path)
    report = validate_portability(cfg_dir)
    assert isinstance(report, PortabilityReport)
    assert report.passed


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------

def test_check_details_contain_no_model_names(tmp_path):
    # Use a routing table with recognisable model names; they must not leak into details
    routing = {
        "routing_table": {
            "models": {"reasoning": {"provider": "ollama", "name": ""}},
            "modes": {
                "executor":   {"primary": "local:qwen2.5:14b-instruct", "secondary": "local:mistral:latest"},
                "challenger": {"primary": "local:deepseek-r1:latest",   "secondary": "local:deepseek-r1:latest"},
                "explorer":   {"primary": "local:qwen2.5:14b-instruct", "secondary": "local:qwen3:8b"},
                "draft":      {"primary": "local:qwen3:8b",             "secondary": "local:qwen3:8b"},
                "fast":       {"primary": "local:mistral:latest",       "secondary": "local:qwen3:8b"},
            },
        }
    }
    cfg_dir = _write_config(tmp_path, {
        "providers.yaml": _PROVIDERS_YAML,
        "routing_table.yaml": routing,
        "memory_packs.yaml": _MEMORY_PACKS_YAML,
        "persona.yaml": _PERSONA_YAML,
    })
    report = run_portability_checks(cfg_dir)
    sensitive_terms = ["qwen2.5", "14b-instruct", "deepseek", "mistral", "qwen3", "gemma", "llama"]
    for check in report.checks:
        for term in sensitive_terms:
            assert term not in check.detail, (
                f"Check '{check.name}' detail leaks model name '{term}': {check.detail!r}"
            )


def test_check_result_fields_are_safe_to_log():
    result = CheckResult(name="some_check", passed=False, detail="field is empty or missing")
    assert isinstance(result.name, str)
    assert isinstance(result.passed, bool)
    assert isinstance(result.detail, str)


# ---------------------------------------------------------------------------
# CLI — cmd_validate
# ---------------------------------------------------------------------------

def test_cmd_validate_returns_0_on_valid_config(tmp_path):
    from io_iii.cli import cmd_validate

    cfg_dir = _full_config(tmp_path)

    class Args:
        config_dir = str(cfg_dir)

    result = cmd_validate(Args())
    assert result == 0


def test_cmd_validate_returns_1_on_invalid_config(tmp_path):
    from io_iii.cli import cmd_validate

    class Args:
        config_dir = str(tmp_path)  # empty dir — all required files missing

    result = cmd_validate(Args())
    assert result == 1


# ---------------------------------------------------------------------------
# CLI — cmd_init
# ---------------------------------------------------------------------------

def test_cmd_init_returns_0_on_valid_config(tmp_path, capsys):
    from io_iii.cli import cmd_init

    cfg_dir = _full_config(tmp_path)

    class Args:
        config_dir = str(cfg_dir)

    result = cmd_init(Args())
    assert result == 0
    out = capsys.readouterr().out
    assert "PASSED" in out


def test_cmd_init_returns_1_on_missing_config(tmp_path, capsys):
    from io_iii.cli import cmd_init

    class Args:
        config_dir = str(tmp_path)  # empty dir

    result = cmd_init(Args())
    assert result == 1
    out = capsys.readouterr().out
    assert "FAILED" in out


def test_cmd_init_output_contains_no_model_names(tmp_path, capsys):
    from io_iii.cli import cmd_init

    cfg_dir = _full_config(tmp_path)

    class Args:
        config_dir = str(cfg_dir)

    cmd_init(Args())
    out = capsys.readouterr().out
    # "llama" is excluded — it is a substring of "Ollama" (provider name), which is
    # legitimately present in the init output as a label. Check specific model names instead.
    sensitive_terms = ["qwen", "deepseek", "mistral", "gemma", "llama3", "ministral"]
    for term in sensitive_terms:
        assert term not in out.lower(), (
            f"cmd_init output leaks model name '{term}'"
        )
