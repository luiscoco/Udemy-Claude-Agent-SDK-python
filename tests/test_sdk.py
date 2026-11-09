import asyncio
import json
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import run_exercise, seed_workspace
from agent_lab.models import RunRequest
from agent_lab.sdk import run_sdk


@pytest.mark.parametrize("lesson_id", range(1, 75))
async def test_every_live_profile_constructs_real_sdk_options_and_owns_client_lifecycle(
    lesson_id, tmp_path, monkeypatch
):
    if lesson_id in {51, 55}:
        pytest.skip("The pinned lesson contract expressly forbids live SDK calls.")
    if lesson_id in {52, 53, 54, 56, 57, 58}:
        pytest.skip("This lesson uses its separate bounded native transport.")
    if lesson_id in {37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49}:
        pytest.skip("This lesson uses a custom SDK transport covered by its focused and live tests.")
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "C:/fixture/claude.exe")
    if lesson_id == 16:
        import agent_lab.settings_lab as settings_lab

        monkeypatch.setattr(settings_lab, "resolve_cli_path", lambda settings: "C:/fixture/claude.exe")
    owners = []
    captured = []
    retry_handlers = []
    room_handlers = []

    def response():
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="00000000-0000-4000-8000-000000000019" if lesson_id == 19 else "00000000-0000-4000-8000-000000000035" if lesson_id == 35 else "sdk-fixture",
            total_cost_usd=0,
            result="fixture",
        )

    class Client:
        def __init__(self, options):
            captured.append(options)
            self.options = options
            self.turn = 0
            self.model = "fixture-model"
            self.closed = False

        async def __aenter__(self):
            owners.append(asyncio.current_task())
            return self

        async def query(self, prompt):
            owners.append(asyncio.current_task())
            if lesson_id == 35:
                from claude_agent_sdk import project_key_for_directory

                session_id = "00000000-0000-4000-8000-000000000035"
                cli_folder = Path(self.options.env["CLAUDE_CONFIG_DIR"]) / "projects" / project_key_for_directory(self.options.cwd)
                cli_folder.mkdir(parents=True, exist_ok=True)
                (cli_folder / f"{session_id}.jsonl").write_text(
                    json.dumps({"type": "user", "uuid": session_id, "message": prompt}) + "\n", encoding="utf-8"
                )
                await self.options.session_store.append(
                    {"project_key": project_key_for_directory(self.options.cwd), "session_id": session_id},
                    [{"type": "user", "uuid": session_id, "message": prompt}, {"type": "assistant", "message": "STORED_35"}],
                )
            if lesson_id == 34:
                import json as json_module

                configured = json_module.loads((Path(self.options.cwd) / ".claude" / "settings.json").read_text())
                self.style_name = configured["outputStyle"] if self.options.setting_sources == ["project"] else "default"
                self.style_answer = "STYLE_NONE_34" if self.style_name == "default" else {"teaching": "STYLE_TEACHING_34", "brief": "STYLE_BRIEF_34"}[self.style_name]
            if lesson_id == 33:
                await room_handlers[0].handler({"room": "Blue"})
            if lesson_id == 32:
                self.turn += 1
            if lesson_id == 31:
                from agent_lab.question_lab import question_input

                self.question_argument = question_input()
                self.permission = await self.options.can_use_tool("AskUserQuestion", self.question_argument, None)
            if lesson_id == 30:
                self.turn += 1
                argument = json.loads(prompt.rsplit("Do not retry within this turn: ", 1)[1])
                cid = f"todo-{self.turn}"
                decision = await self.options.hooks["PreToolUse"][0].hooks[0]({"tool_input": argument}, cid, None)
                if decision["hookSpecificOutput"]["permissionDecision"] == "allow":
                    await self.options.hooks["PostToolUse"][0].hooks[0]({}, cid, None)
            if lesson_id == 29:
                assert len([item async for item in prompt]) == 1
            if lesson_id == 28:
                await retry_handlers[0].handler({"order_id": "A-100"})
            if lesson_id == 26:
                if self.closed:
                    raise CLIConnectionError("Not connected")
                self.turn += 1
            if lesson_id == 19:
                from agent_lab.session_catalog import write_catalog_fixture

                write_catalog_fixture(Path(self.options.cwd), Path(self.options.env["CLAUDE_CONFIG_DIR"]), prompt)

        async def connect(self):
            owners.append(asyncio.current_task())

        async def disconnect(self):
            owners.append(asyncio.current_task())
            self.closed = True

        async def set_model(self, model):
            owners.append(asyncio.current_task())
            self.model = model

        async def set_permission_mode(self, mode):
            owners.append(asyncio.current_task())
            if lesson_id == 32:
                self.permission_mode = mode

        async def get_mcp_status(self):
            owners.append(asyncio.current_task())
            return {"mcpServers": [{"name": "inventory", "status": "connected"}]}

        async def get_server_info(self):
            owners.append(asyncio.current_task())
            return {"commands": [{"name": "lesson-summary"}, {"name": "python-teaching:explain"}]}

        async def receive_response(self):
            owners.append(asyncio.current_task())
            if lesson_id == 36:
                yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture"})
                result = response()
                result.result = "SPAWN_OK_36"
                yield result
                return
            if lesson_id == 35:
                yield SystemMessage(subtype="init", data={"session_id": "00000000-0000-4000-8000-000000000035"})
                result = response()
                result.result = "STORED_35"
                yield result
                return
            if lesson_id == 34:
                yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture", "output_style": self.style_name})
                result = response()
                result.result = self.style_answer
                yield result
                return
            if lesson_id == 33:
                yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture"})
                yield AssistantMessage(content=[ToolUseBlock(id="room-1", name="mcp__rooms__book_room", input={"room": "Blue"})], model="fixture")
                yield AssistantMessage(content=[ToolResultBlock(tool_use_id="room-1", content="booking", is_error=False)], model="fixture")
                yield response()
                return
            if lesson_id == 32:
                from agent_lab.harness_lab import PROPOSALS

                mode = "plan" if self.turn == 1 else self.permission_mode
                yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture", "permissionMode": mode})
                cid = f"plan-{self.turn}"
                yield AssistantMessage(content=[ToolUseBlock(id=cid, name="StructuredOutput", input=PROPOSALS["valid"])], model="fixture")
                yield AssistantMessage(content=[ToolResultBlock(tool_use_id=cid, content="proposal", is_error=False)], model="fixture")
                result = response()
                result.structured_output = PROPOSALS["valid"]
                yield result
                return
            if lesson_id == 31:
                yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture"})
                yield AssistantMessage(content=[ToolUseBlock(id="question-1", name="AskUserQuestion", input=self.question_argument)], model="fixture")
                yield AssistantMessage(content=[ToolResultBlock(tool_use_id="question-1", content="answer", is_error=False)], model="fixture")
                yield response()
                return
            if lesson_id == 26:
                from agent_lab.control_lab import AFTER, BEFORE

                if self.turn == 1:
                    yield SystemMessage(subtype="init", data={"session_id": "sdk-fixture"})
                marker = BEFORE if self.turn == 1 else AFTER
                yield AssistantMessage(content=[TextBlock(text=marker)], model=self.model)
                yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="sdk-fixture", total_cost_usd=0, result=marker)
                return
            if lesson_id in {19, 21}:
                yield SystemMessage(subtype="init", data={"session_id": "00000000-0000-4000-8000-000000000019" if lesson_id == 19 else "sdk-fixture"})
            yield AssistantMessage(
                content=[TextBlock(text="Fixture SDK response")], model="fixture"
            )
            yield response()

        async def __aexit__(self, *args):
            owners.append(asyncio.current_task())

    async def query(*, prompt, options):
        captured.append(options)
        if not isinstance(prompt, str):
            assert [item async for item in prompt][0]["message"]["role"] == "user"
        yield response()

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    monkeypatch.setattr(sdk, "query", query)
    if lesson_id == 21:
        import agent_lab.slash_commands as slash_commands

        monkeypatch.setattr(slash_commands, "ClaudeSDKClient", Client)
    if lesson_id == 22:
        import agent_lab.project_memory as project_memory

        monkeypatch.setattr(project_memory, "ClaudeSDKClient", Client)
    if lesson_id == 23:
        import agent_lab.plugin_lab as plugin_lab

        monkeypatch.setattr(plugin_lab, "ClaudeSDKClient", Client)
    if lesson_id == 24:
        import agent_lab.harness_lab as harness_lab

        monkeypatch.setattr(harness_lab, "ClaudeSDKClient", Client)
    if lesson_id == 25:
        import agent_lab.compaction_lab as compaction_lab

        monkeypatch.setattr(compaction_lab, "ClaudeSDKClient", Client)
    if lesson_id == 26:
        import agent_lab.control_lab as control_lab

        monkeypatch.setattr(control_lab, "ClaudeSDKClient", Client)
    if lesson_id == 27:
        import agent_lab.background_lab as background_lab

        monkeypatch.setattr(background_lab, "ClaudeSDKClient", Client)
    if lesson_id == 28:
        import agent_lab.retry_lab as retry_lab

        monkeypatch.setattr(retry_lab, "ClaudeSDKClient", Client)
        original_retry_options = retry_lab.retry_options

        def capture_retry_options(root, config, request, settings, handler):
            retry_handlers.append(handler)
            return original_retry_options(root, config, request, settings, handler)

        monkeypatch.setattr(retry_lab, "retry_options", capture_retry_options)
    if lesson_id == 29:
        import agent_lab.image_input_lab as image_input_lab

        monkeypatch.setattr(image_input_lab, "ClaudeSDKClient", Client)
    if lesson_id == 30:
        import agent_lab.todo_lab as todo_lab

        monkeypatch.setattr(todo_lab, "ClaudeSDKClient", Client)
    if lesson_id == 31:
        import agent_lab.question_lab as question_lab

        monkeypatch.setattr(question_lab, "ClaudeSDKClient", Client)
    if lesson_id == 32:
        import agent_lab.plan_lab as plan_lab

        monkeypatch.setattr(plan_lab, "ClaudeSDKClient", Client)
    if lesson_id == 33:
        import agent_lab.elicitation_lab as elicitation_lab

        monkeypatch.setattr(elicitation_lab, "ClaudeSDKClient", Client)
        original_elicitation_options = elicitation_lab.elicitation_options

        def capture_elicitation_options(root, config, request, settings, handler):
            room_handlers.append(handler)
            return original_elicitation_options(root, config, request, settings, handler)

        monkeypatch.setattr(elicitation_lab, "elicitation_options", capture_elicitation_options)
    if lesson_id == 34:
        import agent_lab.styles_lab as styles_lab

        monkeypatch.setattr(styles_lab, "ClaudeSDKClient", Client)
    if lesson_id == 35:
        import agent_lab.session_store_lab as session_store_lab

        monkeypatch.setattr(session_store_lab, "ClaudeSDKClient", Client)
        monkeypatch.setattr(session_store_lab, "resolve_cli_path", lambda settings: "C:/fixture/claude.exe", raising=False)
    if lesson_id == 36:
        import agent_lab.process_spawning_lab as process_spawning_lab

        monkeypatch.setattr(process_spawning_lab, "ClaudeSDKClient", Client)
    if lesson_id == 12:
        from claude_agent_sdk import ClaudeSDKClient as RealClient

        import agent_lab.streaming as streaming

        class StreamingClient(RealClient):
            def __init__(self, options, transport=None):
                captured.append(options)
                super().__init__(options=options, transport=streaming.StreamingFixture([["First"], ["Second"]]))

            async def connect(self, prompt=None):
                owners.append(asyncio.current_task())
                await super().connect(prompt=prompt)

            async def disconnect(self):
                owners.append(asyncio.current_task())
                await super().disconnect()

        monkeypatch.setattr(streaming, "ClaudeSDKClient", StreamingClient)
    current = LESSONS[lesson_id]
    request = RunRequest(mode="live")
    seed_workspace(tmp_path / "work", current)
    evidence = {} if lesson_id in {12, 13, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36} else await run_exercise(tmp_path / "work", request, current)
    events = []

    async def emit(event):
        events.append(event)

    async def ask(arguments):
        raise AssertionError("Fixture must not fabricate a user's approval.")

    await run_sdk(
        current,
        request,
        tmp_path / "work",
        tmp_path / "config",
        Settings(enable_live=True),
        evidence,
        emit,
        ask,
    )
    assert all(owner is asyncio.current_task() for owner in owners)
    options = captured[0]
    assert options.cli_path == "C:/fixture/claude.exe"
    assert options.strict_mcp_config
    assert options.cwd == str(tmp_path / "work")
    assert "Bash" not in options.tools
    assert ("Write" in options.tools) is (lesson_id in {4, 17})
    assert options.max_budget_usd == (0.05 if lesson_id == 1 else 0.1)
    if lesson_id == 1:
        assert options.max_turns == 1
    assert options.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "config")
    # The shared policy and audit hooks that the offline hook lessons exercise.
    assert set(options.hooks or {}) == (set() if lesson_id in {12, 15, 22, 24, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36} else {"PreCompact"} if lesson_id == 25 else {"Stop"} if lesson_id == 14 else {"PreToolUse", "PostToolUse"}) | (
        {"UserPromptSubmit", "Stop", "PostToolUseFailure"} if lesson_id == 20 else set()
    )
    # Lesson 13 sends one exact MCP allow rule and retains its PreToolUse guard.
    assert options.allowed_tools == (["mcp__inventory__reserve"] if lesson_id == 13 else ["mcp__context__read_log"] if lesson_id == 25 else ["mcp__billing__refund"] if lesson_id == 28 else ["TodoWrite"] if lesson_id == 30 else ["mcp__rooms__book_room"] if lesson_id == 33 else [])
    assert events[-1].kind == ("evidence" if lesson_id <= 36 else "result")


async def test_missing_live_credential_fails_before_client_connect(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for name in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        monkeypatch.delenv(name, raising=False)

    async def callback(*args):
        raise AssertionError("Must fail before producing SDK events")

    with pytest.raises(PermissionError):
        await run_sdk(
            LESSONS[1],
            RunRequest(mode="live"),
            tmp_path,
            tmp_path / "config",
            Settings(enable_live=True),
            {},
            callback,
            callback,
        )


async def test_openai_key_is_rejected_before_sdk_starts(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-proj-fixture-not-a-real-key")

    async def callback(*args):
        raise AssertionError("Must not send an OpenAI key to Claude")

    with pytest.raises(PermissionError, match="OpenAI-style key"):
        await run_sdk(
            LESSONS[1],
            RunRequest(mode="live"),
            tmp_path,
            tmp_path / "config",
            Settings(enable_live=True),
            {},
            callback,
            callback,
        )


@pytest.mark.parametrize("lesson_id", [1, 6])
async def test_401_stops_stream_and_closes_sdk_connection(tmp_path, monkeypatch, lesson_id):
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    closed = []

    async def messages():
        try:
            yield SystemMessage(subtype="api_retry", data={"error_status": 401})
            raise AssertionError("Must stop consuming authentication retries")
        finally:
            closed.append(True)

    class Client:
        def __init__(self, options):
            self.stream = messages()

        async def __aenter__(self):
            return self

        async def query(self, prompt):
            pass

        def receive_response(self):
            return self.stream

        async def __aexit__(self, *args):
            await self.stream.aclose()

    monkeypatch.setattr(sdk, "query", lambda **kwargs: messages())
    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)

    async def callback(*args):
        if args[0].kind == "options":
            return
        raise AssertionError("Must report authentication failure instead of retry events")

    with pytest.raises(PermissionError, match="HTTP 401"):
        await run_sdk(
            LESSONS[lesson_id],
            RunRequest(mode="live"),
            tmp_path,
            tmp_path / "config",
            Settings(enable_live=True),
            {},
            callback,
            callback,
        )
    assert closed == [True]


@pytest.mark.parametrize(
    ("subtype", "expected"),
    [
        ("error_max_turns", "used all 4 turns"),
        ("error_max_budget_usd", "0.10 USD budget threshold"),
        ("error_during_execution", "failed run (error_during_execution)"),
    ],
)
def test_failed_result_explains_its_subtype(subtype, expected):
    from agent_lab.sdk import failure_message

    result = ResultMessage(
        subtype=subtype,
        duration_ms=1,
        duration_api_ms=1,
        is_error=True,
        num_turns=4,
        session_id="sdk-fixture",
    )
    assert expected in failure_message(result, RunRequest())


def test_lessons_that_need_more_room_have_live_defaults():
    assert LESSONS[1].max_turns == 1 and LESSONS[1].max_budget_usd == 0.05
    assert LESSONS[16].max_turns == 8
    assert LESSONS[32].max_turns == 12
    assert LESSONS[75].max_budget_usd == 0.50
    for lesson in LESSONS.values():
        RunRequest(max_turns=lesson.max_turns, max_budget_usd=lesson.max_budget_usd)
