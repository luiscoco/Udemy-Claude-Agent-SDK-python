"""Validated contracts shared by the browser, API and command-line lessons."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline", "live"] = "offline"
    prompt: str = Field(default="", max_length=10000)
    follow_up: str = Field(
        default="Summarize your previous answer in one sentence.", max_length=2000
    )
    max_turns: int = Field(default=4, ge=1, le=12)
    max_budget_usd: float = Field(default=0.10, gt=0, le=1, allow_inf_nan=False)
    scenario: str = Field(default="success", min_length=1, max_length=40)
    lesson_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt", "follow_up")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QueryRunRequest(RunRequest):
    """Lesson 1's bounded request; other lessons keep their own limits."""

    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(
        default="Explain what an agent loop is in two sentences.", min_length=1, max_length=10000
    )
    max_turns: int = Field(default=1, ge=1, le=1)
    max_budget_usd: float = Field(default=0.05, gt=0, le=0.05, allow_inf_nan=False)
    scenario: Literal["success", "error", "missing-result"] = "success"

    @field_validator("prompt", mode="before")
    @classmethod
    def nonempty_prompt(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Enter a nonempty prompt for lesson 1.")
        return value


class FoundationRunRequest(RunRequest):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(min_length=1, max_length=10000)

    @field_validator("prompt", "follow_up", mode="before")
    @classmethod
    def trim(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def lesson_request(lesson_id: int, value: RunRequest | dict[str, Any]) -> RunRequest:
    """Validate before creating a task; omitted fields get the lesson's defaults."""
    data = value.model_dump(exclude_unset=True) if isinstance(value, RunRequest) else value
    parsed: RunRequest
    if lesson_id == 50:
        from agent_lab.curriculum import get_lesson

        selected = dict(data)
        selected.setdefault("prompt", get_lesson(50).prompt)
        parsed = FoundationRunRequest.model_validate(selected)
        allowed = {"customer", "intent", "conversation_id", "approval"}
        if set(parsed.lesson_options) - allowed:
            raise LessonError("Unknown Lesson 50 desk option.")
        options = {"customer": "ada", "intent": "orders", "conversation_id": None,
                   "approval": "deny"} | parsed.lesson_options
        if (not isinstance(options["customer"], str) or options["customer"] not in {"ada", "bo"} or
                not isinstance(options["intent"], str) or options["intent"] not in {"orders", "ticket", "refund"} or
                not isinstance(options["approval"], str) or options["approval"] not in {"approve", "deny"}):
            raise LessonError("Choose a fixed synthetic customer, intent and approval.")
        if not 1 <= len(parsed.prompt) <= 500:
            raise LessonError("The support message must be 1 to 500 characters.")
        if options["conversation_id"] is not None:
            import uuid

            try:
                options["conversation_id"] = str(uuid.UUID(options["conversation_id"]))
            except (TypeError, ValueError) as exc:
                raise LessonError("Choose a valid conversation UUID.") from exc
        if parsed.scenario not in {"success", "missing", "foreign", "failed"} or (parsed.mode == "live" and parsed.scenario != "success"):
            raise LessonError("Choose a Lesson 50 scenario; live requires success.")
        parsed.lesson_options = options
        return parsed
    if lesson_id == 51:
        from agent_lab.curriculum import get_lesson
        from agent_lab.offline_lab import SuiteInput

        selected = dict(data)
        selected.setdefault("prompt", get_lesson(51).prompt)
        parsed = FoundationRunRequest.model_validate(selected)
        if parsed.mode != "offline" or parsed.scenario != "success":
            raise LessonError("Lesson 51 is an offline-only host testing lab.")
        parsed.lesson_options = SuiteInput.model_validate(parsed.lesson_options).model_dump()
        return parsed
    if 2 <= lesson_id <= 49:
        from agent_lab.curriculum import get_lesson
        from agent_lab.foundation_models import SCENARIOS, inputs

        data = dict(data)
        data.setdefault("prompt", get_lesson(lesson_id).prompt)
        parsed = FoundationRunRequest.model_validate(data)
        parsed.lesson_options = inputs(lesson_id, parsed.lesson_options).model_dump()
        if lesson_id == 14 and parsed.mode == "live" and parsed.lesson_options["comparison"] != "none" and not parsed.lesson_options["authorize_comparison"]:
            raise LessonError("Authorize both paid comparison lanes explicitly, or choose a single lane.")
        if parsed.scenario not in SCENARIOS[lesson_id]:
            raise LessonError("Choose a scenario offered by this lesson.")
        if parsed.mode == "live" and parsed.scenario != "success":
            raise LessonError("Recorded negative scenarios are offline experiments only.")
        if lesson_id == 22 and parsed.prompt != get_lesson(22).prompt:
            raise LessonError("Lesson 22 uses the fixed memory comparison question; restore its example prompt.")
        if lesson_id == 23 and parsed.prompt != get_lesson(23).prompt:
            raise LessonError("Lesson 23 uses fixed plugin prompts; restore its example prompt.")
        if lesson_id == 23 and parsed.lesson_options["action"] == "skill" and not parsed.lesson_options["enabled"]:
            raise LessonError("Select an enabled plugin for the Skill invocation.")
        if lesson_id == 24 and parsed.prompt != get_lesson(24).prompt:
            raise LessonError("Lesson 24 uses fixed proposal prompts; restore its example prompt.")
        if lesson_id == 25 and parsed.prompt != get_lesson(25).prompt:
            raise LessonError("Lesson 25 uses a fixed bounded-log prompt; restore its example prompt.")
        if lesson_id == 26 and parsed.prompt != get_lesson(26).prompt:
            raise LessonError("Lesson 26 uses fixed control-method prompts; restore its example prompt.")
        if lesson_id == 27 and parsed.prompt != get_lesson(27).prompt:
            raise LessonError("Lesson 27 uses a fixed background-task prompt; restore its example prompt.")
        if lesson_id == 28 and parsed.prompt != get_lesson(28).prompt:
            raise LessonError("Lesson 28 uses a fixed refund retry prompt; restore its example prompt.")
        if lesson_id == 29 and parsed.prompt != get_lesson(29).prompt:
            raise LessonError("Lesson 29 uses a fixed image question; restore its example prompt.")
        if lesson_id == 30 and parsed.prompt != get_lesson(30).prompt:
            raise LessonError("Lesson 30 uses fixed TodoWrite proposals; restore its example prompt.")
        if lesson_id == 31 and parsed.prompt != get_lesson(31).prompt:
            raise LessonError("Lesson 31 uses a fixed question; restore its example prompt.")
        if lesson_id == 32 and parsed.prompt != get_lesson(32).prompt:
            raise LessonError("Lesson 32 uses fixed plan proposals; restore its example prompt.")
        if lesson_id == 33 and parsed.prompt != get_lesson(33).prompt:
            raise LessonError("Lesson 33 uses a fixed MCP booking request; restore its example prompt.")
        if lesson_id == 34 and parsed.prompt != get_lesson(34).prompt:
            raise LessonError("Lesson 34 uses a fixed output-style comparison; restore its example prompt.")
        if lesson_id == 35 and parsed.prompt != get_lesson(35).prompt:
            raise LessonError("Lesson 35 uses a fixed transcript comparison; restore its example prompt.")
        if lesson_id == 35:
            selected = parsed.lesson_options
            if selected["fault"] == "reject-append" and (selected["action"] != "commit" or not selected["enabled"]):
                raise LessonError("The rejected-mirror comparison uses enabled storage and one commit turn.")
            if selected["fault"] == "delay-load" and (selected["action"] != "durable-resume" or not selected["enabled"]):
                raise LessonError("Delayed loading uses enabled durable resume.")
            if not selected["enabled"] and selected["action"] != "commit":
                raise LessonError("The disabled-store comparison uses one commit turn.")
        if lesson_id == 36 and parsed.prompt != get_lesson(36).prompt:
            raise LessonError("Lesson 36 uses a fixed process comparison; restore its example prompt.")
        if lesson_id == 37 and parsed.prompt != get_lesson(37).prompt:
            raise LessonError("Lesson 37 uses a fixed owned Write request; restore its example prompt.")
        if lesson_id == 37 and parsed.mode == "live" and parsed.lesson_options["action"] == "missing-effect":
            raise LessonError("The no-effect case is a prepared host failure only.")
        if lesson_id == 38 and parsed.prompt != get_lesson(38).prompt:
            raise LessonError("Lesson 38 uses a fixed suggestion probe; restore its example prompt.")
        if lesson_id == 39 and parsed.prompt != get_lesson(39).prompt:
            raise LessonError("Lesson 39 uses a fixed configuration-root probe; restore its example prompt.")
        if lesson_id == 39 and parsed.mode == "live" and parsed.lesson_options["root"] in {"relative", "missing", "file"}:
            raise LessonError("Invalid-root probes use the credential-free startup action, not a provider call.")
        if lesson_id == 39 and parsed.lesson_options["action"] == "takeover" and (parsed.lesson_options["cwd"] != "branch" or parsed.lesson_options["root"] not in {"trusted", "omitted"} or parsed.lesson_options["sources"] != "project-local"):
            raise LessonError("Takeover uses branch cwd, project/local sources and trusted or omitted root.")
        if lesson_id == 40 and parsed.prompt != get_lesson(40).prompt:
            raise LessonError("Lesson 40 uses fixed transcript turns and review prompts; restore its example prompt.")
        if lesson_id == 41 and parsed.prompt != get_lesson(41).prompt:
            raise LessonError("Lesson 41 uses fixed Python client prompts; restore its example prompt.")
        if lesson_id == 42 and parsed.prompt != get_lesson(42).prompt:
            raise LessonError("Lesson 42 uses fixed web research prompts; restore its example prompt.")
        if lesson_id == 43 and parsed.prompt != get_lesson(43).prompt:
            raise LessonError("Lesson 43 uses fixed remote MCP prompts; restore its example prompt.")
        if lesson_id == 43 and parsed.mode == "live" and parsed.lesson_options["action"] not in {"live", "reconnect"}:
            raise LessonError("Select Agent step for a billed provider call; the other remote MCP actions are local host probes.")
        if lesson_id == 44 and parsed.prompt != get_lesson(44).prompt:
            raise LessonError("Lesson 44 uses fixed telemetry prompts; restore its example prompt.")
        if lesson_id == 44 and parsed.mode == "live" and not parsed.lesson_options["consent"]:
            raise LessonError("Confirm this fresh bounded paid telemetry action.")
        if lesson_id == 45 and parsed.prompt != get_lesson(45).prompt:
            raise LessonError("Lesson 45 uses fixed cloud-format prompts; restore its example prompt.")
        if lesson_id == 45 and parsed.mode == "live" and not parsed.lesson_options["consent"]:
            raise LessonError("Confirm this fresh bounded paid cloud action.")
        if lesson_id == 46 and parsed.prompt != get_lesson(46).prompt:
            raise LessonError("Lesson 46 uses fixed cache measurement prompts; restore its example prompt.")
        if lesson_id == 46 and parsed.mode == "live" and not parsed.lesson_options["consent"]:
            raise LessonError("Confirm this fresh bounded paid cache action.")
        if lesson_id == 47 and parsed.prompt != get_lesson(47).prompt:
            raise LessonError("Lesson 47 uses fixed orchestration prompts; restore its example prompt.")
        if lesson_id == 47 and parsed.mode == "live" and not parsed.lesson_options["consent"]:
            raise LessonError("Confirm this fresh bounded paid orchestration action.")
        if lesson_id == 47 and parsed.scenario in {"cancel-worker", "missing-file"} and parsed.lesson_options["action"] != "fanout":
            raise LessonError("Select regional fan-out for worker cancellation or the missing east file.")
        if lesson_id == 48 and parsed.prompt != get_lesson(48).prompt:
            raise LessonError("Lesson 48 uses fixed owned security probes; restore its example prompt.")
        if lesson_id == 48 and parsed.mode == "live" and not parsed.lesson_options["consent"]:
            raise LessonError("Confirm this fresh bounded paid security action.")
        if lesson_id == 49 and parsed.prompt != get_lesson(49).prompt:
            raise LessonError("Lesson 49 uses fixed headless probes; restore its example prompt.")
        if lesson_id == 49 and parsed.mode == "live" and (not parsed.lesson_options["consent"] or
                                                          parsed.lesson_options["action"] not in {"headless", "ci"}):
            raise LessonError("Select Headless or CI and confirm this fresh bounded paid action.")
        if lesson_id in {6, 12} and not parsed.follow_up:
            raise LessonError("Enter a nonempty follow-up for the session experiment.")
        if lesson_id == 12 and parsed.lesson_options["interactive"] and parsed.scenario != "success":
            raise LessonError("Recorded negative scenarios use the scripted session only.")
        if lesson_id == 13 and parsed.scenario == "tool-error" and (
            parsed.lesson_options["tool"] != "reserve" or not parsed.lesson_options["enabled"]
        ):
            raise LessonError("Select an enabled Reserve tool for the inventory-error scenario.")
        if lesson_id == 18 and parsed.lesson_options["native_required"]:
            from agent_lab.sandbox_native import sandbox_capability

            if parsed.mode != "live":
                raise LessonError("Native sandbox verification requires explicitly selected live mode.")
            if parsed.lesson_options["target"] != "inside":
                raise LessonError("The native probe has its own fixed targets; select Inside.")
            capability = sandbox_capability()
            if not capability["supported"]:
                raise LessonError(capability["reason"])
        return parsed
    parsed = (QueryRunRequest if lesson_id == 1 else RunRequest).model_validate(data)
    if parsed.lesson_options:
        raise LessonError("This lesson does not accept lesson-specific options.")
    if parsed.scenario != "success" and (lesson_id != 1 or parsed.mode != "offline"):
        raise LessonError("Recorded scenarios are available only in lesson 1 offline mode.")
    return parsed


class Event(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class Lesson(BaseModel):
    id: int
    title: str
    topic: str
    objective: str
    prompt: str
    exercise: str
    live_profile: str = "query"
    notes: str = ""
    # Live-run defaults shown in the UI and used by the CLI.
    max_turns: int = 4
    max_budget_usd: float = 0.10


class LessonError(Exception):
    """A host-generated failure whose message is safe to show to the student."""
