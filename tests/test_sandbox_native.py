"""Native probe grading is separate from the real WSL acceptance evidence."""

import asyncio
import json
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab import sandbox_native as native


async def test_unsupported_native_platform_never_opens_provider_or_creates_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(native.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        native, "ClaudeSDKClient", lambda **kwargs: pytest.fail("Unsupported platform")
    )
    result = await native.run_native_probe(tmp_path / "work", tmp_path / "config", "model")
    assert result["status"] == "unsupported" and result["model_calls"] == 0
    assert not list(tmp_path.iterdir())


def test_native_settings_close_fallback_and_independent_command_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(native.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native.shutil, "which", lambda name: None)
    assert not native.sandbox_capability()["supported"]
    options = native.native_options(tmp_path, tmp_path / "config", "model")
    assert options.sandbox["enabled"] and not options.sandbox["allowUnsandboxedCommands"]
    assert (
        options.sandbox["excludedCommands"] == []
        and options.sandbox["network"]["allowedDomains"] == []
    )
    assert json.loads(options.settings)["sandbox"]["failIfUnavailable"] is True
    assert options.setting_sources == [] and options.tools == ["Bash"] and options.strict_mcp_config
    assert native.native_command_allowed("Bash", {"command": native.COMMAND})
    assert not native.native_command_allowed(
        "Bash", {"command": native.COMMAND, "dangerouslyDisableSandbox": True}
    )
    assert not native.native_command_allowed("Bash", {"command": native.COMMAND + "; whoami"})


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "wrong-session",
        "wrong-result",
        "missing-decision",
        "no-inside-write",
        "outside-changed",
        "bad-flags",
        "disconnect-error",
        "auth-retry",
    ],
)
async def test_native_evaluator_requires_correlated_boolean_report_and_actual_file_effects(
    tmp_path, monkeypatch, case
):
    monkeypatch.setattr(
        native,
        "sandbox_capability",
        lambda: {"system": "Linux", "supported": True, "enforcement_verified": False},
    )
    owners = []

    class Client:
        def __init__(self, options):
            self.options = options
            self.root = Path(options.cwd)

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            pass

        async def receive_response(self):
            if case == "auth-retry":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                raise AssertionError("Stop auth retry")
            yield SystemMessage(subtype="init", data={"session_id": "native-parent"})
            args = {"command": native.COMMAND}
            if case != "missing-decision":
                await self.options.hooks["PreToolUse"][0].hooks[0](
                    {"tool_name": "Bash", "tool_input": args}, "native-call", None
                )
            yield AssistantMessage(
                model="injected", content=[ToolUseBlock(id="native-call", name="Bash", input=args)]
            )
            if case != "no-inside-write":
                (self.root / "inside-write.txt").write_text("inside-ok")
            if case == "outside-changed":
                (self.root.parent / "outside-write.txt").write_text("foreign")
            flags = {
                "inside_write": True,
                "outside_write_blocked": case != "bad-flags",
                "direct_loopback_blocked": True,
            }
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="foreign" if case == "wrong-result" else "native-call",
                        content="private-provider-noise\n" + json.dumps(flags),
                        is_error=False,
                    )
                ]
            )
            yield ResultMessage(
                subtype="success",
                is_error=False,
                duration_ms=1,
                duration_api_ms=1,
                num_turns=1,
                session_id="foreign" if case == "wrong-session" else "native-parent",
                total_cost_usd=0.01,
            )

        async def disconnect(self):
            owners.append(asyncio.current_task())
            if case == "disconnect-error":
                raise RuntimeError("private-error")

    monkeypatch.setattr(native, "ClaudeSDKClient", Client)
    proof = await native.run_native_probe(tmp_path / "work", tmp_path / "config", "injected")
    assert proof["passed"] is (case == "success")
    assert proof["capability"]["enforcement_verified"] is (case == "success")
    assert proof["baseline_loopback_reachable"]
    assert len(owners) == 2 and owners[0] is owners[1]
    assert "private-" not in str(proof)
