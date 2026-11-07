"""Bounded SDK experiments for lessons 2–12, with independently correlated evidence.

Offline records explicitly combine real local host effects with recorded SDK identities.
Live records are collected from the actual stream and registered callbacks.
"""

import asyncio
import dataclasses
import hashlib
import inspect
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    HookJSONOutput,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
)
from pydantic import ValidationError

from agent_lab.foundation_models import inputs
from agent_lab.hooks import Ask, call_hook, post_tool_hook
from agent_lab.models import Event, Lesson, LessonError, RunRequest, lesson_request
from agent_lab.policy import decide, inside
from agent_lab.services import Calculation, Summary
from agent_lab.skills import local_skills

Emit = Callable[[Event], Awaitable[None]]


def prompt_representation(mode: str, text: str, context: str = "") -> str | dict[str, str] | None:
    if mode == "default":
        return None
    if mode == "custom":
        return text
    if mode == "boundary":
        return text + "\nSYSTEM_PROMPT_DYNAMIC_BOUNDARY\n" + context
    return {"type": "preset", "preset": "claude_code", "append": text}


def configure(
    options: ClaudeAgentOptions, lesson: Lesson, request: RunRequest, work: Path
) -> dict[str, Any]:
    """Apply selected inputs to the real SDK options; never accept arbitrary paths or tools."""
    selected = inputs(lesson.id, request.lesson_options).model_dump()
    extra = {}
    if lesson.id == 2:
        options.model = selected["model"]
        options.system_prompt = prompt_representation(
            selected["system_mode"], selected["system_text"]
        )  # type: ignore[assignment]
        options.include_partial_messages = selected["partial_messages"]
        options.max_turns = None if selected["omit_turn_limit"] else request.max_turns
        options.max_budget_usd = None if selected["omit_budget_limit"] else request.max_budget_usd
    elif lesson.id == 3:
        options.tools = [selected["tool"]]
    elif lesson.id == 4:
        options.tools = ["Read", "Write", "Edit"]
    elif lesson.id == 8:
        options.agents = {
            "reviewer": AgentDefinition(
                description="Review the owned lesson fixture",
                prompt="Inspect notes.txt using only your configured tools. Report limitations honestly.",
                tools=["Read", "Glob", "Grep"] if selected["worker_tools"] == "read-only" else [],
                model=selected["worker_model"],
                background=False,
            )
        }
    elif lesson.id == 9:
        options.system_prompt = prompt_representation(
            selected["variant"], selected["instruction"], selected["context"]
        )  # type: ignore[assignment]
        options.setting_sources = ["project"] if selected["variant"] == "project" else []
        if selected["variant"] == "project":
            inside(work, "CLAUDE.md").write_text(selected["instruction"] + "\n", encoding="utf-8")
    elif lesson.id == 11:
        from agent_lab.skills import configure_skills

        extra = configure_skills(options, work, request)
    # Do not expose environment variables, CLI authentication or host configuration.
    fields = (
        "model",
        "system_prompt",
        "max_turns",
        "max_budget_usd",
        "include_partial_messages",
        "tools",
        "allowed_tools",
        "setting_sources",
        "strict_mcp_config",
    )
    echo = {name: getattr(options, name) for name in fields}
    if lesson.id == 8:
        echo["agents"] = {
            name: dataclasses.asdict(agent) for name, agent in (options.agents or {}).items()
        }
    if lesson.id == 10:
        echo["output_format"] = options.output_format
    echo.update(extra)
    return echo


def fingerprint(root: Path, target: str) -> str | None:
    path = inside(root, target)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def supported_target(root: Path, value: Any) -> str:
    path = Path(str(value))
    if path.is_absolute():
        path = path.resolve().relative_to(root.resolve())
    relative = path.as_posix()
    inside(root, relative)
    if relative not in {"notes.txt", "draft.txt", "approved.txt"}:
        raise ValueError("Only the displayed lesson fixture targets are supported.")
    return relative


@dataclass
class Evidence:
    lesson: int
    run_id: str
    root: Path
    selected: dict[str, Any]
    source: str
    requested_turns: int = 4
    requested_budget: float = 0.10
    configured: dict[str, Any] = field(default_factory=dict)
    initialized: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    terminals: list[dict[str, Any]] = field(default_factory=list)
    handlers: list[dict[str, Any]] = field(default_factory=list)
    post_hooks: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    sent_sessions: list[str | None] = field(default_factory=list)
    validated: list[dict[str, Any]] = field(default_factory=list)
    unsupported: bool = False
    last_root_message: str | None = None

    def observe(self, event: Event) -> None:
        data = event.data
        if event.kind in {"message", "result"}:
            if not data.get("parent_tool_use_id"):
                self.last_root_message = data.get("message_class")
            self.messages.append(
                {
                    "message_class": data.get("message_class"),
                    "parent_tool_use_id": data.get("parent_tool_use_id"),
                }
            )
            if data.get("message_class") == "SystemMessage" and data.get("subtype") == "init":
                self.initialized.append(data.get("data", {}))
            if event.kind == "result":
                self.terminals.append(data)
            for block in data.get("content", []):
                if not isinstance(block, dict):
                    continue
                if "id" in block and "name" in block and "input" in block:
                    self.calls.append(
                        {
                            "id": block["id"],
                            "name": block["name"],
                            "arguments": block["input"],
                            "parent_tool_use_id": data.get("parent_tool_use_id"),
                            "run_id": self.run_id,
                        }
                    )
                if "tool_use_id" in block:
                    self.results.append(
                        {
                            "id": block["tool_use_id"],
                            "is_error": bool(block.get("is_error")),
                            "run_id": self.run_id,
                        }
                    )
        elif event.kind == "tool" and data.get("name") == "add" and "arguments" in data:
            self.handlers.append(
                {
                    "name": "mcp__lesson__add",
                    "arguments": data["arguments"],
                    "result": data.get("sum"),
                    "run_id": self.run_id,
                }
            )
        elif event.kind == "audit" and data.get("tool_use_id"):
            self.post_hooks.append(
                {"id": data["tool_use_id"], "name": data.get("tool"), "run_id": self.run_id}
            )
        elif event.kind == "validated":
            self.validated.append(data)

    def report(self) -> dict[str, Any]:
        for decision in self.decisions:
            if decision.get("supported"):
                decision["final_hash"] = fingerprint(self.root, decision["target"])
        paired = [
            call
            for call in self.calls
            if call.get("run_id") == self.run_id
            and sum(
                result.get("id") == call.get("id")
                and result.get("run_id") == self.run_id
                and result.get("is_error") is False
                for result in self.results
            )
            == 1
            and sum(other.get("id") == call.get("id") for other in self.calls) == 1
            and sum(result.get("id") == call.get("id") for result in self.results) == 1
        ]
        terminal = self.terminals[-1] if self.terminals else {}
        success = bool(
            terminal.get("subtype") == "success"
            and terminal.get("is_error") is False
            and terminal.get("session_id")
        )
        if self.initialized and terminal.get("session_id") != self.initialized[-1].get(
            "session_id"
        ):
            success = False
        if self.last_root_message is not None and self.last_root_message != "ResultMessage":
            success = False
        passed = success
        explanation = "Inspect successful terminal evidence and the lesson-specific correlation."
        if self.lesson == 2:
            expected_options = {
                "model": self.selected["model"],
                "system_prompt": prompt_representation(
                    self.selected["system_mode"], self.selected["system_text"]
                ),
                "include_partial_messages": self.selected["partial_messages"],
                "max_turns": None if self.selected["omit_turn_limit"] else self.requested_turns,
                "max_budget_usd": None
                if self.selected["omit_budget_limit"]
                else self.requested_budget,
            }
            passed = (
                success
                and bool(self.initialized)
                and all(
                    self.configured.get(key) == value for key, value in expected_options.items()
                )
            )
            explanation = "Actual options were echoed, initialization was observed and the stream completed successfully. Limit enforcement and answer quality need separate review."
        elif self.lesson == 3:
            inventory = set(self.configured.get("tools", []))
            announced = set(self.initialized[0].get("tools", [])) if self.initialized else set()
            passed = success and any(call["name"] in inventory & announced for call in paired)
            explanation = "A configured built-in tool needs one successful result with the same call ID, plus successful completion. File changes and answer quality are separate."
        elif self.lesson == 4:
            denied = [row for row in self.decisions if row.get("decision") == "deny"]
            passed = (
                success
                and not self.unsupported
                and bool(denied)
                and all(
                    row.get("supported") is True
                    and row.get("run_id") == self.run_id
                    and row.get("call_id")
                    and "hash_at_decision" in row
                    and "final_hash" in row
                    and row.get("hash_at_decision") == row.get("final_hash")
                    and any(
                        call["id"] == row["call_id"]
                        and call["name"] in {"Write", "Edit"}
                        and call["run_id"] == self.run_id
                        for call in self.calls
                    )
                    for row in denied
                )
            )
            explanation = "Denied writes require matching run/call IDs and identical hashes or absence at denial and completion. Allow/update examples and unsupported targets need review; intermediate activity is not observed."
        elif self.lesson == 5:
            unique = []
            for handler in self.handlers:
                matching = [
                    call
                    for call in paired
                    if call["name"] == handler["name"] and call["arguments"] == handler["arguments"]
                ]
                identical = [
                    row
                    for row in self.handlers
                    if row["name"] == handler["name"] and row["arguments"] == handler["arguments"]
                ]
                unique.append(
                    len(matching) == len(identical) == 1 and handler["run_id"] == self.run_id
                )
            passed = success and bool(unique) and all(unique)
            explanation = "A custom handler must uniquely match name and arguments, then a successful result by call ID. Ambiguous matches need review."
        elif self.lesson == 6:
            identities = [row.get("session_id") for row in self.terminals]
            passed = (
                success
                and len(identities) >= 2
                and identities[-1] == identities[0]
                and self.selected["strategy"] != "fresh"
                and self.terminals[0].get("subtype") == "success"
                and self.terminals[0].get("is_error") is False
            )
            if self.selected["strategy"] == "resume":
                passed = (
                    passed
                    and self.sent_sessions[-1:] == identities[:1]
                    and len(self.initialized) >= 2
                    and self.initialized[-1].get("session_id") == identities[0]
                )
            explanation = "Compare the previous session, outgoing resume identity and next initialization. Same-client continuation is distinguished from explicit resume. Fresh sessions and recalled answer quality are separate observations."
        elif self.lesson == 7:
            passed = (
                success
                and self.selected["post_hook"]
                and any(
                    hook["run_id"] == self.run_id
                    and hook["id"] == call["id"]
                    and hook["name"] == call["name"]
                    for hook in self.post_hooks
                    for call in paired
                )
            )
            explanation = "An enabled post-use hook must match a successful call/result by ID and name. This does not prove that a pre-use guard or rewrite enforced the intended content."
        elif self.lesson == 8:
            passed = success and any(
                call["name"] in {"Agent", "Task"}
                and not call.get("parent_tool_use_id")
                and call["arguments"].get("subagent_type") == "reviewer"
                for call in paired
            )
            explanation = "A parent Agent/Task delegation needs a successful matching result and successful parent completion. Worker report quality is manual."
        elif self.lesson == 9:
            expected = prompt_representation(
                self.selected["variant"], self.selected["instruction"], self.selected["context"]
            )
            passed = (
                success
                and self.configured.get("system_prompt") == expected
                and self.configured.get("setting_sources")
                == (["project"] if self.selected["variant"] == "project" else [])
            )
            explanation = "The echoed system representation and selected project settings must match. This does not grade adherence or demonstrate caching."
        elif self.lesson == 10:
            accepted = []
            for value in self.validated:
                try:
                    accepted.append(Summary.model_validate(value).model_dump())
                except ValidationError:
                    continue
            passed = success and any(
                value == terminal.get("structured_output") for value in accepted
            )
            explanation = "The host must accept structured_output and observe terminal success. Factual accuracy and the separate interrupt/abort experiment are not certified."
        elif self.lesson == 11:
            from agent_lab.skills import skill_name

            expected = skill_name(self.selected)
            passed = (
                success
                and bool(self.initialized)
                and expected in (self.configured.get("skills") or [])
                and any(
                    call["name"] == "Skill"
                    and call["arguments"].get("skill") == expected
                    and not call.get("parent_tool_use_id")
                    for call in paired
                )
            )
            explanation = "A visible prepared Skill call needs one successful matching result and successful parent completion. Discovery and host preload alone do not pass. Generated files and answer quality are not certified."
        elif self.lesson == 13:
            configured = self.configured.get("mcp_servers", {})
            allowed = set(self.configured.get("allowed_tools", []))
            passed = (
                success
                and bool(self.initialized)
                and bool(configured)
                and any(
                    call["name"].startswith("mcp__inventory__")
                    and call["name"] in allowed
                    and not call.get("parent_tool_use_id")
                    for call in paired
                )
            )
            explanation = "A configured, permitted MCP tool needs one successful result with the same call/run identity and successful parent completion. Inventory snapshots and connection probes are separate evidence; remote service correctness is not certified."
        return {
            "source": self.source,
            "run": self.run_id,
            "configured": self.configured,
            "initialization": self.initialized,
            "calls": self.calls,
            "results": self.results,
            "handler_events": self.handlers,
            "post_use_hooks": self.post_hooks,
            "permission_decisions": self.decisions,
            "terminal_results": self.terminals,
            "message_groups": self.messages,
            "sent_sessions": self.sent_sessions,
            **(
                {
                    "session_identity": {
                        "previous_session": self.terminals[0].get("session_id")
                        if self.terminals
                        else None,
                        "followup_session": self.terminals[-1].get("session_id")
                        if self.terminals
                        else None,
                        "outgoing_resume": self.sent_sessions[-1] if self.sent_sessions else None,
                        "strategy": self.selected["strategy"],
                    }
                }
                if self.lesson == 6
                else {}
            ),
            "validated_values": self.validated,
            "experiment_passed": bool(passed),
            "check_scope": explanation,
        }


async def permission_decision(
    evidence: Evidence,
    request: RunRequest,
    name: str,
    arguments: dict[str, Any],
    call_id: str | None,
    ask: Ask | None,
) -> Any:
    if name not in {"Write", "Edit"}:
        allowed, reason = decide(evidence.root, name, arguments)
        return (
            PermissionResultAllow(updated_input=arguments)
            if allowed
            else PermissionResultDeny(message=reason)
        )
    try:
        target = supported_target(evidence.root, arguments.get("file_path"))
        if target != evidence.selected["target"]:
            raise ValueError("The requested target differs from the selected fixture.")
    except (ValueError, OSError):
        evidence.unsupported = True
        return PermissionResultDeny(message="Use only the selected owned lesson target.")
    decision = evidence.selected["decision"]
    if decision == "ask":
        if ask is None:
            raise LessonError("Use the browser to answer this permission question.")
        question = f"{name} {target}: allow, deny or redirect to approved.txt?"
        response = await ask(
            {
                "questions": [
                    {
                        "question": question,
                        "header": "Fixture permission",
                        "multiSelect": False,
                        "options": [
                            {"label": "Allow", "description": "Permit this fixture operation."},
                            {"label": "Deny", "description": "Refuse the operation."},
                            {"label": "Update", "description": "Redirect to approved.txt."},
                        ],
                    }
                ]
            }
        )
        decision = {"Allow": "allow", "Update": "update"}.get(response.get(question, ""), "deny")
    evidence.decisions.append(
        {
            "run_id": evidence.run_id,
            "call_id": call_id,
            "tool": name,
            "target": target,
            "supported": True,
            "decision": decision,
            "hash_at_decision": fingerprint(evidence.root, target),
        }
    )
    if decision == "deny":
        return PermissionResultDeny(message="The learner denied this fixture operation.")
    updated = dict(arguments)
    if decision == "update":
        updated["file_path"] = str(inside(evidence.root, "approved.txt"))
    return PermissionResultAllow(updated_input=updated)


def experiment_hooks(evidence: Evidence, emit: Emit) -> dict[Any, list[HookMatcher]]:
    selected = evidence.selected

    async def audit(kind: str, data: dict[str, Any]) -> None:
        await emit(Event(kind=kind, data=data))

    async def pre(arguments: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        name, value = arguments.get("tool_name", ""), dict(arguments.get("tool_input", {}))
        # This guard is independent of the learner's teaching-hook toggle.
        if evidence.lesson == 4 and name in {"Write", "Edit"}:
            try:
                supported_target(evidence.root, value.get("file_path"))
                allowed = (
                    name != "Write"
                    or isinstance(value.get("content"), str)
                    and len(value["content"]) <= 2000
                )
            except (ValueError, OSError):
                allowed = False
                evidence.unsupported = True
        else:
            allowed, _ = decide(evidence.root, name, value)
        if not allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "The immutable fixture boundary refused this input.",
                }
            }
        if not selected.get("pre_hook", True):
            return {}
        behavior = selected.get("behavior", "observe")
        await emit(
            Event(
                kind="hook",
                data={"tool": name, "tool_use_id": call_id, "behavior": behavior, "input": value},
            )
        )
        # Permission lesson must reach can_use_tool; an allow decision here would skip it.
        if evidence.lesson == 4:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "Resolve the owned fixture operation through the host callback.",
                }
            }
        if behavior == "block":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Selected blocking experiment.",
                }
            }
        if behavior == "rewrite" and name == "Read":
            value["file_path"] = str(inside(evidence.root, "alternate.txt"))
            return cast(
                HookJSONOutput,
                {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": value}},
            )
        return {}

    config: dict[Any, list[HookMatcher]] = {"PreToolUse": [HookMatcher(hooks=[pre])]}
    if selected.get("post_hook", True):
        config["PostToolUse"] = [HookMatcher(hooks=[post_tool_hook(audit)])]
    return config


def live_permission(evidence: Evidence, request: RunRequest, ask: Ask) -> Callable[..., Any]:
    async def permission(name: str, arguments: dict[str, Any], context: Any) -> Any:
        return await permission_decision(
            evidence, request, name, arguments, getattr(context, "tool_use_id", None), ask
        )

    return permission


def tool_policy(
    request: RunRequest, root: Path, name: str, arguments: dict[str, Any]
) -> tuple[bool, str]:
    selected = inputs(3, request.lesson_options).model_dump()
    if not selected["permit_tool"] or name != selected["tool"]:
        return False, "The selected host policy denies this tool."
    if name == "Bash":
        return arguments.get(
            "command"
        ) == "python --version", "Only the fixed python --version command is supported."
    return decide(root, name, arguments)


def record_call(evidence: Evidence, name: str, arguments: dict[str, Any], identifier: str) -> None:
    evidence.calls.append(
        {
            "id": identifier,
            "name": name,
            "arguments": arguments,
            "run_id": evidence.run_id,
            "parent_tool_use_id": None,
        }
    )


async def local_options(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    return {
        "note": "None means the SDK option is omitted. The host deadline still applies; an omitted budget threshold is not a billing cap."
    }


async def local_tools(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    selected = evidence.selected
    name = selected["tool"]
    arguments = (
        {"command": "python --version"}
        if name == "Bash"
        else {"file_path": "notes.txt"}
        if name == "Read"
        else {"path": ".", "pattern": "*.txt" if name == "Glob" else "Python"}
    )
    record_call(evidence, name, arguments, "fixture-tool-1")
    allowed, reason = tool_policy(request, evidence.root, name, arguments)
    before = fingerprint(evidence.root, "notes.txt")
    result: Any = None
    if allowed:
        if name == "Read":
            result = inside(evidence.root, "notes.txt").read_text(encoding="utf-8")
        elif name == "Glob":
            result = sorted(path.name for path in evidence.root.glob("*.txt") if path.is_file())
        elif name == "Grep":
            result = [
                line
                for line in inside(evidence.root, "notes.txt")
                .read_text(encoding="utf-8")
                .splitlines()
                if "Python" in line
            ]
        else:
            result = (
                await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "--version"],
                    cwd=evidence.root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
            ).stdout.strip()
    evidence.results.append(
        {"id": "fixture-tool-1", "run_id": evidence.run_id, "is_error": not allowed}
    )
    return {
        "tool_result": result,
        "policy": reason,
        "permitted": allowed,
        "before_hash": before,
        "after_hash": fingerprint(evidence.root, "notes.txt"),
    }


async def local_permissions(
    evidence: Evidence, request: RunRequest, ask: Ask | None = None
) -> dict[str, Any]:
    arguments = {"file_path": evidence.selected["target"], "content": evidence.selected["content"]}
    record_call(evidence, "Write", arguments, "fixture-write-1")
    decision = await permission_decision(
        evidence, request, "Write", arguments, "fixture-write-1", ask
    )
    if isinstance(decision, PermissionResultAllow):
        updated = decision.updated_input or arguments
        target = supported_target(evidence.root, updated["file_path"])
        inside(evidence.root, target).write_text(updated["content"], encoding="utf-8")
    evidence.results.append(
        {
            "id": "fixture-write-1",
            "run_id": evidence.run_id,
            "is_error": isinstance(decision, PermissionResultDeny),
        }
    )
    return {
        "files_after": {
            name: inside(evidence.root, name).read_text(encoding="utf-8")
            if inside(evidence.root, name).is_file()
            else None
            for name in (evidence.selected["target"], "approved.txt")
        }
    }


async def local_calculator(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    arguments: dict[str, Any] = {"a": evidence.selected["a"], "b": evidence.selected["b"]}
    if request.scenario == "invalid-arguments":
        arguments["a"] = True
    record_call(evidence, "mcp__lesson__add", arguments, "fixture-add-1")
    try:
        parsed = Calculation.model_validate(arguments)
    except ValidationError as exc:
        return {
            "rejected_before_handler": True,
            "validation_errors": exc.errors(include_context=False, include_input=False),
            "handler_count": 0,
        }
    result = parsed.a + parsed.b
    evidence.handlers.append(
        {
            "name": "mcp__lesson__add",
            "arguments": parsed.model_dump(),
            "result": result,
            "run_id": evidence.run_id,
        }
    )
    evidence.results.append({"id": "fixture-add-1", "is_error": False, "run_id": evidence.run_id})
    if request.scenario == "ambiguous-handler":
        evidence.handlers.append(dict(evidence.handlers[0]))
    return {
        "handler_sum": result,
        "handler_count": len(evidence.handlers),
        "input_schema": Calculation.model_json_schema(),
    }


async def local_sessions(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    from claude_agent_sdk import ClaudeSDKClient, ResultMessage

    from agent_lab.scripted_cli import ScriptedCLI

    first = ScriptedCLI([["Recorded first response"], ["Recorded follow-up response"]])
    first_id: str | None = None
    strategy = "fresh" if request.scenario == "fresh-session" else evidence.selected["strategy"]
    evidence.selected["strategy"] = strategy

    async def consume(client: Any) -> None:
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                evidence.terminals.append(dataclasses.asdict(message))

    async with ClaudeSDKClient(ClaudeAgentOptions(), transport=first) as client:
        await client.query(request.prompt)
        await consume(client)
        first_id = evidence.terminals[-1]["session_id"]
        evidence.initialized.append({"session_id": first_id})
        if strategy == "same-client":
            await client.query(request.follow_up)
            await consume(client)
    if strategy != "same-client":
        assert isinstance(first_id, str)
        second = ScriptedCLI([["Recorded second-client response"]])
        second.session_id = first_id if strategy == "resume" else "fresh-scripted-session"
        evidence.sent_sessions.append(first_id if strategy == "resume" else None)
        async with ClaudeSDKClient(
            ClaudeAgentOptions(resume=first_id if strategy == "resume" else None), transport=second
        ) as client:
            await client.query(request.follow_up)
            await consume(client)
        evidence.initialized.append({"session_id": second.session_id})
    return {
        "transport": "official client with scripted CLI fixtures; no recalled model answer",
        "previous_session": first_id,
        "strategy": strategy,
        "lifecycle": first.lifecycle,
        "turn_inputs": [request.prompt, request.follow_up],
    }


async def local_hooks(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    async def emit(event: Event) -> None:
        evidence.observe(event)
        events.append({"kind": event.kind, **event.data})

    inside(evidence.root, "alternate.txt").write_text(
        "An alternate owned fixture.\n", encoding="utf-8"
    )
    config = experiment_hooks(evidence, emit)
    arguments = {"file_path": "notes.txt"}
    record_call(evidence, "Read", dict(arguments), "fixture-hook-1")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": arguments,
        "session_id": "fixture-session",
    }
    response: dict[str, Any] = {}
    if config.get("PreToolUse"):
        response = await call_hook(config["PreToolUse"][0].hooks[0], payload, "fixture-hook-1")
    decision = response.get("hookSpecificOutput", {})
    allowed = decision.get("permissionDecision") != "deny"
    actual_input = decision.get("updatedInput", arguments)
    actual_path = Path(actual_input["file_path"])
    if actual_path.is_absolute():
        actual_path = actual_path.relative_to(evidence.root.resolve())
    text = inside(evidence.root, str(actual_path)).read_text(encoding="utf-8") if allowed else None
    evidence.results.append(
        {"id": "fixture-hook-1", "is_error": not allowed, "run_id": evidence.run_id}
    )
    if allowed and config.get("PostToolUse") and request.scenario != "missing-hook":
        await call_hook(
            config["PostToolUse"][0].hooks[0],
            {
                **payload,
                "hook_event_name": "PostToolUse",
                "tool_input": actual_input,
                "tool_response": text,
            },
            "fixture-hook-1",
        )
    return {
        "registered_events": list(config),
        "hook_events": events,
        "pre_use_output": response,
        "actual_input": actual_input,
        "read_result": text,
    }


async def local_agents(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    record_call(
        evidence,
        "Agent",
        {"subagent_type": "reviewer", "prompt": "Inspect notes.txt", "run_in_background": False},
        "fixture-agent-1",
    )
    read = evidence.selected["worker_tools"] == "read-only"
    text = (
        inside(evidence.root, "notes.txt").read_text(encoding="utf-8")
        if read
        else "The worker has no file tools."
    )
    evidence.messages.append(
        {"message_class": "AssistantMessage", "parent_tool_use_id": "fixture-agent-1"}
    )
    evidence.results.append({"id": "fixture-agent-1", "is_error": False, "run_id": evidence.run_id})
    return {
        "worker_read_fixture": read,
        "recorded_worker_report": text,
        "worker_note": "Local reviewer function and recorded delegation identities, not a model worker.",
    }


async def local_prompts(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    return {
        "fixed_user_question": request.prompt,
        "project_file": inside(evidence.root, "CLAUDE.md").read_text(encoding="utf-8")
        if evidence.selected["variant"] == "project"
        else None,
        "usage": None,
        "usage_note": "No model usage offline. The boundary marker alone does not demonstrate caching or prompt adherence.",
    }


async def local_structured(evidence: Evidence, request: RunRequest) -> dict[str, Any]:
    payload = (
        evidence.selected["payload"]
        if request.scenario != "schema-error"
        else {"summary": "", "next_steps": []}
    )
    try:
        parsed = Summary.model_validate(payload)
        evidence.validated.append(parsed.model_dump())
        evidence.terminals[-1]["structured_output"] = parsed.model_dump()
        result: dict[str, Any] = {"accepted_structured_value": parsed.model_dump()}
    except ValidationError as exc:
        result = {"schema_errors": exc.errors(include_context=False, include_input=False)}
    if request.scenario == "stop-control":
        from claude_agent_sdk import AssistantMessage, ClaudeSDKClient

        from agent_lab.scripted_cli import ScriptedCLI

        transport = ScriptedCLI(
            [["first ", "second ", "third "], ["continued response"]], chunk_delay=0.01
        )
        chunks = 0
        async with ClaudeSDKClient(ClaudeAgentOptions(), transport=transport) as client:
            await client.query("Stream the fixture.")
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    chunks += 1
                    if evidence.selected["stop_experiment"] == "abort":
                        break
                    await client.interrupt()
            if evidence.selected["stop_experiment"] == "interrupt":
                await client.query("Continue the same scripted session.")
                async for _ in client.receive_response():
                    pass
        result["stop_comparison"] = {
            "operation": evidence.selected["stop_experiment"],
            "received_chunks": chunks,
            "control_requests": [
                m["request"]["subtype"]
                for m in transport.received
                if m["type"] == "control_request"
            ],
            "lifecycle": transport.lifecycle,
            "continued": evidence.selected["stop_experiment"] == "interrupt",
            "source": "official client with scripted transport",
        }
        evidence.validated.clear()  # This is a separate experiment, not a passing schema check.
    return result


LOCAL_EXPERIMENTS: dict[int, Callable[..., Awaitable[dict[str, Any]]]] = {
    2: local_options,
    3: local_tools,
    4: local_permissions,
    5: local_calculator,
    6: local_sessions,
    7: local_hooks,
    8: local_agents,
    9: local_prompts,
    10: local_structured,
    11: local_skills,
}


async def run_local(
    root: Path, request: RunRequest, lesson: Lesson, ask: Ask | None = None
) -> dict[str, Any]:
    request = lesson_request(lesson.id, request)
    if lesson.id == 49:
        from agent_lab.headless_lab import local as local_headless

        result = await local_headless(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 48:
        from agent_lab.hardening_lab import local as local_hardening

        result = await local_hardening(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 47:
        from agent_lab.orchestra_lab import local as local_orchestra

        result = await local_orchestra(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 46:
        from agent_lab.cache_lab import local as local_cache

        result = await local_cache(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 45:
        from agent_lab.cloud_lab import local as local_cloud

        result = await local_cloud(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 44:
        from agent_lab.telemetry_lab import local as local_telemetry

        result = await local_telemetry(root, request)
        result["experiment"]["expected_check"] = "passed" if result["experiment_passed"] else "needs-review"
        return result
    if lesson.id == 43:
        from agent_lab.remote_mcp_lab import local as local_remote_mcp

        return await local_remote_mcp(root, request)
    if lesson.id == 42:
        from agent_lab.web_tools_lab import local as local_web_tools

        return await local_web_tools(root, request)
    if lesson.id == 41:
        from agent_lab.client_lifecycle_lab import local as local_client_lifecycle

        return await local_client_lifecycle(root, request)
    if lesson.id == 40:
        from agent_lab.drops_lab import local as local_drops

        return await local_drops(root, request)
    if lesson.id == 39:
        from agent_lab.config_root_lab import local

        return await local(root, request)
    if lesson.id == 38:
        from agent_lab.suggestions_lab import local_suggestions

        return await local_suggestions(root, request)
    if lesson.id == 37:
        from agent_lab.permission_gate_lab import local_gate

        return await local_gate(root, request)
    if lesson.id == 36:
        from agent_lab.process_spawning_lab import local_spawn

        return await local_spawn(root, request)
    if lesson.id == 35:
        from agent_lab.session_store_lab import local_store

        return await local_store(root, request)
    if lesson.id == 34:
        from agent_lab.styles_lab import local_styles

        return await local_styles(root, request)
    if lesson.id == 33:
        from agent_lab.elicitation_lab import local_elicitation

        return await local_elicitation(root, request)
    if lesson.id == 32:
        from agent_lab.plan_lab import local_plan_mode

        return await local_plan_mode(root, request)
    if lesson.id == 31:
        from agent_lab.question_lab import local_question

        return await local_question(root, request)
    if lesson.id == 30:
        from agent_lab.todo_lab import local_todos

        return await local_todos(root, request)
    if lesson.id == 29:
        from agent_lab.image_input_lab import local_image_input

        return await local_image_input(root, request)
    if lesson.id == 28:
        from agent_lab.retry_lab import local_retry

        return await local_retry(root, request)
    if lesson.id == 27:
        from agent_lab.background_lab import local_background

        return await local_background(root, request)
    if lesson.id == 26:
        from agent_lab.control_lab import local_control

        return await local_control(root, request)
    if lesson.id == 25:
        from agent_lab.compaction_lab import local_compaction

        return await local_compaction(root, request)
    if lesson.id == 24:
        from agent_lab.harness_lab import local_harness

        return await local_harness(root, request)
    if lesson.id == 23:
        from agent_lab.plugin_lab import local_plugin

        return await local_plugin(root, request)
    if lesson.id == 22:
        from agent_lab.project_memory import local_memory

        return await local_memory(root, request)
    if lesson.id == 21:
        from agent_lab.slash_commands import local_commands

        return await local_commands(root, request)
    if lesson.id == 20:
        from agent_lab.hooks_deep import local_hooks_deep

        return await local_hooks_deep(root, request)
    if lesson.id == 19:
        from agent_lab.session_catalog import local_catalog

        return await local_catalog(root, request)
    if lesson.id == 18:
        from agent_lab.sandbox_lab import local_sandbox

        return await local_sandbox(root, request)
    if lesson.id == 17:
        from agent_lab.checkpointing import local_checkpoint

        return await local_checkpoint(root, request)
    if lesson.id == 16:
        from agent_lab.settings_lab import local_settings

        return await local_settings(root, request)
    if lesson.id == 15:
        from agent_lab.usage import local_usage

        return await local_usage(root, request)
    if lesson.id == 14:
        from agent_lab.thinking import local_thinking

        return await local_thinking(root, request)
    if lesson.id == 13:
        from agent_lab.mcp_lab import local_mcp

        return await local_mcp(root, request)
    if lesson.id == 12:
        from agent_lab.streaming import local_streaming

        return await local_streaming(root, request)
    selected = inputs(lesson.id, request.lesson_options).model_dump()
    evidence = Evidence(
        lesson.id,
        root.parent.name,
        root,
        selected,
        "local host effects plus explicitly recorded SDK correlation fixtures",
        requested_turns=request.max_turns,
        requested_budget=request.max_budget_usd,
    )
    options = ClaudeAgentOptions(
        tools=["Read", "Glob", "Grep"]
        if lesson.id in {3, 4, 7}
        else ["Agent"]
        if lesson.id == 8
        else [],
        setting_sources=[],
        strict_mcp_config=True,
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        output_format={"type": "json_schema", "schema": Summary.model_json_schema()}
        if lesson.id == 10
        else None,
    )
    evidence.configured = configure(options, lesson, request, root)
    evidence.initialized = [{"session_id": "fixture-session", "tools": options.tools}]
    evidence.terminals = [
        {
            "subtype": "success",
            "is_error": False,
            "session_id": "fixture-session",
            "total_cost_usd": 0,
        }
    ]
    if lesson.id == 6:
        evidence.initialized.clear()
        evidence.terminals.clear()
    experiment = LOCAL_EXPERIMENTS[lesson.id]
    actual = (
        await experiment(evidence, request, ask)
        if lesson.id == 4
        else await experiment(evidence, request)
    )
    if request.scenario == "missing-evidence":
        evidence.terminals.clear()
    elif request.scenario == "wrong-identity":
        if lesson.id == 4 and evidence.decisions:
            evidence.decisions[0]["run_id"] = "different-run"
        elif lesson.id == 6:
            evidence.terminals[-1]["session_id"] = "different-session"
        elif lesson.id in {2, 9, 10}:
            evidence.terminals[-1]["session_id"] = "different-session"
        elif evidence.results:
            evidence.results[0]["id"] = "unmatched-call"
    elif request.scenario == "limit-error":
        evidence.terminals[-1].update(subtype="error_max_turns", is_error=True)
    report = evidence.report()
    report["validated_prompt"] = request.prompt
    report["local_effects"] = actual
    report["scenario"] = request.scenario
    report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
    return {"experiment": report, "experiment_passed": report["experiment_passed"]}


def source_excerpt(lesson_id: int) -> tuple[str, str, int]:
    from agent_lab.background_lab import local_background
    from agent_lab.checkpointing import local_checkpoint
    from agent_lab.client_lifecycle_lab import local as local_client_lifecycle
    from agent_lab.cloud_lab import local as local_cloud
    from agent_lab.compaction_lab import local_compaction
    from agent_lab.config_root_lab import local as local_config_root
    from agent_lab.control_lab import local_control
    from agent_lab.drops_lab import local as local_drops
    from agent_lab.elicitation_lab import local_elicitation
    from agent_lab.harness_lab import local_harness
    from agent_lab.hooks_deep import local_hooks_deep
    from agent_lab.image_input_lab import local_image_input
    from agent_lab.mcp_lab import local_mcp
    from agent_lab.permission_gate_lab import local_gate
    from agent_lab.plan_lab import local_plan_mode
    from agent_lab.plugin_lab import local_plugin
    from agent_lab.process_spawning_lab import local_spawn
    from agent_lab.project_memory import local_memory
    from agent_lab.question_lab import local_question
    from agent_lab.remote_mcp_lab import local as local_remote_mcp
    from agent_lab.retry_lab import local_retry
    from agent_lab.sandbox_lab import local_sandbox
    from agent_lab.session_catalog import local_catalog
    from agent_lab.session_store_lab import local_store
    from agent_lab.settings_lab import local_settings
    from agent_lab.slash_commands import local_commands
    from agent_lab.streaming import local_streaming
    from agent_lab.styles_lab import local_styles
    from agent_lab.suggestions_lab import local_suggestions
    from agent_lab.telemetry_lab import local as local_telemetry
    from agent_lab.thinking import local_thinking
    from agent_lab.todo_lab import local_todos
    from agent_lab.usage import local_usage
    from agent_lab.web_tools_lab import local as local_web_tools

    function = (
        local_cloud
        if lesson_id == 45
        else local_telemetry
        if lesson_id == 44
        else local_remote_mcp
        if lesson_id == 43
        else local_web_tools
        if lesson_id == 42
        else local_client_lifecycle
        if lesson_id == 41
        else local_drops
        if lesson_id == 40
        else local_config_root
        if lesson_id == 39
        else local_suggestions
        if lesson_id == 38
        else local_gate
        if lesson_id == 37
        else local_spawn
        if lesson_id == 36
        else local_store
        if lesson_id == 35
        else local_styles
        if lesson_id == 34
        else local_elicitation
        if lesson_id == 33
        else local_plan_mode
        if lesson_id == 32
        else local_question
        if lesson_id == 31
        else local_todos
        if lesson_id == 30
        else local_image_input
        if lesson_id == 29
        else local_retry
        if lesson_id == 28
        else local_background
        if lesson_id == 27
        else local_control
        if lesson_id == 26
        else local_compaction
        if lesson_id == 25
        else local_harness
        if lesson_id == 24
        else local_plugin
        if lesson_id == 23
        else local_memory
        if lesson_id == 22
        else local_commands
        if lesson_id == 21
        else local_hooks_deep
        if lesson_id == 20
        else local_catalog
        if lesson_id == 19
        else local_sandbox
        if lesson_id == 18
        else local_checkpoint
        if lesson_id == 17
        else local_settings
        if lesson_id == 16
        else local_usage
        if lesson_id == 15
        else local_thinking
        if lesson_id == 14
        else local_mcp
        if lesson_id == 13
        else local_streaming
        if lesson_id == 12
        else LOCAL_EXPERIMENTS[lesson_id]
    )
    lines, start = inspect.getsourcelines(function)
    path = Path(inspect.getfile(function)).relative_to(Path(__file__).resolve().parent.parent)
    return path.as_posix(), "".join(lines), start


def source_sections(lesson_id: int) -> list[dict[str, Any]]:
    if lesson_id == 52:
        from agent_lab.api_evals import eval_code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Compare measured trials", "Calibrate the heuristic",
                                        "Promote a retained baseline"), eval_code(), strict=True)]
    if lesson_id == 51:
        from agent_lab.api_offline import offline_code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Sequential host assertions", "Injected host consumer",
                                        "Complete-suite evidence"), offline_code(), strict=True)]
    if lesson_id == 50:
        from agent_lab.api_desk import desk_code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Scope the saved records", "Settle one approval",
                                        "Close into CRM"), desk_code(), strict=True)]
    if lesson_id == 49:
        from agent_lab.api_headless import code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Run a bounded process", "Map an explicit CI code",
                                        "Supervise a local worker"), code(), strict=True)]
    if lesson_id == 48:
        from agent_lab.api_hardening import code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Scrub child environment", "Admit fixed tools",
                                        "Rewrite known output"), code(), strict=True)]
    if lesson_id == 47:
        from agent_lab.api_orchestra import code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Queue one worker", "Check fixture truth",
                                        "Gate an analyst stop"), code(), strict=True)]
    if lesson_id == 46:
        from agent_lab.api_cache import code

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Parse exact usage", "Locate breakpoints",
                                        "Join two turns"), code(), strict=True)]
    if lesson_id == 45:
        from agent_lab.api_cloud import source_excerpts

        return [{"title": title, "path": item["file"], "start": item["start_line"],
                 "end": item["end_line"], "code": item["code"] + "\n",
                 "question": item["question"]}
                for title, item in zip(("Verify signed bytes", "Translate one request",
                                        "Join native evidence"), source_excerpts(), strict=True)]
    if lesson_id == 44:
        import json

        from agent_lab.config import ROOT

        script = json.loads((ROOT / "agent_lab/content/lesson_44_narration.json").read_text(encoding="utf-8"))
        questions = (
            "Which request belongs to this collector and lane?",
            "How do delta and cumulative values differ?",
            "What proves the native subprocess exported each signal?",
        )
        return [{"title": section["title"], "path": section["path"],
                 "start": section["start_line"], "end": section["end_line"],
                 "code": "\n".join((ROOT / section["path"]).read_text(encoding="utf-8").splitlines()[
                     section["start_line"] - 1:section["end_line"]]) + "\n",
                 "question": questions[index]}
                for index, section in enumerate(script["sections"])]
    if lesson_id == 43:
        import json

        from agent_lab.config import ROOT

        script = json.loads((ROOT / "agent_lab/content/lesson_43_narration.json").read_text(encoding="utf-8"))
        questions = (
            "Why do reports keep a credential label instead of the bearer value?",
            "Which control updates the connected server before reconnect?",
            "How do two receipts establish same-client credential rotation?",
        )
        return [{"title": section["title"], "path": section["path"],
                 "start": section["start_line"], "end": section["end_line"],
                 "code": "\n".join((ROOT / section["path"]).read_text(encoding="utf-8").splitlines()[
                     section["start_line"] - 1:section["end_line"]]) + "\n",
                 "question": questions[index]}
                for index, section in enumerate(script["sections"])]
    from agent_lab.skills import configure_skills

    sections = []
    functions: tuple[tuple[str, Callable[..., Any], str], ...] = (
        (
            (
                "Actual SDK configuration",
                configure_skills if lesson_id == 11 else configure,
                "Which selected values become actual SDK options?",
            ),
            (
                "Selected local experiment",
                LOCAL_EXPERIMENTS[lesson_id],
                "Which host operation executes, and which evidence is a labelled fixture?",
            ),
            (
                "Bounded evidence evaluator",
                Evidence.report,
                "Which identities and terminal evidence does this lesson require?",
            ),
        )
        if lesson_id not in {12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44}
        else ()
    )
    if lesson_id == 12:
        from agent_lab.streaming import StreamSession, execute_stream, stream_report

        functions = (
            (
                "Wakeable input queue",
                StreamSession.messages,
                "How does closing an idle queue wake the generator?",
            ),
            (
                "One owned SDK connection",
                execute_stream,
                "Which observations establish a yielded input, a terminal result and complete closure?",
            ),
            (
                "Bounded evidence evaluator",
                stream_report,
                "Why are application handles and SDK identities checked separately?",
            ),
        )
    if lesson_id == 13:
        from agent_lab.mcp_lab import local_mcp, server_config

        functions = (
            (
                "Owned server configuration",
                server_config,
                "Which values select a child process, loopback server or SDK server?",
            ),
            (
                "Real transport and inventory experiment",
                local_mcp,
                "Which effects really execute and which agent identities are recorded?",
            ),
            (
                "Bounded evidence evaluator",
                Evidence.report,
                "Why is a configured server alone insufficient?",
            ),
        )
    if lesson_id == 14:
        from agent_lab.thinking import Lane, lane_options

        functions = (
            (
                "Requested SDK options",
                lane_options,
                "Which requested settings actually enter each fresh query?",
            ),
            (
                "Actual Stop observer",
                Lane.stop,
                "Which identity fields connect this observation to its parent turn?",
            ),
            (
                "Observed evidence and unknown metrics",
                Lane.report,
                "Why is unknown effort or usage different from a measured zero?",
            ),
        )
    if lesson_id == 15:
        from agent_lab.usage import UsageMeter, UsageObservation, usage_options

        functions = (
            ("Requested limits and planning guidance", usage_options, "Which fields stop a run, and which only guide planning?"),
            ("Cumulative cost meter", UsageMeter.observe, "Why subtract before updating the baseline?"),
            ("Final accounting criterion", UsageObservation.report, "Why are intermediate usage and unknown counters insufficient?"),
        )
    if lesson_id == 16:
        from agent_lab.settings_lab import probe_environment, settings_options, settings_report

        functions = (
            ("Owned settings and SDK options", settings_options, "Which sources are explicitly enabled?"),
            ("Actual child environment probe", probe_environment, "What is observed without exposing host secrets?"),
            ("Bounded configuration criterion", settings_report, "Why does this not prove CLI precedence?"),
        )
    if lesson_id == 17:
        from agent_lab.checkpointing import (
            checkpoint_options,
            checkpoint_report,
            execute_checkpoint,
        )

        functions = (
            ("Checkpoint SDK options", checkpoint_options, "Which options enable backups and replayed UUIDs?"),
            ("Owned edit and native rewind", execute_checkpoint, "Which UUID is sent to rewind_files and when?"),
            ("Observed restoration criterion", checkpoint_report, "Why is an acknowledgement insufficient without a changed and restored hash?"),
        )
    if lesson_id == 18:
        from agent_lab.sandbox_lab import boundary_probe, sandbox_options, sandbox_report

        functions = (
            ("Bounded SDK tool policy", sandbox_options, "Why is Bash absent from policy comparisons?"),
            ("Actual process counterexample", boundary_probe, "Why can this host child read the synthetic neighbor?"),
            ("Observed boundary criterion", sandbox_report, "Which matching decision and result prove the selected policy outcome?"),
        )
    if lesson_id == 19:
        from agent_lab.session_catalog import catalog_options, catalog_report
        from agent_lab.session_catalog_child import operate

        functions = (
            ("Owned SDK session", catalog_options, "Why are model tools and filesystem settings disabled?"),
            ("Child-only owned catalog operations", operate, "Why is this function called only in an isolated child with an owned session and directories?"),
            ("Observed persistence criterion", catalog_report, "Which persistence and mutation effects must actually match?"),
        )
    if lesson_id == 20:
        from agent_lab.hooks_deep import HookObservation

        functions = (
            ("Contained teaching decisions", HookObservation.teaching, "How do rewrites and callback faults stay inside the host boundary?"),
            ("Actual SDK hook registration", HookObservation.hooks, "Which matchers and lifecycle channels are registered?"),
            ("Correlated lifecycle criterion", HookObservation.report, "Why are a hook log and a successful answer insufficient on their own?"),
        )
    if lesson_id == 21:
        from agent_lab.slash_commands import command_options, command_report, prepare

        functions = (
            ("Owned command template", prepare, "Which exact project file and note are hashed before invocation?"),
            ("SDK discovery options", command_options, "Which setting source enables discovery and which tools remain available?"),
            ("Correlated invocation criterion", command_report, "Why are a command file and a successful answer alone insufficient?"),
        )
    if lesson_id == 22:
        from agent_lab.project_memory import memory_options, memory_report, prepare_memory

        functions = (
            ("Owned project instruction", prepare_memory, "Which host-authored CLAUDE.md is hashed?"),
            ("SDK settings and prompt mode", memory_options, "Which options load the project file and disable automatic memory?"),
            ("Behavioral comparison criterion", memory_report, "What can the fixed-answer comparison establish without the resolved system prompt?"),
        )
    if lesson_id == 23:
        from agent_lab.plugin_lab import plugin_options, plugin_report, prepare_plugin

        functions = (
            ("Owned plugin files", prepare_plugin, "Which manifest, commands and skill are created by the host?"),
            ("Explicit SDK plugin options", plugin_options, "Which trusted local plugin and tool catalog are configured?"),
            ("Discovery and invocation criterion", plugin_report, "What correlates the SDK command or Skill behavior with the owned plugin?"),
        )
    if lesson_id == 24:
        from agent_lab.harness_lab import harness_options, harness_report, host_gate

        functions = (
            ("Structured SDK proposal", harness_options, "Why is schema output still a proposal?"),
            ("Strict host gate", host_gate, "Which graph and exact owned-file rules run before workers?"),
            ("Observed execution criterion", harness_report, "How are accepted, rejected and review-only outcomes distinguished?"),
        )
    if lesson_id == 25:
        from agent_lab.compaction_lab import bounded_result, compaction_options, compaction_report

        functions = (
            ("Bounded MCP result", bounded_result, "Where is the exact delivery bound and marker computed?"),
            ("SDK tool and compaction hook options", compaction_options, "Which tool and PreCompact observer are registered?"),
            ("Correlated context criterion", compaction_report, "Why must the callback and SDK call/result agree?"),
        )
    if lesson_id == 26:
        from agent_lab.control_lab import control_options, control_report, execute_control

        functions = (
            ("Owned SDK control configuration", control_options, "Which tools, model and streaming option are selected?"),
            ("One connected control sequence", execute_control, "When are controls sent relative to the two turns or interrupt?"),
            ("Observed lifecycle criterion", control_report, "Which acknowledgements, session IDs and terminal outcomes prove the selected control?"),
        )
    if lesson_id == 27:
        from agent_lab.background_lab import (
            background_options,
            background_report,
            execute_background,
        )

        functions = (
            ("Bounded SDK turn", background_options, "Why are model tools disabled while the host watcher runs?"),
            ("Owned watcher lifecycle", execute_background, "Where does the host cancel or release and await the task?"),
            ("Cleanup criterion", background_report, "Which task and SDK observations establish complete cleanup?"),
        )
    if lesson_id == 28:
        from agent_lab.retry_lab import refund_attempt, retry_options, retry_report

        functions = (
            ("Idempotent in-memory effect", refund_attempt, "When is the fixed refund key applied, and why only once?"),
            ("Owned SDK MCP tool", retry_options, "Which tool and session settings are allowed?"),
            ("Bounded retry criterion", retry_report, "Which correlated results and decisions distinguish recovery, rejection and exhaustion?"),
        )
    if lesson_id == 29:
        from agent_lab.image_input_lab import image_report, image_turn, validated_image

        functions = (
            ("Owned PNG validation", validated_image, "Which byte signature and dimensions must match the MIME type?"),
            ("Typed SDK image message", image_turn, "Where are the image and text blocks placed in the user message?"),
            ("Observed image criterion", image_report, "Which file hashes, sent block and model answer are checked?"),
        )
    if lesson_id == 30:
        from agent_lab.todo_lab import todo_options, todo_report, validate_todos

        functions = (
            ("Host transition validator", validate_todos, "Which status changes and task identities can pass?"),
            ("TodoWrite hook registration", todo_options, "How are the pre and post callbacks attached to the SDK tool?"),
            ("Correlated ledger criterion", todo_report, "Why do only accepted and completed tool uses commit state?"),
        )
    if lesson_id == 31:
        from agent_lab.question_lab import question_options, question_report, validate_question

        functions = (
            ("Exact question validator", validate_question, "Which shape and fixed options can reach the answer callback?"),
            ("AskUserQuestion SDK configuration", question_options, "Where is can_use_tool registered without a bypassing allow rule?"),
            ("Correlated answer criterion", question_report, "Which call, result, callback, and session observations must agree?"),
        )
    if lesson_id == 32:
        from agent_lab.plan_lab import plan_options, plan_prompt, plan_report

        functions = (
            ("Plan-mode SDK configuration", plan_options, "Where is permission_mode set to plan with no model tools?"),
            ("Fixed proposal request", plan_prompt, "Which exact plan does the host ask the model to propose?"),
            ("Mode and execution criterion", plan_report, "Why must validation and approval precede the mode switch and workers?"),
        )
    if lesson_id == 33:
        from agent_lab.elicitation_lab import elicitation_options, elicitation_report, known_request

        functions = (
            ("Owned MCP form boundary", known_request, "Which server and form fields can receive a host answer?"),
            ("Owned SDK-to-MCP bridge", elicitation_options, "Which SDK tool invokes the host's MCP client callback?"),
            ("Correlated response criterion", elicitation_report, "Which callback, action, call/result and session observations must agree?"),
        )
    if lesson_id == 34:
        from agent_lab.styles_lab import prepare_style, style_options, style_report

        functions = (
            ("Owned style and settings files", prepare_style, "Which project files select the output style?"),
            ("Project setting source control", style_options, "Where does the SDK opt into project settings without adding tools?"),
            ("Style behavior criterion", style_report, "Which marker, file hashes and SDK session observations must agree?"),
        )
    if lesson_id == 35:
        from agent_lab.observed_session_store import ObservedSessionStore
        from agent_lab.session_store_lab import store_report
        from agent_lab.sqlite_session_store import SQLiteSessionStore

        functions = (
            ("Observed SDK mirror calls", ObservedSessionStore.append, "How are append timing and errors observed without replacing the store?"),
            ("Transactional SQLite mirror", SQLiteSessionStore._append, "Where are UUID deduplication and summary folding committed?"),
            ("UUID coverage and resume criterion", store_report, "Which local UUID, mirror error, summary and session observations must agree?"),
        )
    if lesson_id == 36:
        from agent_lab.process_spawning_lab import FrameTap, probe_child, spawn_report

        functions = (
            ("Incremental protocol framing", FrameTap.feed, "How do partial UTF-8 chunks become complete JSONL frames without changing forwarded bytes?"),
            ("Owned child lifecycle", probe_child, "Which argv, cwd, stream and cleanup controls bind the process?"),
            ("Correlated host and SDK criterion", spawn_report, "Why must both the host child and SDK terminal succeed?"),
        )
    if lesson_id == 37:
        from agent_lab.permission_gate_lab import GateState, gate_report, prepared_round_trip

        functions = (
            ("Correlated host decision", GateState.decide, "Which identities and exact Write arguments must match before a decision?"),
            ("Actual MCP client receipt", prepared_round_trip, "Where does the owned stdio MCP server receive the request?"),
            ("Gate and disk criterion", gate_report, "Which process, SDK and fresh file observations are required?"),
        )
    if lesson_id == 38:
        from agent_lab.suggestions_lab import SuggestionSession, SuggestionTap, evaluate

        functions = (
            ("Raw suggestion relay", SuggestionTap.read_messages, "Where is prompt_suggestion observed after the typed SDK parser skips it?"),
            ("Validated send queue", SuggestionSession.send, "Which input limits and busy-turn facts are recorded?"),
            ("Turn and suggestion criterion", evaluate, "Which result, session, order and closure observations establish the check?"),
        )
    if lesson_id == 39:
        from agent_lab.config_root_lab import dry_flags, fixture
        from agent_lab.config_root_lab import evaluate as evaluate_config_root

        functions = (
            ("Owned Git fixture", fixture, "How are trusted, branch and docs worktrees kept inside one run?"),
            ("Inert SDK argument capture", dry_flags, "Where is the optional project-config-root flag serialized without a real CLI?"),
            ("Origin evidence criterion", evaluate_config_root, "Which initialization, hook, hash and closure observations must agree?"),
        )
    if lesson_id == 40:
        from agent_lab.drops_lab import active_chain, cases_report, turns

        functions = (
            ("Active transcript ancestry", active_chain, "How are inactive physical branches excluded and invalid parent links refused?"),
            ("Logical turns and queued attachments", turns, "Which user prompts start turns and where does the queued command attach?"),
            ("Exact and unsafe guard criterion", cases_report, "Why must a typed refusal and independently verified fork agree?"),
        )
    if lesson_id == 41:
        from agent_lab.client_lifecycle_lab import _one_turn, base, resume

        functions = (
            ("One identified Python client turn", _one_turn, "Which SDK result ends one turn?"),
            ("One connected client", base, "How do three turns share a session before disconnect?"),
            ("Owned resume", resume, "How is the saved session ID checked on a fresh client?"),
        )
    if lesson_id == 42:
        from agent_lab.web_tools_lab import WebPolicy, citation_labels

        functions = (
            ("Host web input policy", WebPolicy.pre, "How does the host replace search domains and deny unlisted fetch URLs?"),
            ("Fetched output treatment", WebPolicy.post, "Which known instruction-like spans are replaced before delivery?"),
            ("Citation provenance", citation_labels, "How are URLs labelled from the current lane's observed source history?"),
        )
    if lesson_id == 43:
        from agent_lab.remote_fixture_lab import RemoteFixture, host_probe
        from agent_lab.remote_mcp_lab import live_action

        functions = (
            ("Protected fixture boundary", RemoteFixture.__call__, "How are credentials and MCP sessions checked?"),
            ("Real transport probe", host_probe, "Which tools and resources are observed over HTTP or SSE?"),
            ("Provider-backed call", live_action,
             "How do SDK call and result IDs join the host receipt?"),
        )
    if lesson_id == 44:
        from agent_lab.telemetry_collector import Collector, aggregate
        from agent_lab.telemetry_lab import local_action

        functions = (
            ("Bounded OTLP collector", Collector.__call__,
             "Which HTTP receipt proves a signal reached the collector?"),
            ("Numeric temporality reducer", aggregate,
             "Why is a cumulative value kept by timestamp instead of summed?"),
            ("Owned local producer", local_action,
             "Which records came from an authored fixture rather than a native subprocess?"),
        )
    for title, function, question in functions:
        function = inspect.unwrap(function)
        lines, start = inspect.getsourcelines(function)
        sections.append(
            {
                "title": title,
                "path": Path(inspect.getfile(function))
                .relative_to(Path(__file__).resolve().parent.parent)
                .as_posix(),
                "start": start,
                "end": start + len(lines) - 1,
                "code": "".join(lines),
                "question": question,
            }
        )
    return sections
