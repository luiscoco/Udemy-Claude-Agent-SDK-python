"""Correlated hook stages, actual local effects and guarded live callback ownership."""

import asyncio
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.curriculum import get_lesson
from agent_lab.exercises import seed_workspace
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import Evidence, source_sections
from agent_lab.hooks import call_hook, matches
from agent_lab.hooks_deep import (
    FILES,
    MARKERS,
    HookObservation,
    hashes,
    hook_options,
    hook_policy,
    offline_hooks,
)
from agent_lab.learning import check_evidence, guide
from agent_lab.models import RunRequest, lesson_request
from agent_lab.runtime import RunService


@pytest.mark.parametrize(
    "behavior,matcher,outcome",
    [
        ("observe", "Read", "success"),
        ("deny", "Read", "denied"),
        ("rewrite", "Read", "rewritten"),
        ("tool-error", "Read", "failure"),
        ("callback-error", "Read", "denied"),
        ("deny", "Write|Edit", "success"),
        ("rewrite", "Write|Edit", "success"),
        ("callback-error", "Write|Edit", "success"),
        ("tool-error", "Write|Edit", "failure"),
        ("observe", "Read|Glob", "success"),
        ("rewrite", "Read|Glob", "rewritten"),
    ],
)
async def test_selected_hooks_execute_real_owned_effects_and_correlate(
    tmp_path, behavior, matcher, outcome
):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(20, RunRequest(lesson_options={"behavior": behavior, "matcher": matcher}))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    report = proof["experiment"]
    assert proof["experiment_passed"] and report["observation_passed"]
    assert (
        report["observed_outcome"] == outcome
        and report["fixture_hashes_unchanged"]
        and report["connection_closed"]
    )
    assert check_evidence(20, proof, status="completed", mode="live").status == "needs-review"
    roles = [r["role"] for r in report["hook_timeline"]]
    assert roles.count("host-guard") == 1
    assert roles.count("teaching-pre") == (0 if matcher == "Write|Edit" else 1)
    assert roles.count("success-audit") == (1 if outcome in {"success", "rewritten"} else 0)
    assert roles.count("failure-audit") == (1 if outcome == "failure" else 0)
    if outcome == "rewritten":
        assert report["result_observations"]["fixture-read"]["markers"] == ["alternate"]
    assert "Synthetic callback fault; do not expose payloads" not in str(report)


@pytest.mark.parametrize("scenario", SCENARIOS[20])
@pytest.mark.parametrize("behavior", ["observe", "deny", "tool-error"])
async def test_negative_hook_records_need_review(tmp_path, scenario, behavior):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(20, RunRequest(scenario=scenario, lesson_options={"behavior": behavior}))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(20, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )


@pytest.mark.parametrize(
    "key,behavior,role",
    [
        ("post_hook", "observe", "success-audit"),
        ("failure_hook", "tool-error", "failure-audit"),
        ("prompt_hook", "observe", "prompt-observer"),
        ("stop_hook", "observe", "stop-observer"),
    ],
)
async def test_disabled_channels_are_observable_but_do_not_complete_full_criterion(
    tmp_path, key, behavior, role
):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(20, RunRequest(lesson_options={key: False, "behavior": behavior}))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert not proof["experiment_passed"] and proof["experiment"]["observation_passed"]
    assert not any(r["role"] == role for r in proof["experiment"]["hook_timeline"])
    assert any(r["role"] == "host-guard" for r in proof["experiment"]["hook_timeline"])


async def prepared_observer(tmp_path):
    request = lesson_request(20, {})
    seed_workspace(tmp_path, get_lesson(20))
    for label, marker in MARKERS.items():
        (tmp_path / FILES[label]).write_text(marker + "\n", encoding="utf-8")
    state = Evidence(20, "owned-run", tmp_path, request.lesson_options, "recorded fixture")

    async def ignore(event):
        pass

    import hashlib

    observer = HookObservation(
        state, hashlib.sha256(b"prompt").hexdigest(), ignore, hashes(tmp_path)
    )
    options = hook_options(tmp_path, tmp_path.parent / "config", request, Settings())
    options.hooks = observer.hooks()
    state.configured = {
        "tools": options.tools,
        "setting_sources": options.setting_sources,
        "hooks": {
            event: [m.matcher or "*" for m in matchers] for event, matchers in options.hooks.items()
        },
    }
    await offline_hooks(observer, options, "prompt", "notes")
    return observer


@pytest.mark.parametrize(
    "tamper",
    [
        "missing-guard",
        "missing-hash",
        "wrong-target",
        "early-post",
        "early-stop",
        "late-prompt",
        "foreign-session",
        "extra-foreign-audit",
        "duplicate-result",
        "no-pre",
    ],
)
async def test_hook_evaluator_rejects_uncorrelated_or_incomplete_records(tmp_path, tamper):
    observer = await prepared_observer(tmp_path)
    assert observer.report(True, hashes(tmp_path))["experiment_passed"]
    post = next(r for r in observer.rows if r["role"] == "success-audit")
    if tamper == "missing-guard":
        observer.rows = [r for r in observer.rows if r["role"] != "host-guard"]
    elif tamper == "missing-hash":
        post.pop("response_digest")
    elif tamper == "wrong-target":
        post["target"] = "alternate"
    elif tamper == "early-post":
        post["sequence"] = 0
    elif tamper == "early-stop":
        next(r for r in observer.rows if r["role"] == "stop-observer")["sequence"] = 0
    elif tamper == "late-prompt":
        next(r for r in observer.rows if r["role"] == "prompt-observer")["sequence"] = 99
    elif tamper == "foreign-session":
        post["session_id"] = "foreign"
    elif tamper == "extra-foreign-audit":
        observer.rows.append({**post, "call_id": "foreign"})
    elif tamper == "duplicate-result":
        observer.state.results.append(deepcopy(observer.state.results[0]))
    elif tamper == "no-pre":
        observer.rows = [r for r in observer.rows if r["event"] != "PreToolUse"]
    assert not observer.report(True, hashes(tmp_path))["experiment_passed"]


async def test_pre_hook_relative_callback_order_is_not_assumed(tmp_path):
    observer = await prepared_observer(tmp_path)
    pre = [r for r in observer.rows if r["event"] == "PreToolUse"]
    pre[0]["sequence"], pre[1]["sequence"] = pre[1]["sequence"], pre[0]["sequence"]
    assert observer.report(True, hashes(tmp_path))["experiment_passed"]
    result = await call_hook(
        observer.guard,
        {
            "hook_event_name": "PreToolUse",
            "session_id": "hook-fixture",
            "tool_name": "Read",
            "tool_input": {"file_path": "../outside"},
        },
        "foreign",
    )
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    result = await call_hook(
        observer.teaching,
        {
            "hook_event_name": "PreToolUse",
            "session_id": "hook-fixture",
            "tool_name": "Write",
            "tool_input": {"file_path": "notes.txt"},
        },
        "foreign",
    )
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not hook_policy(tmp_path, "Bash", {"file_path": "notes.txt"})[0]


@pytest.mark.parametrize(
    "options",
    [
        {"matcher": ".*"},
        {"behavior": "run-shell"},
        {"post_hook": "true"},
        {"stop_hook": 1},
        {"path": "../outside"},
        {"hook_timeout": 0},
        {"hooks": {}},
    ],
)
async def test_hook_inputs_reject_before_task_or_files(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/20/run", json={"lesson_options": options})
    assert response.status_code == 422 and not runner.active and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "missing-post",
        "wrong-hook-id",
        "wrong-session",
        "disconnect-error",
        "auth-retry",
        "cancel",
    ],
)
async def test_injected_live_callbacks_keep_one_owner_and_require_actual_hooks(
    tmp_path, monkeypatch, case
):
    import agent_lab.sdk as sdk

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")
    entered = asyncio.Event()
    owners = []

    class Client:
        def __init__(self, options):
            self.options = options

        async def connect(self):
            owners.append(asyncio.current_task())

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_response(self):
            entered.set()
            if case == "cancel":
                await asyncio.Event().wait()
            if case == "auth-retry":
                yield SystemMessage(subtype="api_retry", data={"error_status": 401})
                raise AssertionError("Must stop authentication retry")
            sid, cid = "actual-parent", "actual-read"
            yield SystemMessage(subtype="init", data={"session_id": sid})
            data = {"session_id": sid, "cwd": self.options.cwd, "prompt": self.prompt}
            await call_hook(
                self.options.hooks["UserPromptSubmit"][0].hooks[0],
                {**data, "hook_event_name": "UserPromptSubmit"},
                None,
            )
            args = {"file_path": str(Path(self.options.cwd) / "notes.txt")}
            yield AssistantMessage(
                model="injected", content=[ToolUseBlock(id=cid, name="Read", input=args)]
            )
            for matcher in self.options.hooks["PreToolUse"]:
                if matches(matcher.matcher, "Read"):
                    for callback in matcher.hooks:
                        await call_hook(
                            callback,
                            {
                                **data,
                                "hook_event_name": "PreToolUse",
                                "tool_name": "Read",
                                "tool_input": args,
                            },
                            "foreign" if case == "wrong-hook-id" else cid,
                        )
            content = (Path(self.options.cwd) / "notes.txt").read_text()
            if case != "missing-post":
                await call_hook(
                    self.options.hooks["PostToolUse"][0].hooks[0],
                    {
                        **data,
                        "hook_event_name": "PostToolUse",
                        "tool_name": "Read",
                        "tool_input": args,
                        "tool_response": {"text": content, "private": "private-audit-body"},
                    },
                    cid,
                )
            yield UserMessage(
                content=[ToolResultBlock(tool_use_id=cid, content=content, is_error=False)]
            )
            output = await call_hook(
                self.options.hooks["Stop"][0].hooks[0],
                {**data, "hook_event_name": "Stop", "stop_hook_active": False},
                None,
            )
            assert output == {}
            yield ResultMessage(
                subtype="success",
                is_error=False,
                duration_ms=1,
                duration_api_ms=1,
                num_turns=1,
                session_id="foreign" if case == "wrong-session" else sid,
            )

        async def disconnect(self):
            owners.append(asyncio.current_task())
            if case == "disconnect-error":
                raise RuntimeError("private-provider-error")

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(20, RunRequest(mode="live"))
    if case == "cancel":
        await asyncio.wait_for(entered.wait(), 5)
        await runner.cancel(handle)
    events = [e async for e in runner.events(handle)]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    assert proof["experiment"]["connection_closed"] is (case != "disconnect-error")
    assert len(owners) == 2 and owners[0] is owners[1] and not runner.active
    assert "private-provider-error" not in str(events) and "private-audit-body" not in str(proof)


def test_seven_questions_and_exact_current_excerpts():
    assert len(guide(20).quiz) == 7
    for section in source_sections(20):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]
