"""Reported usage, message grouping and a meter over comparable cumulative results."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
)

from agent_lab.config import Settings
from agent_lab.foundation_models import UsageInputs
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.thinking import counter

Emit = Callable[[Event], Awaitable[None]]
CRITERION = "A successful final result reports finite nonnegative cost and input/output token counts. Future billing and cache savings are not predicted."


@dataclass
class UsageMeter:
    baseline: int | float | None = 0
    identity: str | None = None
    samples: list[dict] = field(default_factory=list)

    def observe(self, identity: str | None, value: Any) -> dict:
        """Subtract before updating; missing/decreasing/unrelated totals break comparability."""
        total = counter(value)
        same = bool(identity) and self.identity in {None, identity}
        delta = (
            round(total - self.baseline, 10)
            if same and total is not None and self.baseline is not None and total >= self.baseline
            else None
        )
        row = {
            "cumulative_cost_usd": total,
            "delta_usd": delta,
            "comparable": delta is not None,
            "sdk_identity": identity,
        }
        self.samples.append(row)
        self.baseline = total if same else None
        self.identity = identity
        return row


@dataclass
class UsageObservation:
    run: str
    live: bool
    groups: dict[str, dict] = field(default_factory=dict)
    identities: list[str] = field(default_factory=list)
    finals: list[dict] = field(default_factory=list)
    last_root: str = ""
    connection_closed: bool = False

    def observe(self, data: dict, block_types: list[str] | None = None) -> None:
        if data.get("parent_tool_use_id"):
            return
        self.last_root = data.get("message_class", "")
        if self.last_root == "SystemMessage" and data.get("subtype") == "init":
            identity = data.get("data", {}).get("session_id")
            if isinstance(identity, str) and identity:
                self.identities.append(identity)
        if self.last_root == "AssistantMessage":
            identity = data.get("message_id")
            key = identity if isinstance(identity, str) and identity else "[unidentified]"
            row = self.groups.setdefault(
                key, {"message_id": identity, "block_types": [], "intermediate_usage": None}
            )
            row["block_types"] = sorted(set(row["block_types"]) | set(block_types or []))
            if isinstance(data.get("usage"), dict):
                row["intermediate_usage"] = usage_fields(data["usage"])
        if self.last_root == "ResultMessage":
            self.finals.append(
                {
                    "session_id": data.get("session_id"),
                    "subtype": data.get("subtype"),
                    "is_error": data.get("is_error"),
                    "total_cost_usd": counter(data.get("total_cost_usd")),
                    "usage": usage_fields(data.get("usage")),
                    "model_usage": model_fields(data.get("model_usage")),
                    "num_turns": counter(data.get("num_turns")),
                }
            )

    def report(self) -> dict:
        final = self.finals[-1] if self.finals else {}
        usage = final.get("usage", {})
        identity = final.get("session_id")
        passed = bool(
            identity
            and self.identities
            and all(s == identity for s in self.identities)
            and len(self.finals) == 1
            and self.last_root == "ResultMessage"
            and final.get("subtype") == "success"
            and final.get("is_error") is False
            and final.get("total_cost_usd") is not None
            and usage.get("input_tokens") is not None
            and usage.get("output_tokens") is not None
            and self.connection_closed
        )
        return {
            "run_id": self.run,
            "correlated_identity": identity
            if identity and self.identities and all(s == identity for s in self.identities)
            else None,
            "source": "live SDK stream and actual host callbacks"
            if self.live
            else "host accounting with explicitly recorded SDK payloads; no model call",
            "messages": list(self.groups.values()),
            "identified_messages": sum(k != "[unidentified]" for k in self.groups),
            "final": final,
            "connection_closed": self.connection_closed,
            "experiment_passed": passed,
            "expected_check": "passed" if passed else "needs-review",
            "check_scope": CRITERION,
            "note": "Message usage is intermediate. Final usage and per-model aggregates are distinct reports. Unknown is not zero; a threshold is not an exact price or billing guarantee.",
        }


def usage_fields(value: Any) -> dict:
    value = value if isinstance(value, dict) else {}
    return {
        key: counter(value.get(key))
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
    }


def model_fields(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        str(model)[:100]: {
            key: counter(row.get(key))
            for key in (
                "inputTokens",
                "outputTokens",
                "cacheReadInputTokens",
                "cacheCreationInputTokens",
                "costUSD",
            )
        }
        for model, row in list(value.items())[:20]
        if isinstance(row, dict)
    }


def usage_options(
    request: RunRequest, work: Path, config: Path, settings: Settings
) -> ClaudeAgentOptions:
    """Only typed bounded options; task_budget is planning guidance, not a hard stop."""
    from agent_lab.sdk import isolated_env, resolve_cli_path

    selected = UsageInputs.model_validate(request.lesson_options)

    async def helper_only(name: str, arguments: dict, context: Any) -> Any:
        if name == "Agent" and arguments.get("subagent_type") == "usage_reader":
            return PermissionResultAllow(updated_input=arguments)
        return PermissionResultDeny(
            message="Only the usage_reader helper with no tools is permitted."
        )

    return ClaudeAgentOptions(
        model=settings.model,
        tools=["Agent"] if selected.allow_agent else [],
        agents={
            "usage_reader": AgentDefinition(
                description="Explain usage concepts",
                prompt="Explain briefly. Do not delegate or use tools.",
                tools=[],
            )
        }
        if selected.allow_agent
        else None,
        max_turns=None if selected.omit_turn_limit else request.max_turns,
        max_budget_usd=None if selected.omit_budget_limit else request.max_budget_usd,
        task_budget={"total": selected.task_tokens} if selected.task_tokens is not None else None,
        setting_sources=[],
        strict_mcp_config=True,
        cwd=str(work),
        env=isolated_env(config),
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        include_partial_messages=False,
        can_use_tool=helper_only if selected.allow_agent else None,
    )


def recorded_usage(scenario: str, turn: int = 1) -> list[tuple[dict, list[str]]]:
    identity = "recorded-usage-session"
    assistant = {
        "message_class": "AssistantMessage",
        "message_id": f"recorded-message-{turn}",
        "usage": {"input_tokens": 3, "output_tokens": 1},
        "content": [{"text": "Recorded public usage example; no model was called."}],
    }
    final = {
        "message_class": "ResultMessage",
        "session_id": "unrelated" if scenario == "wrong-identity" else identity,
        "subtype": {
            "turn-limit": "error_max_turns",
            "budget-limit": "error_max_budget_usd",
            "interrupted": "recorded_interruption",
        }.get(scenario, "success"),
        "is_error": scenario in {"turn-limit", "budget-limit", "interrupted"},
        "total_cost_usd": [0.01, 0.025, 0.04, 0.05][min(turn, 4) - 1],
        "usage": {"input_tokens": turn * 10, "output_tokens": turn * 4},
        "model_usage": {
            "recorded-model": {
                "inputTokens": turn * 10,
                "outputTokens": turn * 4,
                "costUSD": [0.01, 0.025, 0.04, 0.05][min(turn, 4) - 1],
            }
        },
    }
    if scenario == "missing-usage":
        final["usage"] = None
    if scenario == "invalid-usage":
        final["usage"] = {"input_tokens": -1, "output_tokens": True}
    rows: list[tuple[dict, list[str]]] = [
        (
            {"message_class": "SystemMessage", "subtype": "init", "data": {"session_id": identity}},
            [],
        ),
        (assistant, ["TextBlock"]),
        (assistant, ["ThinkingBlock"]),
    ]
    return rows if scenario == "missing-evidence" else [*rows, (final, [])]


async def collect_usage(
    observation: UsageObservation, request: RunRequest, client: Any, emit: Emit, turn: int = 1
) -> None:
    """Collect one response; expose only public text and validated counters."""
    from agent_lab.sdk import message_data

    async def observe(data: dict, types: list[str]) -> None:
        if data.get("parent_tool_use_id"):
            return
        observation.observe(data, types)
        if data.get("message_class") == "AssistantMessage":
            await emit(
                Event(
                    kind="message",
                    data={
                        "message_class": "AssistantMessage",
                        "content": [
                            b
                            for b in data.get("content", [])
                            if isinstance(b, dict)
                            and "text" in b
                            and "thinking" not in b
                            and "signature" not in b
                        ],
                        "parent_tool_use_id": data.get("parent_tool_use_id"),
                    },
                )
            )
        elif data.get("message_class") == "ResultMessage":
            await emit(
                Event(
                    kind="result", data={"message_class": "ResultMessage", **observation.finals[-1]}
                )
            )

    if request.mode == "offline":
        for data, types in recorded_usage(request.scenario, turn):
            await observe(data, types)
    else:
        async for message in client.receive_response():
            if (
                isinstance(message, SystemMessage)
                and message.subtype == "api_retry"
                and message.data.get("error_status") == 401
            ):
                raise PermissionError(
                    "Claude rejected authentication (HTTP 401). No host retry was attempted."
                )
            if (
                isinstance(message, (SystemMessage, ResultMessage))
                or type(message).__name__ == "AssistantMessage"
            ):
                await observe(
                    message_data(message),
                    [type(b).__name__ for b in getattr(message, "content", [])],
                )


async def execute_usage(
    root: Path, request: RunRequest, settings: Settings, emit: Emit, config: Path | None = None
) -> dict:
    from agent_lab.sdk import ClaudeSDKClient, require_live_access

    request = lesson_request(15, request)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    config = config or root.parent / "usage-config"
    await asyncio.to_thread(config.mkdir, parents=True, exist_ok=True)
    options = usage_options(request, root, config, settings)
    observation = UsageObservation(root.parent.name, live)
    client = None
    proof = {}
    try:
        await emit(
            Event(
                kind="options",
                data={
                    "lesson_id": 15,
                    "sdk_options": {
                        "max_turns": options.max_turns,
                        "max_budget_usd": options.max_budget_usd,
                        "task_budget": options.task_budget,
                        "tools": options.tools,
                    },
                },
            )
        )
        if live:
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(request.prompt)
        await collect_usage(observation, request, client, emit)
        if live and (
            not observation.finals
            or observation.finals[-1]["subtype"] != "success"
            or observation.finals[-1]["is_error"] is not False
        ):
            subtype = (
                observation.finals[-1]["subtype"] if observation.finals else "missing final result"
            )
            raise LessonError(
                "The SDK stopped this run: "
                + str(subtype)
                + ". Inspect the terminal evidence; a limit stop is not successful completion."
            )
    finally:
        try:
            if client is not None:
                await client.disconnect()
            observation.connection_closed = True
        finally:
            experiment = observation.report()
            experiment["scenario"] = request.scenario
            meter = UsageMeter()
            final = experiment["final"]
            experiment["meter"] = meter.observe(
                experiment.get("correlated_identity"), final.get("total_cost_usd")
            )
            proof = {
                "exercise": "budget",
                "experiment": experiment,
                "experiment_passed": experiment["experiment_passed"],
            }
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 15, "result": proof}))
    return proof


async def local_usage(root: Path, request: RunRequest) -> dict:
    async def ignore(event: Event) -> None:
        pass

    return await execute_usage(
        root, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
