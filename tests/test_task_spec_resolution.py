from io_iii.core.task_spec import TaskSpec


def test_task_spec_create_generates_id():
    spec = TaskSpec.create(
        mode="executor",
        prompt="Summarise this text.",
    )

    assert spec.task_spec_id.startswith("ts-")
    assert spec.mode == "executor"
    assert spec.prompt == "Summarise this text."
    assert spec.capabilities == []
    assert spec.metadata == {}


def test_task_spec_from_dict_round_trip():
    data = {
        "task_spec_id": "ts-abc123",
        "mode": "executor",
        "prompt": "Validate this JSON.",
        "capabilities": ["cap.validate_json_schema"],
        "metadata": {"source": "test"},
    }

    spec = TaskSpec.from_dict(data)

    assert spec.to_dict() == data


def test_task_spec_rejects_empty_mode():
    try:
        TaskSpec.create(mode="", prompt="Hello")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "mode" in str(exc)


def test_task_spec_rejects_empty_prompt():
    try:
        TaskSpec.create(mode="executor", prompt="")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "prompt" in str(exc)


def test_task_spec_rejects_invalid_capabilities_type():
    try:
        TaskSpec.create(
            mode="executor",
            prompt="Hello",
            capabilities="cap.echo_json",  # type: ignore[arg-type]
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "capabilities" in str(exc)