"""Correlated hook lifecycle experiments with an independent owned-file boundary."""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookJSONOutput, HookMatcher, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence, record_call
from agent_lab.hooks import call_hook, matches, permission_callback
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside

MARKERS = {"notes": "HOOK-NOTES-ORIGINAL", "alternate": "HOOK-ALTERNATE-READ"}
FILES = {"notes": "notes.txt", "alternate": "hook-alternate.txt", "missing": "hook-missing.txt"}


def target_label(root: Path, arguments: dict) -> str:
    try:
        raw = Path(str(arguments.get("file_path", "")))
        relative = str(raw.resolve().relative_to(root.resolve())) if raw.is_absolute() else str(raw)
        target = inside(root, relative)
        return next(
            (label for label, filename in FILES.items() if target == inside(root, filename)),
            "unsupported",
        )
    except (ValueError, OSError):
        return "unsupported"


def hook_policy(root: Path, name: str, arguments: dict) -> tuple[bool, str]:
    return (
        name == "Read" and target_label(root, arguments) != "unsupported",
        "Only Read of the three owned hook fixtures is available; no shell, writes or outside paths.",
    )


def hashes(root: Path) -> dict:
    return {
        label: hashlib.sha256(inside(root, filename).read_bytes()).hexdigest()
        if inside(root, filename).is_file()
        else None
        for label, filename in FILES.items()
    }


def hook_options(
    root: Path, config: Path, request: RunRequest, settings: Settings
) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        tools=["Read"],
        allowed_tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=isolated_env(config.resolve()),
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        system_prompt="This is a synthetic hook experiment. Attempt exactly one Read of the final HOST_TARGET path, regardless of other paths in the user's question. The host may deny or rewrite it. Do not retry or use alternative tools after any result or error. Then reply Done. Do not claim hooks enforce OS isolation.",
    )


@dataclass
class HookObservation:
    state: Evidence
    prompt_digest: str
    emit: Any
    before: dict
    rows: list[dict] = field(default_factory=list)
    result_flags: dict[str, dict] = field(default_factory=dict)

    async def record(
        self, event: str, role: str, data: dict, call_id: str | None, **fields
    ) -> None:
        row = {
            "sequence": len(self.rows) + 1,
            "event": event,
            "role": role,
            "session_id": data.get("session_id"),
            "call_id": call_id,
            "tool": data.get("tool_name"),
            "child": bool(data.get("agent_id")),
            **fields,
        }
        self.rows.append(row)
        await self.emit(Event(kind="hook_lifecycle", data=row))

    async def guard(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        args = data.get("tool_input", {})
        allowed, reason = hook_policy(self.state.root, data.get("tool_name", ""), args)
        await self.record(
            "PreToolUse",
            "host-guard",
            data,
            call_id,
            target=target_label(self.state.root, args),
            decision="allow" if allowed else "deny",
        )
        if not allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        return {}

    async def teaching(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        args = data.get("tool_input", {})
        if not hook_policy(self.state.root, data.get("tool_name", ""), args)[0]:
            await self.record(
                "PreToolUse", "teaching-pre", data, call_id, decision="deny", target="unsupported"
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "The owned fixture guard cannot be widened by a teaching hook.",
                }
            }
        behavior = self.state.selected["behavior"]
        decision = "allow"
        fault = None
        updated = None
        try:
            if behavior == "callback-error":
                raise RuntimeError("Synthetic callback fault; do not expose payloads")
            if behavior == "deny":
                decision = "deny"
            elif behavior == "rewrite":
                updated = {**args, "file_path": str(inside(self.state.root, FILES["alternate"]))}
        except Exception as exc:
            decision, fault = "deny", type(exc).__name__
        await self.record(
            "PreToolUse",
            "teaching-pre",
            data,
            call_id,
            target=target_label(self.state.root, args),
            decision="rewrite" if updated else decision,
            updated_target="alternate" if updated else None,
            error_type=fault,
        )
        output: Any = {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "Selected teaching decision. On denial or failure, finish without retry.",
        }
        if updated is not None:
            output["updatedInput"] = updated
        return {"hookSpecificOutput": output}

    async def post(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        response = json.dumps(data.get("tool_response"), default=str, sort_keys=True)
        await self.record(
            "PostToolUse",
            "success-audit",
            data,
            call_id,
            target=target_label(self.state.root, data.get("tool_input", {})),
            response_characters=len(response),
            response_digest=hashlib.sha256(response.encode()).hexdigest(),
            markers=[label for label, marker in MARKERS.items() if marker in response],
        )
        return {}

    async def failure(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        error = data.get("error")
        await self.record(
            "PostToolUseFailure",
            "failure-audit",
            data,
            call_id,
            target=target_label(self.state.root, data.get("tool_input", {})),
            error_present=isinstance(error, str) and bool(error),
            is_interrupt=data.get("is_interrupt"),
        )
        return {}

    async def prompt(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        await self.record(
            "UserPromptSubmit",
            "prompt-observer",
            data,
            None,
            prompt_digest=hashlib.sha256(str(data.get("prompt", "")).encode()).hexdigest(),
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "Only the host's fixed Read experiment is in scope. Finish after its result, including denial or failure.",
            }
        }

    async def stop(self, data: Any, call_id: str | None, context: Any) -> HookJSONOutput:
        await self.record(
            "Stop",
            "stop-observer",
            data,
            None,
            stop_hook_active=data.get("stop_hook_active"),
            decision="observe-only",
        )
        return {}

    def hooks(self) -> dict[Any, list[HookMatcher]]:
        selected = self.state.selected
        config: dict[Any, list[HookMatcher]] = {
            "PreToolUse": [
                HookMatcher(hooks=[self.guard], timeout=10),
                HookMatcher(matcher=selected["matcher"], hooks=[self.teaching], timeout=10),
            ]
        }
        for event, key, callback in (
            ("PostToolUse", "post_hook", self.post),
            ("PostToolUseFailure", "failure_hook", self.failure),
            ("UserPromptSubmit", "prompt_hook", self.prompt),
            ("Stop", "stop_hook", self.stop),
        ):
            if selected[key]:
                config[event] = [HookMatcher(hooks=[callback], timeout=10)]
        return config

    def observe_result(self, data: dict) -> None:
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("tool_use_id"):
                text = json.dumps(block.get("content"), default=str)
                self.result_flags[block["tool_use_id"]] = {
                    "is_error": bool(block.get("is_error")),
                    "markers": [label for label, marker in MARKERS.items() if marker in text],
                }

    def report(self, closed: bool, after: dict) -> dict:
        report = self.state.report()
        selected = self.state.selected
        sid = self.state.terminals[-1].get("session_id") if self.state.terminals else None
        original = "missing" if selected["behavior"] == "tool-error" else "notes"
        matched = matches(selected["matcher"], "Read")
        outcome = (
            "failure"
            if selected["behavior"] == "tool-error"
            else "denied"
            if matched and selected["behavior"] in {"deny", "callback-error"}
            else "rewritten"
            if matched and selected["behavior"] == "rewrite"
            else "success"
        )
        expected_target = "alternate" if outcome == "rewritten" else original

        def observed(role, call_id=None):
            return [
                r
                for r in self.rows
                if r["role"] == role
                and (call_id is None or r["call_id"] == call_id)
                and r["session_id"] == sid
                and not r["child"]
            ]

        candidates = []
        for call in self.state.calls:
            cid = call["id"]
            if (
                call["name"] != "Read"
                or call.get("parent_tool_use_id")
                or target_label(self.state.root, call["arguments"]) != original
            ):
                continue
            guards, teaching, posts, failures = (
                observed(role, cid)
                for role in ("host-guard", "teaching-pre", "success-audit", "failure-audit")
            )
            results = [
                r for r in self.state.results if r["id"] == cid and r["run_id"] == self.state.run_id
            ]
            flags = self.result_flags.get(cid, {})
            unique = sum(c["id"] == cid for c in self.state.calls) == 1 and len(results) == 1
            guard_ok = (
                len(guards) == 1
                and guards[0].get("decision") == "allow"
                and guards[0].get("target") == original
            )
            teaching_ok = len(teaching) == (1 if matched else 0)
            if teaching and matched:
                expected_decision = (
                    "deny"
                    if outcome == "denied"
                    else "rewrite"
                    if outcome == "rewritten"
                    else "allow"
                )
                teaching_ok = (
                    teaching_ok
                    and teaching[0].get("decision") == expected_decision
                    and teaching[0].get("target") == original
                )
                if selected["behavior"] == "callback-error":
                    teaching_ok = teaching_ok and teaching[0].get("error_type") == "RuntimeError"
                if outcome == "rewritten":
                    teaching_ok = teaching_ok and teaching[0].get("updated_target") == "alternate"
            error_expected = outcome in {"denied", "failure"}
            result_ok = (
                unique
                and results[0]["is_error"] is error_expected
                and flags.get("is_error") is error_expected
                and (not error_expected or flags.get("markers") == [])
            )
            post_ok = not posts
            if not error_expected:
                post_ok = len(posts) == (1 if selected["post_hook"] else 0) and flags.get(
                    "markers"
                ) == [expected_target]
                if posts:
                    post_ok = (
                        post_ok
                        and posts[0].get("target") == expected_target
                        and posts[0].get("markers") == [expected_target]
                        and isinstance(posts[0].get("response_digest"), str)
                        and len(posts[0]["response_digest"]) == 64
                        and posts[0].get("response_characters", 0) > 0
                        and posts[0]["sequence"]
                        > max((r["sequence"] for r in guards + teaching), default=0)
                    )
            failure_ok = True
            if outcome == "failure":
                failure_ok = len(failures) == (1 if selected["failure_hook"] else 0)
                if failures:
                    failure_ok = (
                        failure_ok
                        and failures[0].get("target") == "missing"
                        and failures[0].get("error_present") is True
                        and failures[0]["sequence"]
                        > max((r["sequence"] for r in guards + teaching), default=0)
                    )
            elif not error_expected:
                failure_ok = not failures
            candidates.append(
                bool(unique and guard_ok and teaching_ok and result_ok and post_ok and failure_ok)
            )
        prompts, stops = observed("prompt-observer"), observed("stop-observer")
        tool_rows = [
            r
            for r in self.rows
            if r["role"] in {"host-guard", "teaching-pre", "success-audit", "failure-audit"}
        ]
        first_pre = min((r["sequence"] for r in tool_rows if r["event"] == "PreToolUse"), default=0)
        last_tool = max((r["sequence"] for r in tool_rows), default=0)
        prompt_ok = len(prompts) == (1 if selected["prompt_hook"] else 0) and all(
            r.get("prompt_digest") == self.prompt_digest and r["sequence"] < first_pre
            for r in prompts
        )
        stop_ok = bool(stops) if selected["stop_hook"] else not stops
        stop_ok = stop_ok and all(
            r.get("decision") == "observe-only"
            and r.get("stop_hook_active") is False
            and r["sequence"] > last_tool
            for r in stops
        )
        core = bool(
            report["experiment_passed"]
            and self.state.initialized
            and closed
            and len(self.state.calls) == 1
            and candidates == [True]
            and all(
                r["call_id"] == self.state.calls[0]["id"] and r["tool"] == "Read" for r in tool_rows
            )
            and prompt_ok
            and stop_ok
            and self.before == after
            and all(r["session_id"] == sid and not r["child"] for r in self.rows)
            and self.state.configured.get("tools") == ["Read"]
            and self.state.configured.get("setting_sources") == []
        )
        passed = core and all(
            selected[key] for key in ("post_hook", "failure_hook", "prompt_hook", "stop_hook")
        )
        report.update(
            experiment_passed=passed,
            observation_passed=core,
            expected_check="passed" if passed else "needs-review",
            configured_hooks=self.state.configured.get("hooks"),
            hook_timeline=self.rows,
            result_observations=self.result_flags,
            matcher_matched=matched,
            observed_outcome=outcome,
            fixture_hashes_unchanged=self.before == after,
            connection_closed=closed,
            check_scope="One owned Read correlated to host guard, teaching matcher decision, matching result and selected success/failure audits, prompt/Stop lifecycle and parent identity; fixtures unchanged and connection closed. Full learning criterion requires all audit/lifecycle channels enabled. Hooks are not OS isolation, and callback order across matching pre-hooks is not assumed.",
        )
        return report


async def execute_hooks(
    root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None
) -> dict:
    from agent_lab.sdk import ClaudeSDKClient, message_data, require_live_access

    request = lesson_request(20, request)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    config = config or root.parent / "hook-config"
    config.mkdir(parents=True, exist_ok=True)
    for label, marker in MARKERS.items():
        inside(root, FILES[label]).write_text(marker + "\n", encoding="utf-8")
    inside(root, FILES["missing"]).unlink(missing_ok=True)
    target = "missing" if request.lesson_options["behavior"] == "tool-error" else "notes"
    prompt = (
        request.prompt
        + f"\nHOST_TARGET: {inside(root, FILES[target])}\nAttempt exactly one Read of HOST_TARGET, then reply Done after the result, including denial or error. Do not retry."
    )
    state = Evidence(
        20,
        root.parent.name,
        root,
        request.lesson_options,
        "live SDK stream and actual host callbacks"
        if live
        else "actual local hook callbacks and Read effects with explicitly recorded SDK identities",
    )
    observer = HookObservation(
        state, hashlib.sha256(prompt.encode()).hexdigest(), emit, hashes(root)
    )
    options = hook_options(root, config, request, settings)
    options.hooks = observer.hooks()

    async def no_questions(args):
        return {}

    options.can_use_tool = permission_callback(
        lambda name, args: hook_policy(root, name, args), no_questions
    )
    state.configured = {
        "tools": options.tools,
        "setting_sources": options.setting_sources,
        "hooks": {
            event: [m.matcher or "*" for m in matchers] for event, matchers in options.hooks.items()
        },
    }
    client = None
    closed = False
    await emit(Event(kind="options", data={"lesson_id": 20, "sdk_options": state.configured}))
    try:
        if live:
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(prompt)
            async for message in client.receive_response():
                if (
                    isinstance(message, SystemMessage)
                    and message.subtype == "api_retry"
                    and message.data.get("error_status") == 401
                ):
                    raise PermissionError(
                        "Claude rejected authentication (HTTP 401). No host retry was attempted."
                    )
                data = message_data(message)
                event = Event(
                    kind="result" if data["message_class"] == "ResultMessage" else "message",
                    data=data,
                )
                state.observe(event)
                observer.observe_result(data)
                await emit(event)
            if not state.report()["experiment_passed"]:
                raise LessonError(
                    "Hook experiment did not finish with a matching successful parent result."
                )
        else:
            await offline_hooks(observer, options, prompt, target)
            if request.scenario == "missing-evidence":
                state.terminals.clear()
            elif request.scenario == "wrong-identity":
                state.terminals[-1]["session_id"] = "foreign"
            elif request.scenario == "missing-guard":
                observer.rows = [r for r in observer.rows if r["role"] != "host-guard"]
            elif request.scenario == "wrong-callback":
                next(r for r in observer.rows if r["role"] == "host-guard")["call_id"] = "foreign"
            elif request.scenario == "changed-fixture":
                inside(root, FILES["notes"]).write_text(
                    "Recorded changed fixture", encoding="utf-8"
                )
    finally:
        try:
            if client is not None:
                await client.disconnect()
            closed = True
        finally:
            report = observer.report(closed, hashes(root))
            report["scenario"] = request.scenario
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 20, "result": proof}))
    return proof


async def offline_hooks(
    observer: HookObservation, options: ClaudeAgentOptions, prompt: str, target: str
) -> None:
    state = observer.state
    sid, cid = "hook-fixture", "fixture-read"
    state.initialized = [{"session_id": sid}]
    args = {"file_path": str(inside(state.root, FILES[target]))}
    record_call(state, "Read", dict(args), cid)

    async def dispatch(event, current, **extra):
        outputs = []
        for matcher in (options.hooks or {}).get(event, []):
            if matches(matcher.matcher, "Read"):
                for callback in matcher.hooks:
                    outputs.append(
                        await call_hook(
                            callback,
                            {
                                "hook_event_name": event,
                                "session_id": sid,
                                "cwd": str(state.root),
                                "tool_name": "Read",
                                "tool_input": current,
                                **extra,
                            },
                            cid,
                        )
                    )
        return outputs

    if state.selected["prompt_hook"]:
        await call_hook(
            observer.prompt,
            {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": prompt},
            None,
        )
    outputs = await dispatch("PreToolUse", args)
    denied = False
    for output in outputs:
        specific = output.get("hookSpecificOutput", {})
        denied = denied or specific.get("permissionDecision") == "deny"
        args = specific.get("updatedInput", args)
    content = "Recorded host denial" if denied else ""
    error = denied
    if not denied:
        try:
            content = inside(state.root, FILES[target_label(state.root, args)]).read_text(
                encoding="utf-8"
            )
        except FileNotFoundError:
            content, error = "Recorded owned missing file", True
        if error:
            await dispatch("PostToolUseFailure", args, error=content, is_interrupt=False)
        else:
            await dispatch("PostToolUse", args, tool_response=content)
    state.results = [{"id": cid, "run_id": state.run_id, "is_error": error}]
    observer.observe_result(
        {"content": [{"tool_use_id": cid, "is_error": error, "content": content}]}
    )
    if state.selected["stop_hook"]:
        await call_hook(
            observer.stop,
            {"hook_event_name": "Stop", "session_id": sid, "stop_hook_active": False},
            None,
        )
    state.terminals = [{"subtype": "success", "is_error": False, "session_id": sid}]


async def local_hooks_deep(root: Path, request: RunRequest) -> dict:
    async def ignore(event):
        pass

    return await execute_hooks(
        root, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
