# io_iii/persona_contract.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

PERSONA_CONTRACT_VERSION = "v0.1"

# Default config path — resolves from this file to the project config directory.
_CONFIG_DIR = Path(__file__).parent.parent / "architecture" / "runtime" / "config"

_IDENTITY_DEFAULTS: Dict[str, Any] = {
    "name": "IO-III",
    "description": "",
    "style": "",
}


_USER_PROFILE_DEFAULTS: Dict[str, Any] = {
    "name": "",
    "role": "",
    "expertise": [],
    "preferences": {},
    "notes": "",
}


def load_user_profile() -> Dict[str, Any]:
    """
    Load the user profile block from user_profile.yaml.

    Returns a dict with keys: name, role, expertise, preferences, notes.
    Falls back to _USER_PROFILE_DEFAULTS on any read or parse failure.
    Never raises.
    """
    path = _CONFIG_DIR / "user_profile.yaml"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {**_USER_PROFILE_DEFAULTS, **(data.get("user") or {})}
    except Exception:
        return dict(_USER_PROFILE_DEFAULTS)


def load_identity() -> Dict[str, Any]:
    """
    Load the identity block from persona.yaml.

    Returns a dict with keys: name, description, style.
    Falls back to _IDENTITY_DEFAULTS on any read or parse failure so the
    system prompt is always well-formed. Never raises.
    """
    path = _CONFIG_DIR / "persona.yaml"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {**_IDENTITY_DEFAULTS, **(data.get("identity") or {})}
    except Exception:
        return dict(_IDENTITY_DEFAULTS)

EXECUTOR_PERSONA_CONTRACT = (
    "IO-III Persona Contract (Executor)\n"
    f"Version: {PERSONA_CONTRACT_VERSION}\n"
    "\n"
    "Role: Deterministic local execution engine.\n"
    "Priorities:\n"
    "- Deterministic routing (no self-routing)\n"
    "- Bounded execution (no recursion loops)\n"
    "- Single unified final output\n"
    "- Avoid introducing new facts unless explicitly requested\n"
    "- Prefer concise, technically precise language\n"
)

CHALLENGER_PERSONA_CONTRACT = (
    "IO-III Persona Contract (Challenger)\n"
    f"Version: {PERSONA_CONTRACT_VERSION}\n"
    "\n"
    "Role: Single-pass audit layer (ADR-008).\n"
    "Priorities:\n"
    "- Evaluate executor draft for policy/compliance risk\n"
    "- Highlight factual risk, contradictions, missing verification\n"
    "- Never rewrite the draft\n"
    "- Never introduce new facts\n"
    "- Respond in strict JSON only\n"
)
