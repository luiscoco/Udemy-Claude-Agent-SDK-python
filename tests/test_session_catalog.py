"""Actual owned SDK catalog operations and guarded provider lifecycle, without paid calls."""

import asyncio
import hashlib
import os
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import ResultMessage, SystemMessage

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.foundation_models import SCENARIOS
from agent_lab.foundations import source_sections
from agent_lab.learning import check_evidence, guide
from agent_lab.models import RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.session_catalog import FIXTURE_SESSION, operate_catalog, write_catalog_fixture


@pytest.mark.parametrize("action", ["inspect", "rename-tag", "fork", "delete"])
@pytest.mark.parametrize("scenario", SCENARIOS[19])
async def test_actual_sdk_catalog_actions_and_negative_evidence(tmp_path, action, scenario):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(19, RunRequest(lesson_options={"action": action}, scenario=scenario))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (scenario == "success")
    assert check_evidence(19, proof, status="completed").status == (
        "passed" if scenario == "success" else "needs-review"
    )
    assert check_evidence(19, proof, status="completed", mode="live").status == "needs-review"
    if scenario == "success":
        record = proof["experiment"]["catalog"]
        assert record["isolation"] == {
            "empty_config_session_count": 0,
            "other_project_session_count": 0,
        }
        assert record["before"]["message_session_ids"] == [FIXTURE_SESSION]
        if action == "fork":
            assert set(record["mutation"]["fork"]["message_uuids"]).isdisjoint(
                record["before"]["message_uuids"]
            )
            assert record["mutation"]["original_file_unchanged"]
        if action == "delete":
            assert (
                not record["after"]["info_found"] and not record["mutation"]["original_file_exists"]
            )


@pytest.mark.parametrize("offset", [0, 1, 20])
async def test_empty_and_nonempty_pages_are_checked_against_actual_transcript(tmp_path, offset):
    runner = RunService(Settings(data_dir=tmp_path))
    events = [
        e
        async for e in runner.events(
            runner.start(19, RunRequest(lesson_options={"page_size": 1, "offset": offset}))
        )
    ]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"]
    before = proof["experiment"]["catalog"]["before"]
    assert len(before["message_page"]) == (0 if offset == 20 else 1)
    assert before["message_page_matches"] and before["session_page_matches"]


async def test_catalog_isolation_does_not_mutate_parent_env_or_personal_transcript(
    tmp_path, monkeypatch
):
    work = tmp_path / "owned" / "work"
    config = tmp_path / "owned" / "config"
    personal = tmp_path / "personal-config"
    work.mkdir(parents=True)
    write_catalog_fixture(work, personal, "PERSONAL-CONVERSATION-MARKER")
    personal_file = next(personal.glob("projects/*/*.jsonl"))
    original = personal_file.read_bytes()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(personal))
    prompt = "OWNED-SESSION"
    write_catalog_fixture(work, config, prompt)
    request = lesson_request(19, {"lesson_options": {"action": "delete"}})
    proof = await operate_catalog(
        work, config, FIXTURE_SESSION, request, hashlib.sha256(prompt.encode()).hexdigest()
    )
    assert not proof["after"]["info_found"]
    assert personal_file.read_bytes() == original and os.environ["CLAUDE_CONFIG_DIR"] == str(
        personal
    )
    assert "PERSONAL-CONVERSATION-MARKER" not in str(proof)


@pytest.mark.parametrize(
    "options",
    [
        {"session_id": FIXTURE_SESSION},
        {"config": "../private"},
        {"action": "resume-foreign"},
        {"page_size": True},
        {"page_size": 0},
        {"offset": -1},
        {"offset": 21},
        {"title": "   "},
        {"title": "bad\nmetadata"},
        {"tag": "private"},
        {"title": "x" * 81},
    ],
)
async def test_invalid_catalog_inputs_create_no_task_files_or_client(tmp_path, options):
    runner = RunService(Settings(data_dir=tmp_path))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, with_ui=False)), base_url="http://test"
    ) as client:
        response = await client.post("/api/lessons/19/run", json={"lesson_options": options})
    assert response.status_code == 422
    assert not runner.active and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "wrong-session",
        "missing-init",
        "missing-result",
        "no-transcript",
        "wrong-prompt",
        "disconnect-error",
        "auth-retry",
        "cancel",
    ],
)
async def test_live_catalog_waits_for_closed_owned_session_before_local_operations(
    tmp_path, monkeypatch, case
):
    import agent_lab.sdk as sdk
    import agent_lab.session_catalog as catalog

    monkeypatch.setattr(sdk, "require_live_access", lambda settings: None)
    monkeypatch.setattr(sdk, "resolve_cli_path", lambda settings: "injected-cli")
    owners, operations, clients = [], [], []
    entered = asyncio.Event()
    original_operate = catalog.operate_catalog

    async def observe_operation(*args):
        assert clients[0].closed
        operations.append(True)
        return await original_operate(*args)

    monkeypatch.setattr(catalog, "operate_catalog", observe_operation)

    class Client:
        def __init__(self, options):
            self.options = options
            self.closed = False
            clients.append(self)

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
            if case != "missing-init":
                yield SystemMessage(subtype="init", data={"session_id": FIXTURE_SESSION})
            if case != "missing-result":
                yield ResultMessage(
                    subtype="success",
                    is_error=False,
                    duration_ms=1,
                    duration_api_ms=1,
                    num_turns=1,
                    session_id="00000000-0000-4000-8000-000000000099"
                    if case == "wrong-session"
                    else FIXTURE_SESSION,
                )

        async def disconnect(self):
            owners.append(asyncio.current_task())
            if case != "no-transcript":
                write_catalog_fixture(
                    Path(self.options.cwd),
                    Path(self.options.env["CLAUDE_CONFIG_DIR"]),
                    "foreign prompt" if case == "wrong-prompt" else self.prompt,
                )
            if case == "disconnect-error":
                raise RuntimeError("private-provider-detail")
            self.closed = True

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Client)
    runner = RunService(Settings(data_dir=tmp_path, enable_live=True))
    handle = runner.start(19, RunRequest(mode="live", lesson_options={"action": "rename-tag"}))
    if case == "cancel":
        await asyncio.wait_for(entered.wait(), 5)
        await runner.cancel(handle)
    events = [e async for e in runner.events(handle)]
    proof = next(e.data["result"] for e in events if e.kind == "evidence")
    assert proof["experiment_passed"] is (case == "success")
    assert proof["experiment"]["connection_closed"] is (case != "disconnect-error")
    assert len(owners) == 2 and owners[0] is owners[1] and not runner.active
    assert len(operations) == (1 if case in {"success", "no-transcript", "wrong-prompt"} else 0)
    assert "private-provider-detail" not in str(events)
    if case == "success":
        assert proof["experiment"]["catalog"]["after"]["title"] == "Lesson 19 reviewed session"
    else:
        for file in tmp_path.glob("*/config/projects/*/*.jsonl"):
            assert "custom-title" not in file.read_text()


async def test_cancelled_catalog_child_is_killed_and_awaited(tmp_path, monkeypatch):
    import agent_lab.session_catalog as catalog

    entered = asyncio.Event()
    flags = []

    class Process:
        returncode = None

        async def communicate(self, data):
            entered.set()
            await asyncio.Event().wait()

        def kill(self):
            self.returncode = -1
            flags.append("killed")

        async def wait(self):
            flags.append("awaited")

    async def create(*args, **kwargs):
        return Process()

    monkeypatch.setattr(catalog.asyncio, "create_subprocess_exec", create)
    task = asyncio.create_task(
        operate_catalog(
            tmp_path / "work",
            tmp_path / "config",
            FIXTURE_SESSION,
            lesson_request(19, {}),
            "digest",
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert flags == ["killed", "awaited"]


def test_catalog_title_normalizes_and_source_excerpts_match():
    assert (
        lesson_request(19, {"lesson_options": {"title": "  Reviewed  "}}).lesson_options["title"]
        == "Reviewed"
    )
    assert len(guide(19).quiz) == 7
    for section in source_sections(19):
        lines = (
            (Path(__file__).resolve().parents[1] / section["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert section["code"].splitlines() == lines[section["start"] - 1 : section["end"]]


@pytest.mark.parametrize(
    "tamper",
    [
        "missing-digest",
        "missing-after-info",
        "rename-no-effect",
        "fork-wrong-info",
        "delete-stale-messages",
    ],
)
async def test_catalog_evaluator_rejects_incomplete_or_inconsistent_effects(tmp_path, tamper):
    from copy import deepcopy

    from agent_lab.foundations import Evidence
    from agent_lab.session_catalog import catalog_report

    action = {
        "rename-no-effect": "rename-tag",
        "fork-wrong-info": "fork",
        "delete-stale-messages": "delete",
    }.get(tamper, "inspect")
    request = lesson_request(19, {"lesson_options": {"action": action}})
    runner = RunService(Settings(data_dir=tmp_path))
    events = [e async for e in runner.events(runner.start(19, request))]
    experiment = next(e.data["result"]["experiment"] for e in events if e.kind == "evidence")
    assert experiment["experiment_passed"]
    state = Evidence(
        19,
        experiment["run"],
        tmp_path / experiment["run"] / "work",
        request.lesson_options,
        experiment["source"],
    )
    state.initialized = experiment["initialization"]
    state.terminals = experiment["terminal_results"]
    state.configured = experiment["configured"]
    catalog = deepcopy(experiment["catalog"])
    if tamper == "missing-digest":
        catalog["before"].pop("visible_content_digest")
        catalog["after"].pop("visible_content_digest")
    elif tamper == "missing-after-info":
        catalog["after"]["info_found"] = False
    elif tamper == "rename-no-effect":
        catalog["mutation"]["original_file_unchanged"] = True
    elif tamper == "fork-wrong-info":
        catalog["mutation"]["fork"]["info_session_id"] = "foreign"
    elif tamper == "delete-stale-messages":
        catalog["after"]["message_uuids"] = ["stale-message"]
    digest = hashlib.sha256(
        (request.prompt + "\nReply briefly: SESSION-CATALOG-OK.").encode()
    ).hexdigest()
    assert not catalog_report(state, catalog, True, digest)["experiment_passed"]
