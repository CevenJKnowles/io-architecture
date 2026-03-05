from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from io_iii.core.capabilities import (
    Capability,
    CapabilityBounds,
    CapabilityCategory,
    CapabilityContext,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
)


@dataclass(frozen=True)
class EchoJsonSummaryCapability:
    """
    Reference capability: cap.echo_json

    Purpose:
    - Demonstrate end-to-end capability invocation (Phase 3 M3.9)
    - Stay content-safe by returning ONLY structural summary (not payload content)

    Output:
    {
      "summary": {
        "payload_bytes": int,
        "payload_type": str,
        "top_level_keys": int | None,
        "top_level_len": int | None
      }
    }
    """

    _spec: CapabilitySpec

    @property
    def spec(self) -> CapabilitySpec:
        return self._spec

    def invoke(self, ctx: CapabilityContext, payload: Mapping[str, Any]) -> CapabilityResult:
        # Structural summary only (no payload echo)
        try:
            payload_bytes = len(json.dumps(payload, ensure_ascii=False))
        except Exception:
            payload_bytes = len(str(payload))

        payload_type = type(payload).__name__
        top_level_keys = None
        top_level_len = None

        if isinstance(payload, Mapping):
            top_level_keys = len(payload.keys())
        elif isinstance(payload, (list, tuple, set)):
            top_level_len = len(payload)

        return CapabilityResult(
            ok=True,
            output={
                "summary": {
                    "payload_bytes": payload_bytes,
                    "payload_type": payload_type,
                    "top_level_keys": top_level_keys,
                    "top_level_len": top_level_len,
                }
            },
        )


@dataclass(frozen=True)
class JsonPrettyCapability:
    """Demonstration capability: cap.json_pretty

    Deterministically pretty-formats the provided JSON object.

    Output:
    {
      "pretty": "{
  ...
}"
    }

    Notes:
    - Output is content, but IO-III content logging remains disabled by default.
    - Metadata logging must never store the output.
    """

    _spec: CapabilitySpec

    @property
    def spec(self) -> CapabilitySpec:
        return self._spec

    def invoke(self, ctx: CapabilityContext, payload: Mapping[str, Any]) -> CapabilityResult:
        pretty = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        return CapabilityResult(ok=True, output={"pretty": pretty})


def _validate_json_schema_minimal(schema: Mapping[str, Any], data: Any) -> dict:
    """Minimal deterministic JSON Schema validator for demo purposes.

    Supported subset:
    - type: "object" | "string" | "integer"
    - required: [..]
    - properties: { name: {type, minimum} }
    - additionalProperties: false
    - minimum (for integer)

    Returns a structured, content-safe report:
    {
      "valid": bool,
      "errors": [{"path": str, "code": str, "detail": str}],
      "error_count": int,
      "error_codes": [str]
    }
    """
    errors: list[dict] = []

    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, Mapping):
            errors.append({"path": "", "code": "TYPE_MISMATCH", "detail": "Expected object"})
        else:
            required = schema.get("required", [])
            if isinstance(required, list):
                for key in required:
                    if isinstance(key, str) and key not in data:
                        errors.append({"path": f"/{key}", "code": "MISSING_REQUIRED", "detail": "Missing required field"})

            properties = schema.get("properties", {})
            if isinstance(properties, Mapping):
                for key, subschema in properties.items():
                    if not isinstance(key, str) or not isinstance(subschema, Mapping):
                        continue
                    if key not in data:
                        continue
                    value = data[key]
                    expected = subschema.get("type")

                    if expected == "string":
                        if not isinstance(value, str):
                            errors.append({"path": f"/{key}", "code": "TYPE_MISMATCH", "detail": "Expected string"})

                    elif expected == "integer":
                        # bool is a subclass of int; exclude it for schema type checks.
                        if not (isinstance(value, int) and not isinstance(value, bool)):
                            errors.append({"path": f"/{key}", "code": "TYPE_MISMATCH", "detail": "Expected integer"})
                        else:
                            minimum = subschema.get("minimum")
                            if isinstance(minimum, int) and value < minimum:
                                errors.append({"path": f"/{key}", "code": "MINIMUM_VIOLATION", "detail": "Value below minimum"})

            additional = schema.get("additionalProperties", True)
            if additional is False and isinstance(properties, Mapping):
                allowed = {k for k in properties.keys() if isinstance(k, str)}
                for key in data.keys():
                    if isinstance(key, str) and key not in allowed:
                        errors.append({"path": f"/{key}", "code": "ADDITIONAL_PROPERTY", "detail": "Additional property not allowed"})

    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append({"path": "", "code": "TYPE_MISMATCH", "detail": "Expected string"})

    elif schema_type == "integer":
        if not (isinstance(data, int) and not isinstance(data, bool)):
            errors.append({"path": "", "code": "TYPE_MISMATCH", "detail": "Expected integer"})
        else:
            minimum = schema.get("minimum")
            if isinstance(minimum, int) and data < minimum:
                errors.append({"path": "", "code": "MINIMUM_VIOLATION", "detail": "Value below minimum"})

    else:
        errors.append({"path": "", "code": "UNSUPPORTED_SCHEMA", "detail": "Unsupported schema type"})

    error_codes = [e["code"] for e in errors if isinstance(e.get("code"), str)]
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "error_count": len(errors),
        "error_codes": error_codes,
    }


@dataclass(frozen=True)
class ValidateJsonSchemaCapability:
    """Demonstration capability: cap.validate_json_schema

    Validates payload["data"] against payload["schema"] using a minimal JSON Schema subset.

    Output:
    {
      "valid": bool,
      "errors": [...],
      "error_count": int,
      "error_codes": [...]
    }
    """

    _spec: CapabilitySpec

    @property
    def spec(self) -> CapabilitySpec:
        return self._spec

    def invoke(self, ctx: CapabilityContext, payload: Mapping[str, Any]) -> CapabilityResult:
        schema = payload.get("schema")
        data = payload.get("data")

        if not isinstance(schema, Mapping):
            return CapabilityResult(
                ok=False,
                error_code="INVALID_SCHEMA",
                output={
                    "valid": False,
                    "errors": [
                        {"path": "/schema", "code": "INVALID_SCHEMA", "detail": "Schema must be an object"}
                    ],
                    "error_count": 1,
                    "error_codes": ["INVALID_SCHEMA"],
                },
            )

        report = _validate_json_schema_minimal(schema=schema, data=data)
        return CapabilityResult(ok=True, output=report)


def builtin_capabilities() -> list[Capability]:
    """Declared built-in capabilities shipped with the reference runtime."""

    echo_spec = CapabilitySpec(
        capability_id="cap.echo_json",
        version="1.0",
        category=CapabilityCategory.VALIDATION,
        bounds=CapabilityBounds(
            max_calls=1,
            timeout_ms=50,
            max_input_chars=4096,
            max_output_chars=1024,
        ),
        description="Return a content-safe structural summary of the provided JSON payload.",
    )

    json_pretty_spec = CapabilitySpec(
        capability_id="cap.json_pretty",
        version="1.0",
        category=CapabilityCategory.TRANSFORMATION,
        bounds=CapabilityBounds(
            max_calls=1,
            timeout_ms=50,
            max_input_chars=4096,
            max_output_chars=8192,
        ),
        description="Deterministically pretty-format the provided JSON object.",
    )

    validate_schema_spec = CapabilitySpec(
        capability_id="cap.validate_json_schema",
        version="1.0",
        category=CapabilityCategory.VALIDATION,
        bounds=CapabilityBounds(
            max_calls=1,
            timeout_ms=50,
            max_input_chars=8192,
            max_output_chars=4096,
        ),
        description="Validate JSON data against a minimal JSON Schema subset and return a structured report.",
    )

    return [
        EchoJsonSummaryCapability(_spec=echo_spec),
        JsonPrettyCapability(_spec=json_pretty_spec),
        ValidateJsonSchemaCapability(_spec=validate_schema_spec),
    ]


def builtin_registry() -> CapabilityRegistry:
    """Deterministic registry of built-in capabilities."""
    return CapabilityRegistry(builtin_capabilities())
