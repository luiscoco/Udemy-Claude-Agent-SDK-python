"""Fresh bounded comparison lanes: requested options versus Stop-hook observations.

Offline hooks execute with recorded payloads; model metrics remain unknown. Live
lanes use separate SDK clients and the identical prompt, without a fallback/retry.
"""

import asyncio
import hashlib
import math
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    ResultMessage,
    SystemMessage,
)
from claude_agent_sdk.types import ThinkingConfig

from agent_lab.config import Settings
from agent_lab.foundation_models import ThinkingInputs
from agent_lab.hooks import call_hook
from agent_lab.models import Event, LessonError, RunRequest, lesson_request

Emit = Callable[[Event], Awaitable[None]]


def thinking_config(selected: ThinkingInputs) -> ThinkingConfig:
    if selected.thinking == "disabled":
        return {"type": "disabled"}
    config: dict[str, Any] = {"type": selected.thinking}
    if selected.thinking == "enabled":
        config["budget_tokens"] = selected.budget_tokens
    if selected.display != "default":
        config["display"] = selected.display
    return cast(ThinkingConfig, config)


def plan_lanes(values: dict, configured_model: str) -> list[tuple[str, ThinkingInputs]]:
    primary = ThinkingInputs.model_validate(
        dict(values, model=values.get("model") or configured_model)
    )
    lanes = [("A", primary)]
    if primary.comparison != "none":
        field_name = primary.comparison
        next_value = getattr(primary, "comparison_" + field_name)
        if getattr(primary, field_name) == next_value:
            raise LessonError(
                "Change the selected comparison setting; identical lanes are not a comparison."
            )
        secondary = ThinkingInputs.model_validate(primary.model_dump() | {field_name: next_value})
        lanes.append(("B", secondary))
    return lanes


def counter(value: Any) -> int | float | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value >= 0 else None
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


@dataclass
class Lane:
    name: str
    run: str
    selected: ThinkingInputs
    prompt: str
    live: bool
    input_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    initialization: list[str] = field(default_factory=list)
    hooks: list[dict] = field(default_factory=list)
    terminals: list[dict] = field(default_factory=list)
    reported_models: set[str] = field(default_factory=set)
    configured: dict = field(default_factory=dict)
    connection_closed: bool = False
    host_elapsed_ms: float | None = None
    last_root_message: str | None = None

    async def stop(
        self, arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        data = cast(dict, arguments)
        if data.get("hook_event_name") != "Stop":
            return {}
        effort = data.get("effort")
        level = effort.get("level") if isinstance(effort, dict) else None
        if not isinstance(level, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", level):
            level = None
        self.hooks.append(
            {
                "event": "Stop",
                "run": self.run,
                "lane": self.name,
                "sdk_identity": data.get("session_id"),
                "prompt_id": data.get("prompt_id")
                if data.get("prompt_id") is None or isinstance(data.get("prompt_id"), str)
                else "[invalid]",
                "root": not bool(data.get("agent_id") or data.get("parent_tool_use_id")),
                "effort_field_present": "effort" in data,
                "observed_effort": level,
            }
        )
        return {}  # An observer: never block, modify or continue a turn.

    def observe(self, event: Event) -> None:
        data = event.data
        if event.kind in {"message", "result"} and not data.get("parent_tool_use_id"):
            self.last_root_message = data.get("message_class")
            if data.get("message_class") == "SystemMessage" and data.get("subtype") == "init":
                identity = data.get("data", {}).get("session_id")
                if isinstance(identity, str) and identity:
                    self.initialization.append(identity)
            if data.get("message_class") == "AssistantMessage" and isinstance(
                data.get("model"), str
            ):
                self.reported_models.add(data["model"])
            if event.kind == "result":
                self.terminals.append(data)

    def report(self) -> dict:
        terminal = self.terminals[-1] if self.terminals else {}
        identity = terminal.get("session_id")
        successful = bool(
            identity
            and self.initialization
            and all(s == identity for s in self.initialization)
            and terminal.get("subtype") == "success"
            and terminal.get("is_error") is False
            and self.last_root_message == "ResultMessage"
            and self.connection_closed
        )
        observations = [
            h
            for h in self.hooks
            if h["run"] == self.run
            and h["lane"] == self.name
            and h["root"]
            and h["sdk_identity"] == identity
            and h["prompt_id"] in {None, self.input_id}
            and h["observed_effort"] is not None
        ]
        usage = terminal.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return {
            "lane": self.name,
            "source": "live SDK stream and actual Stop callback"
            if self.live
            else "host options and callback executed with explicitly recorded SDK payloads; no model",
            "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
            "requested": self.configured,
            "reported_models": sorted(self.reported_models),
            "stop_observations": self.hooks,
            "terminal_results": self.terminals,
            "observed_effort": observations[-1]["observed_effort"] if observations else None,
            "metrics": {
                "host_elapsed_ms": self.host_elapsed_ms,
                "sdk_duration_ms": counter(terminal.get("duration_ms")) if self.live else None,
                "input_tokens": counter(usage.get("input_tokens")) if self.live else None,
                "output_tokens": counter(usage.get("output_tokens")) if self.live else None,
                "cost_usd": counter(terminal.get("total_cost_usd")) if self.live else None,
            },
            "connection_closed": self.connection_closed,
            "experiment_passed": successful and bool(observations),
            "note": "Unknown effort/usage is not zero. Requested versus reported values do not establish hidden reasoning, fallback, answer quality or model compatibility.",
        }


def lane_options(
    lane: Lane, request: RunRequest, work: Path, config: Path, settings: Settings
) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    options = ClaudeAgentOptions(
        model=lane.selected.model,
        thinking=thinking_config(lane.selected),
        effort=lane.selected.effort,
        tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        cwd=str(work),
        env=isolated_env(config),
        cli_path=resolve_cli_path(settings) if lane.live else None,
        hooks={"Stop": [HookMatcher(hooks=[lane.stop])]},
        include_partial_messages=False,
    )
    lane.configured = {
        "model": options.model,
        "thinking": options.thinking,
        "effort": options.effort,
        "tools": [],
        "setting_sources": [],
        "max_turns": options.max_turns,
        "max_budget_usd": options.max_budget_usd,
    }
    return options


def comparison_report(lanes: list[Lane], planned: int, scenario: str) -> dict:
    reports = [lane.report() for lane in lanes]
    passed = len(reports) == planned and all(r["experiment_passed"] for r in reports)
    return {
        "source": "live SDK stream and actual host callbacks"
        if lanes and lanes[0].live
        else "host options and Stop callbacks with explicitly recorded SDK fixtures; no model call",
        "scenario": scenario,
        "planned_lanes": planned,
        "started_lanes": len(reports),
        "completed_lanes": sum(
            r["connection_closed"] and bool(r["terminal_results"]) for r in reports
        ),
        "lanes": reports,
        "not_started_lanes": planned - len(reports),
        "experiment_passed": passed,
        "check_scope": "Each planned lane needs a Stop effort observation matching its parent session/run, successful terminal completion and closed connection. Hidden reasoning, fallback, answer quality and general model support are not measured.",
        "expected_check": "passed" if passed else "needs-review",
    }


async def execute_thinking(
    root: Path, request: RunRequest, settings: Settings, emit: Emit, config_root: Path | None = None
) -> dict:
    from agent_lab.sdk import ClaudeSDKClient, message_data, require_live_access

    request = lesson_request(14, request)
    plan = plan_lanes(request.lesson_options, settings.model)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    lanes: list[Lane] = []
    try:
        for name, selected in plan:
            lane = Lane(name, root.parent.name, selected, request.prompt, live)
            lanes.append(lane)
            work = root if len(plan) == 1 else root / ("lane-" + name)
            config = (
                (config_root if len(plan) == 1 else config_root / name)
                if config_root
                else root.parent / ("thinking-config-" + name)
            )
            await asyncio.to_thread(work.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(config.mkdir, parents=True, exist_ok=True)
            options = lane_options(lane, request, work, config, settings)
            await emit(
                Event(
                    kind="options",
                    data={"lesson_id": 14, "lane": name, "sdk_options": lane.configured},
                )
            )
            started = time.perf_counter()
            try:
                if not live:
                    assert options.hooks is not None
                    identity = "recorded-parent-" + name
                    lane.initialization.append(identity)
                    if request.scenario not in {
                        "missing-evidence",
                        "unsupported",
                        "model-error",
                        "interrupted",
                    }:
                        payload = {
                            "hook_event_name": "Stop",
                            "session_id": "different-parent"
                            if request.scenario == "wrong-identity"
                            else identity,
                            "prompt_id": lane.input_id,
                            "stop_hook_active": False,
                            "effort": {"level": selected.effort or "medium"},
                        }
                        if request.scenario == "missing-effort":
                            payload.pop("effort")
                        await call_hook(options.hooks["Stop"][0].hooks[0], payload, None)
                    error = request.scenario in {"unsupported", "model-error", "interrupted"}
                    lane.terminals.append(
                        {
                            "subtype": {
                                "unsupported": "recorded_unsupported_options",
                                "model-error": "recorded_model_access_error",
                                "interrupted": "recorded_interruption",
                            }.get(request.scenario, "success"),
                            "is_error": error,
                            "session_id": identity,
                        }
                    )
                    lane.last_root_message = "ResultMessage"
                    lane.connection_closed = True
                else:

                    async def one_input(current_lane: Lane = lane) -> Any:
                        yield {
                            "type": "user",
                            "uuid": current_lane.input_id,
                            "session_id": "default",
                            "parent_tool_use_id": None,
                            "message": {"role": "user", "content": request.prompt},
                        }

                    client = ClaudeSDKClient(options=options)
                    try:
                        await client.connect()
                        await client.query(one_input())
                        async for message in client.receive_response():
                            if (
                                isinstance(message, SystemMessage)
                                and message.subtype == "api_retry"
                                and message.data.get("error_status") == 401
                            ):
                                raise PermissionError(
                                    "Claude rejected authentication (HTTP 401). Check credentials; this comparison makes no automatic retry."
                                )
                            data = message_data(message)
                            if data.get("message_class") == "StreamEvent":
                                continue  # Complete public text is enough; never forward thinking/signature deltas.
                            # Capture public answers and metrics, never private thinking blocks.
                            if isinstance(data.get("content"), list):
                                data["content"] = [
                                    b
                                    for b in data["content"]
                                    if isinstance(b, dict)
                                    and "text" in b
                                    and "thinking" not in b
                                    and "signature" not in b
                                    and b.get("type") in {None, "text"}
                                ]
                            event = Event(
                                kind="result" if isinstance(message, ResultMessage) else "message",
                                data=data | {"lane": name},
                            )
                            lane.observe(event)
                            await emit(event)
                            if isinstance(message, ResultMessage) and (
                                message.is_error or message.subtype != "success"
                            ):
                                raise LessonError(
                                    "The SDK rejected or failed this lane. Inspect its terminal error and account/model access. No host fallback, retry or subsequent lane was started."
                                )
                    finally:
                        await client.disconnect()
                        lane.connection_closed = True
            finally:
                lane.host_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    finally:
        report = comparison_report(lanes, len(plan), request.scenario)
        try:
            async with asyncio.timeout(1):
                await emit(
                    Event(
                        kind="evidence",
                        data={
                            "lesson_id": 14,
                            "source": report["source"],
                            "result": {
                                "experiment": report,
                                "experiment_passed": report["experiment_passed"],
                            },
                        },
                    )
                )
        except TimeoutError:
            pass
    return {"experiment": report, "experiment_passed": report["experiment_passed"]}


async def local_thinking(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    # This producer builds host options and recorded payloads, never a paid client.
    return await execute_thinking(
        root, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
