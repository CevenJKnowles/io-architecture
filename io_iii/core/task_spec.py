from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional
import uuid


def _ensure_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _ensure_string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    cleaned: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} entries must be non-empty strings")
        cleaned.append(item.strip())
    return cleaned


def _ensure_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping/object")
    return dict(value)


@dataclass(frozen=True)
class TaskSpec:
    """
    Declarative single-run execution contract for Phase 4.

    Properties:
    - serialisable
    - deterministic
    - bounded to one execution path
    - no loops
    - no branching
    - no planner semantics
    """

    task_spec_id: str
    mode: str
    prompt: str
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        mode: str,
        prompt: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        task_spec_id: Optional[str] = None,
    ) -> "TaskSpec":
        return cls(
            task_spec_id=task_spec_id or cls.new_id(),
            mode=_ensure_non_empty_string(mode, "mode"),
            prompt=_ensure_non_empty_string(prompt, "prompt"),
            capabilities=_ensure_string_list(capabilities, "capabilities"),
            metadata=_ensure_mapping(metadata, "metadata"),
        )

    @staticmethod
    def new_id() -> str:
        return f"ts-{uuid.uuid4().hex[:12]}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSpec":
        if not isinstance(data, Mapping):
            raise ValueError("TaskSpec input must be a mapping/object")

        return cls.create(
            task_spec_id=data.get("task_spec_id"),
            mode=data.get("mode"),
            prompt=data.get("prompt"),
            capabilities=data.get("capabilities"),
            metadata=data.get("metadata"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_spec_id": self.task_spec_id,
            "mode": self.mode,
            "prompt": self.prompt,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }