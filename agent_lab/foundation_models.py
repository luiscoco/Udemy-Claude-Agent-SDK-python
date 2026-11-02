"""Lesson-specific inputs for the first SDK learning block."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OptionsInputs(Inputs):
    model: str | None = Field(default=None, min_length=1, max_length=100)
    system_mode: Literal["default", "custom", "preset"] = "default"
    system_text: str = Field(
        default="Teach using concise Python examples.", min_length=1, max_length=2000
    )
    partial_messages: bool = True
    omit_turn_limit: bool = False
    omit_budget_limit: bool = False


class ToolsInputs(Inputs):
    tool: Literal["Read", "Glob", "Grep", "Bash"] = "Read"
    permit_tool: bool = True


class PermissionInputs(Inputs):
    decision: Literal["deny", "allow", "update", "ask"] = "deny"
    target: Literal["draft.txt", "notes.txt"] = "draft.txt"
    content: str = Field(default="A permission-controlled lesson note.\n", max_length=2000)


class CalculatorInputs(Inputs):
    a: float = Field(default=19.0, ge=-1e6, le=1e6, allow_inf_nan=False)
    b: float = Field(default=23.0, ge=-1e6, le=1e6, allow_inf_nan=False)


class SessionInputs(Inputs):
    strategy: Literal["same-client", "resume", "fresh"] = "same-client"


class HookInputs(Inputs):
    pre_hook: bool = True
    post_hook: bool = True
    behavior: Literal["observe", "block", "rewrite"] = "observe"


class AgentInputs(Inputs):
    worker_tools: Literal["read-only", "none"] = "read-only"
    worker_model: Literal["inherit", "haiku", "sonnet"] = "inherit"


class PromptInputs(Inputs):
    variant: Literal["default", "custom", "preset", "boundary", "project"] = "preset"
    instruction: str = Field(
        default="Teach using concise Python examples.", min_length=1, max_length=2000
    )
    context: str = Field(default="The student is practising SDK configuration.", max_length=1000)


class StructuredInputs(Inputs):
    payload: dict[str, Any] = Field(
        default_factory=lambda: {
            "summary": "Host-validated example",
            "next_steps": ["Inspect the terminal result"],
        }
    )
    stop_experiment: Literal["interrupt", "abort"] = "interrupt"

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, allow_nan=False)) > 10000:
            raise ValueError("Use at most 10000 characters of structured JSON.")
        return value


INPUT_MODELS: dict[int, type[Inputs]] = {
    2: OptionsInputs,
    3: ToolsInputs,
    4: PermissionInputs,
    5: CalculatorInputs,
    6: SessionInputs,
    7: HookInputs,
    8: AgentInputs,
    9: PromptInputs,
    10: StructuredInputs,
}

SCENARIOS: dict[int, dict[str, str]] = {
    number: {
        "success": "Passing example",
        "missing-evidence": "Missing required evidence",
        "wrong-identity": "Mismatched identity",
    }
    for number in INPUT_MODELS
}
SCENARIOS[2]["limit-error"] = "Recorded limit error"
SCENARIOS[5].update(
    {
        "invalid-arguments": "Rejected handler arguments",
        "ambiguous-handler": "Ambiguous handler match",
    }
)
SCENARIOS[6]["fresh-session"] = "Fresh session comparison"
SCENARIOS[7]["missing-hook"] = "Missing post-use hook"
SCENARIOS[10].update(
    {"schema-error": "Rejected structured value", "stop-control": "Interrupt / abort comparison"}
)


def inputs(lesson_id: int, values: dict[str, Any]) -> Inputs:
    return INPUT_MODELS[lesson_id].model_validate(values)
