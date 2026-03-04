from __future__ import annotations

import pytest

from io_iii.core.capabilities import (
    Capability,
    CapabilityBounds,
    CapabilityCategory,
    CapabilityContext,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    default_registry,
)


class DummyCapability:
    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            capability_id="dummy.echo",
            version="v0",
            category=CapabilityCategory.TRANSFORMATION,
            description="Echoes structured payload (test-only).",
            bounds=CapabilityBounds(max_calls=1, timeout_ms=100, max_input_chars=1000, max_output_chars=1000),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

    def invoke(self, ctx: CapabilityContext, payload):
        return CapabilityResult(ok=True, output=dict(payload))


def test_default_registry_is_empty():
    reg = default_registry()
    assert reg.ids() == []
    assert reg.specs() == {}


def test_registry_register_and_get():
    reg = CapabilityRegistry()
    cap = DummyCapability()
    reg.register(cap)

    assert reg.has("dummy.echo") is True
    got = reg.get("dummy.echo")
    assert isinstance(got, DummyCapability)
    assert got.spec.capability_id == "dummy.echo"


def test_registry_rejects_duplicate_ids():
    reg = CapabilityRegistry([DummyCapability()])
    with pytest.raises(ValueError) as e:
        reg.register(DummyCapability())
    assert "CAPABILITY_ID_DUPLICATE" in str(e.value)


def test_registry_rejects_invalid_bounds():
    class BadBoundsCapability:
        @property
        def spec(self) -> CapabilitySpec:
            return CapabilitySpec(
                capability_id="bad.bounds",
                version="v0",
                category=CapabilityCategory.COMPUTATION,
                description="Invalid bounds (test-only).",
                bounds=CapabilityBounds(max_calls=0, timeout_ms=0, max_input_chars=0, max_output_chars=0),
            )

        def invoke(self, ctx: CapabilityContext, payload):
            return CapabilityResult(ok=True, output={})

    reg = CapabilityRegistry()
    with pytest.raises(ValueError) as e:
        reg.register(BadBoundsCapability())
    assert "CAPABILITY_BOUNDS_INVALID" in str(e.value)


def test_dummy_capability_invoke_contract():
    cap = DummyCapability()
    ctx = CapabilityContext(cfg=None, session_state=None, execution_context=None)

    res = cap.invoke(ctx, {"a": 1})
    assert isinstance(res, CapabilityResult)
    assert res.ok is True
    assert res.output == {"a": 1}
    