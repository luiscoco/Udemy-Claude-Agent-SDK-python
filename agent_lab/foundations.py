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
    from agent_lab.mcp_lab import local_mcp
    from agent_lab.streaming import local_streaming
    from agent_lab.thinking import local_thinking

    function = (
        local_thinking
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
        if lesson_id not in {12, 13, 14}
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
