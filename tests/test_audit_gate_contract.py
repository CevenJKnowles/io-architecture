import types

import io_iii.cli as cli


class FakeProvider:
    """
    Deterministic provider stub:
    - 1st generate() call returns an executor draft
    - 2nd generate() call returns a revised final answer
    """
    def __init__(self):
        self.calls = []

    def generate(self, model: str, prompt: str) -> str:
        self.calls.append({"model": model, "prompt": prompt})
        if len(self.calls) == 1:
            return "DRAFT: Berlin is nice."
        return "FINAL: Berlin is the capital of Germany."


def test_audit_and_revision_are_bounded(monkeypatch, capsys):
    # --- Arrange: patch config loader and routing so cmd_run is fully local/deterministic

    fake_cfg = types.SimpleNamespace(
        config_dir=".",
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
    )

    def fake_load(_cfg_dir):
        return fake_cfg

    def fake_default_dir():
        return "."

    monkeypatch.setattr(cli, "load_io3_config", fake_load)
    monkeypatch.setattr(cli, "default_config_dir", fake_default_dir)

    # Force deterministic route resolution to ollama/qwen
    fake_selection = types.SimpleNamespace(
        mode="executor",
        primary_target="local:qwen3:8b",
        secondary_target=None,
        selected_target="local:qwen3:8b",
        selected_provider="ollama",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )

    def fake_resolve_route(*args, **kwargs):
        return fake_selection

    monkeypatch.setattr(cli, "resolve_route", fake_resolve_route)

    # Patch _parse_target to return the model name expected by cmd_run
    def fake_parse_target(_target):
        return ("local", "qwen3:8b")

    monkeypatch.setattr(cli, "_parse_target", fake_parse_target, raising=False)

    # Patch provider factory to return our fake provider
    fake_provider = FakeProvider()

    class FakeOllamaProvider:
        @staticmethod
        def from_config(_providers_cfg):
            return fake_provider

    monkeypatch.setattr(cli, "OllamaProvider", FakeOllamaProvider)

    # Patch challenger to always demand a single revision (needs_work)
    challenger_calls = {"n": 0}

    def fake_run_challenger(_cfg, _prompt, _draft):
        challenger_calls["n"] += 1
        return {"verdict": "needs_work", "issues": ["x"], "high_risk_claims": [], "suggested_fixes": []}

    monkeypatch.setattr(cli, "_run_challenger", fake_run_challenger)

    # --- Act: run cmd_run with audit enabled
    args = types.SimpleNamespace(mode="executor", prompt="State 3 facts about Berlin.", audit=True, config_dir=None)
    rc = cli.cmd_run(args)
    assert rc == 0

    captured = capsys.readouterr().out

    # --- Assert: bounded passes
    assert challenger_calls["n"] == 1, "Challenger must run at most once"
    assert len(fake_provider.calls) == 2, "Provider.generate should be called exactly twice (draft + single revision)"

    # --- Assert: challenger content does not leak into final message
    # The final output is JSON printed by cli._print, so we can string-check safely.
    assert "CHALLENGER_FEEDBACK" not in captured
    assert '"audit_meta"' in captured
    assert '"audit_used": true' in captured
    assert '"audit_verdict": "needs_work"' in captured