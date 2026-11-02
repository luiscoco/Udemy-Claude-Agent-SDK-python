import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock

from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS
from agent_lab.exercises import run_exercise, seed_workspace
from agent_lab.models import RunRequest
from agent_lab.sdk import run_sdk


@pytest.mark.parametrize("lesson_id", range(1, 75))
async def test_every_live_profile_constructs_real_sdk_options_and_owns_client_lifecycle(
    lesson_id, tmp_path, monkeypatch
):
    import agent_lab.sdk as sdk

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-not-a-real-key")
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "C:/fixture/claude.exe")
    owners = []
    captured = []

    def response():
        return ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sdk-fixture",
            total_cost_usd=0,
            result="fixture",
        )

    class Client:
        def __init__(self, options):
            captured.append(options)
            self.options = options

        async def __aenter__(self):
            owners.append(asyncio.current_task())
            return self

        async def query(self, prompt):
            owners.append(asyncio.current_task())

        async def receive_response(self):
            owners.append(asyncio.current_task())
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
    current = LESSONS[lesson_id]
    request = RunRequest(mode="live")
    seed_workspace(tmp_path / "work", current)
    evidence = await run_exercise(tmp_path / "work", request, current)
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
    assert ("Write" in options.tools) is (lesson_id == 4)
    assert options.max_budget_usd == (0.05 if lesson_id == 1 else 0.1)
    if lesson_id == 1:
        assert options.max_turns == 1
    assert options.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "config")
    # The shared policy and audit hooks that the offline hook lessons exercise.
    assert set(options.hooks) == {"PreToolUse", "PostToolUse"} | (
        {"Elicitation"} if lesson_id == 33 else set()
    )
    # Pre-approving tools would skip can_use_tool; the PreToolUse hook decides instead.
    assert options.allowed_tools == []
    assert events[-1].kind == ("evidence" if lesson_id <= 10 else "result")


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
