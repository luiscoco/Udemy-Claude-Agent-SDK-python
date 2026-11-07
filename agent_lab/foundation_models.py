"""Lesson-specific inputs for the first SDK learning block."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StoreInputs(Inputs):
    action: Literal["commit", "interrupted", "resume", "durable-resume"] = "commit"
    flush: Literal["eager", "batched"] = "eager"
    enabled: bool = True
    fault: Literal["none", "reject-append", "delay-load"] = "none"


class SpawnInputs(Inputs):
    action: Literal["success", "stderr", "failed-launch", "timeout", "cancel"] = "success"
    location: Literal["machine-a", "machine-b"] = "machine-a"


class GateInputs(Inputs):
    action: Literal["allow", "edit", "remember", "deny", "interrupt", "malformed", "missing-effect", "manual"] = "allow"


class SuggestionInputs(Inputs):
    variant: Literal["enabled", "omitted", "disabled", "env-off", "setting-off", "env-on", "plan", "small", "cached", "uncached", "queued"] = "enabled"
    edited: bool = False


class ConfigRootInputs(Inputs):
    action: Literal["where", "takeover"] = "where"
    cwd: Literal["trusted", "branch", "docs"] = "branch"
    root: Literal["trusted", "branch", "omitted", "relative", "missing", "file"] = "trusted"
    sources: Literal["project-local", "none"] = "project-local"


class DropsInputs(Inputs):
    recover: bool = True


class ClientLifecycleInputs(Inputs):
    """Lesson 41 uses only fixed host prompts and a fixed comparison."""


class WebToolInputs(Inputs):
    action: Literal["basics", "fetch-lab", "injection", "guard", "research"] = "basics"
    page: Literal["page", "json", "redirect", "missing"] = "page"


class RemoteMcpInputs(Inputs):
    action: Literal["auth", "cache", "transports", "toolsets", "resources", "host-read", "live", "reconnect"] = "auth"
    step: Literal["tool", "resource", "rotate"] = "tool"
    transport: Literal["http", "sse"] = "http"
    resource: Literal["runbook", "incident", "logo", "widget", "order"] = "runbook"


class TelemetryInputs(Inputs):
    action: Literal["signals", "privacy", "tracing", "rich", "exporters", "collector"] = "signals"
    consent: bool = False


class CloudInputs(Inputs):
    action: Literal["catalog", "same", "auth", "models", "failures"] = "catalog"
    auth_case: Literal["sigv4", "bearer", "wif", "foundry", "gateway"] = "bearer"
    model_case: Literal["alias", "profile", "region"] = "profile"
    consent: bool = False


class CacheInputs(Inputs):
    action: Literal["anatomy", "switches", "breakers", "model-switch"] = "anatomy"
    ttl: Literal["5m", "1h", "off"] = "5m"
    prefix: Literal["stable", "changed", "tool", "dynamic", "short"] = "stable"
    policy: Literal["cap", "allow"] = "cap"
    consent: bool = False


class OrchestraInputs(Inputs):
    action: Literal["orchestrator", "hierarchy", "pipeline", "fanout", "evaluator"] = "orchestrator"
    limit: Literal[1, 2] = 2
    consent: bool = False


class HardeningInputs(Inputs):
    action: Literal["permissions", "lockdown", "secrets", "injection"] = "permissions"
    consent: bool = False


class HeadlessInputs(Inputs):
    action: Literal["headless", "ci", "limits", "deploy"] = "headless"
    consent: bool = False


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


class DeepHookInputs(Inputs):
    behavior: Literal["observe", "deny", "rewrite", "tool-error", "callback-error"] = "observe"
    matcher: Literal["Read", "Read|Glob", "Write|Edit"] = "Read"
    post_hook: bool = True
    failure_hook: bool = True
    prompt_hook: bool = True
    stop_hook: bool = True


class SlashCommandInputs(Inputs):
    source: Literal["project", "none"] = "project"
    template: Literal["summary", "quiz"] = "summary"


class ProjectMemoryInputs(Inputs):
    source: Literal["project", "none"] = "project"
    system_mode: Literal["preset", "custom"] = "preset"
    rule: Literal["alpha", "beta"] = "alpha"


class PluginInputs(Inputs):
    action: Literal["explain", "quiz", "skill"] = "explain"
    enabled: bool = True


class HarnessInputs(Inputs):
    proposal: Literal["valid", "duplicate", "cycle", "outside"] = "valid"
    approve: bool = True


class CompactionInputs(Inputs):
    limit: Literal[200, 600] = 600
    retain_summary: bool = True


class ControlInputs(Inputs):
    action: Literal["switch", "interrupt"] = "switch"
    target_model: Literal["current", "sonnet"] = "current"
    permission_mode: Literal["default", "plan"] = "plan"


class BackgroundInputs(Inputs):
    ending: Literal["cancel", "finish"] = "cancel"


class RetryInputs(Inputs):
    outcome: Literal["recover", "permanent", "exhausted"] = "recover"


class ImageInputs(Inputs):
    color: Literal["red", "blue"] = "red"


class TodoInputs(Inputs):
    sequence: Literal["valid", "skip", "parallel", "reopen"] = "valid"


class QuestionInputs(Inputs):
    answer: Literal["Concise", "Detailed"] = "Concise"


class PlanModeInputs(Inputs):
    proposal: Literal["valid", "duplicate"] = "valid"
    approve: bool = True


class ElicitationInputs(Inputs):
    action: Literal["accept", "decline", "cancel"] = "accept"


class StyleInputs(Inputs):
    style: Literal["teaching", "brief"] = "teaching"
    source: Literal["project", "none"] = "project"


class CatalogInputs(Inputs):
    action: Literal["inspect", "rename-tag", "fork", "delete"] = "inspect"
    page_size: int = Field(default=2, ge=1, le=10)
    offset: int = Field(default=0, ge=0, le=20)
    title: str = Field(default="Lesson 19 reviewed session", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    tag: Literal["reviewed", "practice"] = "reviewed"

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class SandboxInputs(Inputs):
    target: Literal["inside", "outside", "protected"] = "inside"
    native_required: bool = False


class CheckpointInputs(Inputs):
    checkpointing: bool = True
    replay_messages: bool = True
    action: Literal["rewind", "inspect"] = "rewind"
    replacement: Literal["short", "long"] = "short"


class SettingsInputs(Inputs):
    sources: Literal["none", "project", "project-local"] = "none"
    env_override: bool = True
    demo_value: Literal["alpha", "beta"] = "alpha"


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
    16: SettingsInputs,
    17: CheckpointInputs,
    18: SandboxInputs,
    19: CatalogInputs,
    20: DeepHookInputs,
    21: SlashCommandInputs,
    22: ProjectMemoryInputs,
    23: PluginInputs,
    24: HarnessInputs,
    25: CompactionInputs,
    26: ControlInputs,
    27: BackgroundInputs,
    28: RetryInputs,
    29: ImageInputs,
    30: TodoInputs,
    31: QuestionInputs,
    32: PlanModeInputs,
    33: ElicitationInputs,
    34: StyleInputs,
    35: StoreInputs,
    36: SpawnInputs,
    37: GateInputs,
    38: SuggestionInputs,
    39: ConfigRootInputs,
    40: DropsInputs,
    41: ClientLifecycleInputs,
    42: WebToolInputs,
    43: RemoteMcpInputs,
    44: TelemetryInputs,
    45: CloudInputs,
    46: CacheInputs,
    47: OrchestraInputs,
    48: HardeningInputs,
    49: HeadlessInputs,
}

SCENARIOS: dict[int, dict[str, str]] = {
    number: {
        "success": "Passing example",
        "missing-evidence": "Missing required evidence",
        "wrong-identity": "Mismatched identity",
    }
    for number in INPUT_MODELS
}
SCENARIOS[20].update({"missing-guard": "Missing host guard observation", "wrong-callback": "Unmatched hook call identity", "changed-fixture": "Changed Read-only fixture"})
SCENARIOS[47].update({"failed": "Worker failed", "cancel-worker": "Cancel north worker",
                      "missing-file": "Missing east file", "wrong-report": "Incorrect worker report"})
SCENARIOS[48].update({"failed": "Probe failed", "leaked": "Known canary leaked"})
SCENARIOS[49].update({"failed": "Process failed"})
SCENARIOS[21].update({"missing-command": "Command absent from SDK inventory", "missing-invocation": "No command marker in the response", "unmatched-read": "Read result identity differs"})
SCENARIOS[22].update({"wrong-answer": "Response does not match selected project rule", "changed-file": "Project instruction file changed", "auto-memory-file": "Recorded automatic memory file appeared"})
SCENARIOS[23].update({"missing-discovery": "Plugin command absent from SDK inventory", "wrong-marker": "Plugin template marker missing", "unmatched-skill": "Skill call/result identity differs"})
SCENARIOS[24].update({"missing-proposal": "Structured proposal absent", "wrong-worker": "Worker execution ledger mismatch"})
SCENARIOS[25].update({"missing-handler": "Bounded tool callback absent", "wrong-call": "Mismatched MCP call/result identity", "wrong-bound": "Tool result exceeded its bound"})
SCENARIOS[26].update({"missing-control": "Control acknowledgement absent", "wrong-model": "Observed model differs from target", "after-close": "Client accepted a query after disconnect"})
SCENARIOS[27].update({"missing-cleanup": "Watcher cleanup absent", "unawaited": "Watcher was not awaited", "not-running": "Watcher was not running during the SDK turn"})
SCENARIOS[28].update({"missing-handler": "Refund handler absent", "unmatched-result": "Refund call/result IDs differ", "duplicate-write": "Idempotency ledger applied twice", "wrong-stop": "Host retry decision does not match outcome"})
SCENARIOS[29].update({"wrong-mime": "MIME type differs from PNG bytes", "changed-file": "Owned image changed after encoding", "missing-yield": "Typed user image message absent", "wrong-answer": "Model color answer differs from image"})
SCENARIOS[30].update({"missing-hook": "Todo gate callback absent", "unmatched-call": "Todo call/result identity differs", "wrong-ledger": "Committed ledger differs from accepted transitions", "extra-post": "Rejected proposal was committed"})
SCENARIOS[31].update({"missing-callback": "Answer callback absent", "wrong-answer": "Callback returned a different answer", "changed-question": "Tool question differs from fixed input"})
SCENARIOS[32].update({"missing-proposal": "Structured plan absent", "missing-switch": "Approved mode switch missing", "unapproved-work": "Worker started without approval", "wrong-worker": "Unexpected worker execution"})
SCENARIOS[33].update({"missing-hook": "Elicitation callback absent", "wrong-action": "Host response action differs", "wrong-content": "Accepted content differs", "wrong-server": "Form request from another server"})
SCENARIOS[34].update({"wrong-answer": "Style marker differs", "changed-style": "Owned style file changed", "wrong-source": "Setting source differs from selection"})
SCENARIOS[35].update({"changed-host": "Host transcript differs", "wrong-answer": "Resumed word differs"})
SCENARIOS[36].update({"wrong-frame": "Child frame differs", "wrong-answer": "SDK marker differs"})
SCENARIOS[37].update({"rejected-input": "Gate refused an unrelated Write"})
SCENARIOS[38].update({"missing-suggestion": "No suggestion after a turn", "foreign-suggestion": "Suggestion belongs to another session", "failed-result": "One turn failed", "duplicate-result": "Duplicate turn result", "misordered-result": "Results out of order", "interrupted": "Input stream interrupted"})
SCENARIOS[39].update({"failed": "SDK result failed", "interrupted": "Probe was interrupted",
                      "wrong-hook": "Hook marker differs from selected configuration", "duplicate-hook": "Duplicate hook receipt",
                      "duplicate-result": "Duplicate terminal result", "missing-command": "Selected command absent from inventory",
                      "changed-fixture": "Configuration fixture hash changed", "wrong-effect": "Takeover proof file differs"})
SCENARIOS[40].update({"missing": "Guard refusal evidence missing", "foreign": "Fork identity differs",
                      "duplicate": "Duplicate event in comparison", "interrupted": "Comparison interrupted",
                      "tampered": "Source transcript hash changed"})
SCENARIOS[41].update({"missing": "Terminal result missing", "foreign": "Session identity differs",
                      "failed": "One turn failed"})
SCENARIOS[42].update({"missing": "Web tool result missing", "foreign": "Web tool result ID differs",
                      "failed": "Web tool result failed"})
SCENARIOS[43].update({"missing": "Remote MCP evidence missing", "foreign": "Remote MCP identity differs",
                      "failed": "Remote MCP call failed"})
SCENARIOS[44].update({"missing": "Telemetry export missing", "foreign": "Telemetry run identity differs",
                      "failed": "Collector did not close normally"})
SCENARIOS[45].update({"missing": "Cloud wire receipt missing", "foreign": "Cloud run identity differs",
                      "failed": "Proxy did not close normally"})
SCENARIOS[46].update({"missing": "Cache usage missing", "foreign": "Turn identity differs",
                      "failed": "One turn failed"})
SCENARIOS[19].update({"missing-catalog": "Missing SDK catalog observation", "wrong-effect": "Mismatched operation effect"})
SCENARIOS[18].update({"missing-decision": "Missing host policy decision", "wrong-result": "Unmatched Read result"})
SCENARIOS[17].update({"missing-checkpoint": "No replayed checkpoint UUID", "rewind-error": "Recorded rewind rejection", "no-effect": "Acknowledged rewind without restoration"})
SCENARIOS[16].update({"wrong-environment": "Mismatched child configuration", "unmatched-read": "Unmatched Read result"})
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
