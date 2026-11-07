"""A bounded file rewind lesson using the public Python client and owned files."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from claude_agent_sdk import ClaudeAgentOptions, SystemMessage

from agent_lab.config import Settings
from agent_lab.foundations import Evidence
from agent_lab.models import Event, LessonError, RunRequest, lesson_request
from agent_lab.policy import inside
from agent_lab.scripted_cli import ScriptedCLI

REPLACEMENTS = {
    "short": "Checkpoint lesson: a disposable SDK edit.\n",
    "long": "Checkpoint lesson: compare the changed file with its original bytes before rewinding.\n",
}
FIXTURE_CHECKPOINT = "00000000-0000-4000-8000-000000000017"


def file_hash(root: Path) -> str | None:
    path = inside(root, "notes.txt")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def checkpoint_policy(root: Path, replacement: str, name: str, arguments: dict) -> tuple[bool, str]:
    """Never allow the model to expand the file, content or tool scope."""
    try:
        raw = Path(str(arguments.get("file_path", "")))
        relative = raw.resolve().relative_to(root.resolve()) if raw.is_absolute() else raw
        target = inside(root, str(relative))
    except (ValueError, OSError):
        return False, "Only the owned notes.txt fixture is available."
    allowed = target == inside(root, "notes.txt") and (
        name == "Read" or name == "Write" and arguments.get("content") == replacement
    )
    return allowed, "Only Read or the exact displayed Write to notes.txt is permitted."


def checkpoint_options(
    root: Path, config: Path, request: RunRequest, settings: Settings
) -> ClaudeAgentOptions:
    from agent_lab.sdk import isolated_env, resolve_cli_path

    selected = lesson_request(17, request).lesson_options
    return ClaudeAgentOptions(
        cwd=str(root.resolve()),
        model=settings.model,
        cli_path=resolve_cli_path(settings) if request.mode == "live" else None,
        setting_sources=[],
        strict_mcp_config=True,
        tools=["Read", "Write"],
        allowed_tools=[],
        permission_mode="default",
        enable_file_checkpointing=selected["checkpointing"],
        extra_args={"replay-user-messages": None} if selected["replay_messages"] else {},
        env=isolated_env(config.resolve()),
        max_turns=request.max_turns,
        max_budget_usd=request.max_budget_usd,
        system_prompt="First Read notes.txt, then use Write once on notes.txt with the exact JSON-decoded replacement, including its final newline. Do not use any other file or tool. Reply Done after the write. File rewind is managed by the host and does not reset conversation history.",
    )


class CheckpointFixture(ScriptedCLI):
    """Real SDK protocol; file edits/backups and rewind effects are scripted host fixtures."""

    def __init__(self, root: Path, request: RunRequest, prompt: str):
        super().__init__([[]])
        self.root, self.request, self.prompt = root, request, prompt
        self.before = inside(root, "notes.txt").read_bytes()

    async def _reply(self) -> None:
        selected = self.request.lesson_options
        scenario = self.request.scenario
        await self._outbox.put(
            {
                "type": "system",
                "subtype": "init",
                "session_id": self.session_id,
                "tools": ["Read", "Write"],
            }
        )
        if selected["replay_messages"] and scenario != "missing-checkpoint":
            await self._outbox.put(
                {
                    "type": "user",
                    "uuid": FIXTURE_CHECKPOINT,
                    "session_id": self.session_id,
                    "message": {"role": "user", "content": self.prompt},
                    "parent_tool_use_id": None,
                }
            )
        replacement = REPLACEMENTS[selected["replacement"]]
        await self._outbox.put(
            {
                "type": "assistant",
                "session_id": self.session_id,
                "message": {
                    "model": self.model,
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "fixture-write",
                            "name": "Write",
                            "input": {
                                "file_path": str(inside(self.root, "notes.txt")),
                                "content": replacement,
                            },
                        }
                    ],
                },
            }
        )
        inside(self.root, "notes.txt").write_text(replacement, encoding="utf-8")
        if scenario != "missing-evidence":
            await self._outbox.put(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "fixture-write",
                                "content": "Fixture write completed",
                                "is_error": False,
                            }
                        ],
                    },
                }
            )
        await self._outbox.put(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 0,
                "duration_api_ms": 0,
                "num_turns": 1,
                "is_error": False,
                "session_id": "foreign-session"
                if scenario == "wrong-identity"
                else self.session_id,
                "total_cost_usd": 0,
                "result": "Scripted file edit; no model was called.",
            }
        )

    async def _control(self, request_id: str, request: dict[str, Any]) -> None:
        if request.get("subtype") != "rewind_files":
            await super()._control(request_id, request)
            return
        valid = (
            request.get("user_message_id") == FIXTURE_CHECKPOINT
            and self.request.lesson_options["checkpointing"]
            and self.request.scenario != "rewind-error"
        )
        if valid and self.request.scenario != "no-effect":
            inside(self.root, "notes.txt").write_bytes(self.before)
        self.lifecycle.append("control: rewind_files")
        await self._outbox.put(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success" if valid else "error",
                    "request_id": request_id,
                    **({"response": {}} if valid else {"error": "Recorded rewind rejection"}),
                },
            }
        )


def checkpoint_report(state: Evidence, observation: dict[str, Any]) -> dict[str, Any]:
    """Require a successful edit, captured user UUID, acknowledged rewind and actual restoration."""
    report = state.report()
    paired = [
        call
        for call in state.calls
        if call.get("name") == "Write"
        and not call.get("parent_tool_use_id")
        and checkpoint_policy(
            state.root, REPLACEMENTS[state.selected["replacement"]], "Write", call["arguments"]
        )[0]
        and sum(c["id"] == call["id"] for c in state.calls) == 1
        and sum(r["id"] == call["id"] for r in state.results) == 1
        and any(
            r["id"] == call["id"] and r.get("is_error") is False and r.get("run_id") == state.run_id
            for r in state.results
        )
    ]
    passed = bool(
        report["experiment_passed"]
        and state.initialized
        and state.configured.get("enable_file_checkpointing") is True
        and state.configured.get("extra_args") == {"replay-user-messages": None}
        and len(paired) == 1
        and observation.get("checkpoint_id")
        and state.selected["checkpointing"]
        and state.selected["replay_messages"]
        and observation.get("rewind_acknowledged") is True
        and observation.get("before_hash") != observation.get("changed_hash")
        and observation.get("before_hash") is not None
        and observation.get("changed_hash") is not None
        and observation.get("after_hash") == observation.get("before_hash")
        and observation.get("connection_closed") is True
    )
    report.update(observation)
    report.update(
        experiment_passed=passed,
        expected_check="passed" if passed else "needs-review",
        check_scope="One owned Write with matching result, successful parent session, replayed user checkpoint UUID, acknowledged native rewind, changed then restored file hash, and connection closure. File restoration does not reset conversation history. Offline backup and rewind effects are scripted, not native CLI acceptance.",
    )
    return report


async def execute_checkpoint(
    root: Path, request: RunRequest, settings: Settings, emit: Any, config: Path | None = None
) -> dict[str, Any]:
    from agent_lab.hooks import lesson_hooks, permission_callback
    from agent_lab.sdk import ClaudeSDKClient, message_data, require_live_access

    request = lesson_request(17, request)
    live = request.mode == "live"
    if live:
        require_live_access(settings)
    config = config or root.parent / "checkpoint-config"
    config.mkdir(parents=True, exist_ok=True)
    selected = request.lesson_options
    replacement = REPLACEMENTS[selected["replacement"]]
    prompt = (
        request.prompt
        + "\nFirst Read notes.txt. Then use Write once to replace it. "
        + "The content argument must be this JSON-decoded string, including the final newline: "
        + json.dumps(replacement)
    )
    options = checkpoint_options(root, config, request, settings)
    state = Evidence(
        17,
        root.parent.name,
        root,
        selected,
        "live SDK stream and actual host callbacks"
        if live
        else "real Python SDK client with explicitly recorded CLI and backup fixtures",
    )
    state.configured = {
        "enable_file_checkpointing": options.enable_file_checkpointing,
        "extra_args": options.extra_args,
        "tools": options.tools,
        "setting_sources": options.setting_sources,
    }
    observation: dict[str, Any] = {
        "before_hash": file_hash(root),
        "checkpoint_id": None,
        "rewind_requested": False,
        "rewind_acknowledged": False,
        "connection_closed": False,
    }

    async def audit(kind: str, data: dict) -> None:
        await emit(Event(kind=kind, data=data))

    async def no_questions(args: dict) -> dict:
        return {}

    def permitted(name: str, args: dict) -> tuple[bool, str]:
        return checkpoint_policy(root, replacement, name, args)

    options.hooks = lesson_hooks(permitted, audit)
    options.can_use_tool = permission_callback(permitted, no_questions)
    fixture = None if live else CheckpointFixture(root, request, prompt)
    client = (
        ClaudeSDKClient(options=options, transport=fixture)
        if fixture
        else ClaudeSDKClient(options=options)
    )
    await emit(Event(kind="options", data={"lesson_id": 17, "sdk_options": state.configured}))
    try:
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
            if (
                data["message_class"] == "UserMessage"
                and not data.get("parent_tool_use_id")
                and not state.calls
                and observation["checkpoint_id"] is None
            ):
                content = data.get("content")
                text = (
                    content
                    if isinstance(content, str)
                    else "".join(b.get("text", "") for b in (content or []) if isinstance(b, dict))
                )
                if text == prompt and isinstance(data.get("uuid"), str):
                    try:
                        observation["checkpoint_id"] = str(UUID(data["uuid"]))
                    except ValueError:
                        pass
            event = Event(
                kind="result" if data["message_class"] == "ResultMessage" else "message", data=data
            )
            state.observe(event)
            await emit(event)
        observation["changed_hash"] = file_hash(root)
        eligible = (
            state.report()["experiment_passed"]
            and bool(state.initialized)
            and selected["checkpointing"]
            and selected["replay_messages"]
            and observation["checkpoint_id"]
            and selected["action"] == "rewind"
        )
        if eligible:
            observation["rewind_requested"] = True
            try:
                await client.rewind_files(observation["checkpoint_id"])
                observation["rewind_acknowledged"] = True
            except Exception as exc:
                if live:
                    raise LessonError(
                        "Native rewind was rejected. Inspect the owned file evidence; no host restore was substituted."
                    ) from exc
                observation["rewind_error"] = "Recorded native control rejection"
        if live and not state.report()["experiment_passed"]:
            raise LessonError(
                "The checkpoint run did not finish with a matching successful parent result."
            )
    finally:
        try:
            await client.disconnect()
            observation["connection_closed"] = True
        finally:
            observation["after_hash"] = file_hash(root)
            if fixture:
                observation["fixture_controls"] = [
                    r["request"] for r in fixture.received if r.get("type") == "control_request"
                ]
            report = checkpoint_report(state, observation)
            report["scenario"] = request.scenario
            proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
            async with asyncio.timeout(1):
                await emit(Event(kind="evidence", data={"lesson_id": 17, "result": proof}))
    return proof


async def local_checkpoint(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_checkpoint(
        root, request.model_copy(update={"mode": "offline"}), Settings(), ignore
    )
