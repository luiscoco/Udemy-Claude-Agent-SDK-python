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


class SkillsInputs(Inputs):
    loading: Literal["invoke", "discovery", "preload"] = "invoke"
    discovery: Literal["project", "plugin"] = "project"
    visible: bool = True
    load_support: bool = False


class StreamingInputs(Inputs):
    interactive: bool = False
    queue_timing: Literal["immediate", "after-result"] = "immediate"
    runtime_control: Literal["none", "model", "permission"] = "none"
    max_messages: int = Field(default=2, ge=2, le=4)


class McpInputs(Inputs):
    transport: Literal["stdio", "http", "sdk"] = "sdk"
    tool: Literal["stock", "reserve"] = "reserve"
    sku: Literal["notebook", "pen"] = "notebook"
    quantity: int = Field(default=2, ge=1, le=5)
    enabled: bool = True
    lifecycle: Literal["none", "toggle", "reconnect"] = "none"


class UsageInputs(Inputs):
    omit_turn_limit: bool = False
    omit_budget_limit: bool = False
    task_tokens: int | None = Field(default=None, ge=1, le=100000)
    allow_agent: bool = False


class ThinkingInputs(Inputs):
    model: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    )
    thinking: Literal["disabled", "adaptive", "enabled"] = "adaptive"
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "medium"
    budget_tokens: int = Field(default=4000, ge=1024, le=16384)
    display: Literal["default", "summarized", "omitted"] = "default"
    comparison: Literal["none", "effort", "model", "thinking"] = "none"
    comparison_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "high"
    comparison_model: str = Field(
        default="sonnet", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    )
    comparison_thinking: Literal["disabled", "adaptive", "enabled"] = "disabled"
    authorize_comparison: bool = False


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
    11: SkillsInputs,
    12: StreamingInputs,
    13: McpInputs,
    14: ThinkingInputs,
    15: UsageInputs,
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
SCENARIOS[15].update({
    "missing-usage": "Missing final token counts",
    "invalid-usage": "Invalid final counters",
    "turn-limit": "Recorded turn limit stop",
    "budget-limit": "Recorded budget threshold stop",
    "interrupted": "Recorded interrupted usage run",
})
SCENARIOS[12]["interrupted"] = "Interrupted input queue"
SCENARIOS[13]["tool-error"] = "Inventory server rejects the reservation"
SCENARIOS[14].update(
    {
        "missing-effort": "Stop hook has unknown effort",
        "unsupported": "Recorded unsupported combination",
        "model-error": "Recorded model access error",
        "interrupted": "Recorded interrupted turn",
    }
)
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
