"""Injected agent streams exercise real SDK options and the actual in-process MCP tools."""

import asyncio

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from mcp.shared.memory import create_connected_server_and_client_session

from agent_lab.config import Settings
from agent_lab.learning import check_evidence
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def test_cancellation_closes_owned_http_server_even_with_a_blocked_consumer(
    tmp_path, monkeypatch
):
    import socket
    from urllib.parse import urlsplit

    import agent_lab.sdk as sdk
    from agent_lab.mcp_sdk import run_mcp_sdk

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")
    ready, blocked = asyncio.Event(), asyncio.Event()
    urls = []

    async def emit(event):
        if event.kind == "options":
            urls.append(event.data["sdk_options"]["mcp_servers"]["inventory"]["url"])
            ready.set()
        await blocked.wait()

    task = asyncio.create_task(
        run_mcp_sdk(
            RunRequest(mode="live", lesson_options={"transport": "http"}),
            tmp_path,
            tmp_path / "config",
            Settings(enable_live=True),
            emit,
        )
    )
    await asyncio.wait_for(ready.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    port = urlsplit(urls[0]).port

    def bind_released_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
            return listener.getsockname()[1]

    assert await asyncio.to_thread(bind_released_port) == port


async def injected(
    tmp_path, monkeypatch, *, lifecycle="none", wrong=False, missing=False, failed=False, auth=False
):
    import agent_lab.sdk as sdk

    captured, operations, owners = [], [], []
    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")

    class Client:
        def __init__(self, options):
            self.options, self.enabled = options, True
            captured.append(options)

        async def __aenter__(self):
            owners.append(asyncio.current_task())
            return self

        async def __aexit__(self, *args):
            owners.append(asyncio.current_task())
            operations.append("closed")

        async def get_mcp_status(self):
            return {
                "mcpServers": [
                    {"name": "inventory", "status": "connected" if self.enabled else "disabled"}
                ]
            }

        async def toggle_mcp_server(self, name, enabled):
            assert name == "inventory"
            self.enabled = enabled
            operations.append(("toggle", enabled))

        async def reconnect_mcp_server(self, name):
            assert name == "inventory"
            operations.append("reconnect")

        async def query(self, prompt):
            operations.append("query")
            assert "mcp__inventory__reserve" in prompt

        async def receive_response(self):
            if auth:
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                return
            yield SystemMessage(
                subtype="init",
                data={"session_id": "injected-parent", "tools": ["mcp__inventory__reserve"]},
            )
            if not missing:
                arguments = {"sku": "notebook", "quantity": 2}
                yield AssistantMessage(
                    content=[
                        ToolUseBlock(id="call-A", name="mcp__inventory__reserve", input=arguments)
                    ],
                    model="injected",
                )
                server = self.options.mcp_servers["inventory"]["instance"]
                async with create_connected_server_and_client_session(server) as client:
                    result = await client.call_tool("reserve", arguments)
                assert not result.isError
                yield UserMessage(
                    content=[
                        ToolResultBlock(
                            tool_use_id="wrong" if wrong else "call-A",
                            is_error=result.isError,
                            content="Recorded SDK delivery of the real inventory result",
                        )
                    ]
                )
            yield ResultMessage(
                subtype="error_during_execution" if failed else "success",
                is_error=failed,
                duration_ms=1,
                duration_api_ms=1,
                num_turns=1,
                session_id="injected-parent",
                total_cost_usd=0,
            )

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(13, RunRequest(mode="live", lesson_options={"lifecycle": lifecycle}))
    events = [event async for event in runner.events(handle)]
    result = next(event.data["result"] for event in events if event.kind == "evidence")
    assert not runner.active
    return events, result, captured, operations, owners


@pytest.mark.parametrize("lifecycle", ["none", "toggle", "reconnect"])
async def test_live_options_controls_real_host_effect_and_correlated_parent_result(
    tmp_path, monkeypatch, lifecycle
):
    events, proof, captured, operations, owners = await injected(
        tmp_path, monkeypatch, lifecycle=lifecycle
    )
    assert events[-1].data["status"] == "completed"
    assert proof["experiment_passed"]
    assert check_evidence(13, proof, status="completed", mode="live").status == "passed"
    assert proof["experiment"]["local_stock"]["after"]["stock"]["notebook"] == 10
    assert captured[0].allowed_tools == ["mcp__inventory__reserve"]
    assert captured[0].setting_sources == [] and captured[0].strict_mcp_config
    assert len(captured) == 1 and operations.count("query") == 1 and operations[-1] == "closed"
    assert owners[0] is owners[-1]
    if lifecycle == "toggle":
        assert ("toggle", False) in operations and ("toggle", True) in operations
        assert len(proof["experiment"]["mcp_status_history"]) == 3
    elif lifecycle == "reconnect":
        assert "reconnect" in operations


@pytest.mark.parametrize("case", ["wrong", "missing", "failed", "auth"])
async def test_live_error_or_unrelated_evidence_cannot_pass(tmp_path, monkeypatch, case):
    events, result, _, operations, _ = await injected(tmp_path, monkeypatch, **{case: True})
    assert not result["experiment_passed"] and operations[-1] == "closed"
    if case in {"failed", "auth"}:
        assert events[-1].data["status"] == "failed"
        assert any(event.kind == "error" for event in events)
    if case == "auth":
        assert any(event.kind == "error" and "401" in event.data["message"] for event in events)
        assert (
            result["experiment"]["local_stock"]["before"]
            == result["experiment"]["local_stock"]["after"]
        )
