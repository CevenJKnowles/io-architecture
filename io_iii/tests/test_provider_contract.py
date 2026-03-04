from __future__ import annotations

import pytest

from io_iii.providers.null_provider import NullProvider
from io_iii.providers.provider_contract import Provider, ProviderError, ProviderResult


def test_null_provider_conforms_to_contract():
    p = NullProvider()
    assert isinstance(p, Provider)
    out = p.generate(model="any", prompt="hello")
    assert isinstance(out, str)

    res = p.run(mode="executor", route_id="executor", meta={})
    assert isinstance(res, ProviderResult)
    assert isinstance(res.message, str)
    assert isinstance(res.meta, dict)
    assert res.meta.get("provider") == "null"


def test_provider_error_shape():
    e = ProviderError("CODE", "details")
    assert "CODE" in str(e)
    assert "details" in str(e)
    assert e.code == "CODE"
    