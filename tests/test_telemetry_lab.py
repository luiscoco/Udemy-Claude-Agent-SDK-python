"""Owned OTLP collector and local Lesson 44 route checks."""

import asyncio
import copy
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from agent_lab.api import create_app
from agent_lab.config import Settings
from agent_lab.exercises import EmbeddedServer
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.telemetry_collector import Collector, aggregate
from agent_lab.telemetry_lab import ACTIONS, evaluate_live, local_action, payload, run, state


@pytest.mark.parametrize("action", ACTIONS)
async def test_local_telemetry_actions_have_received_exports(action):
    report = await local_action(action)
    assert report["experiment_passed"], report
    assert report["closed"]
    assert "L44-CONTENT-" not in json.dumps(report)
    for lane in report["lanes"]:
        assert {item["signal"] for item in lane["receipts"]} == {"metrics", "logs", "traces"}
        assert all(item["count"] > 0 and item["sha256"] for item in lane["receipts"])
        assert not lane["raw_body_retained"]
        assert all(row["sender"] == "fixture" for row in lane["records"] if row["signal"] != "traces"
                   or row["sender"] != "host")


@pytest.mark.parametrize("scenario", ["missing", "foreign", "failed"])
async def test_telemetry_faults_fail_before_evaluation(scenario):
    report = await local_action("signals", scenario)
    assert not report["experiment_passed"]


async def test_collector_rejects_bad_envelopes_and_auth():
    collector = Collector("run-44", ["main"], "private")
    async with EmbeddedServer(collector).running() as base:
        collector.base = base
        url = base + "/r/run-44/main/v1/metrics"
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            assert (await client.post(url, json={})).status_code == 401
            headers = {"Authorization": "Bearer private"}
            assert (await client.post(url, content=b"bad", headers={
                **headers, "Content-Type": "application/json"})).status_code == 400
            assert (await client.post(url, json={"resourceLogs": []}, headers=headers)).status_code == 400
            assert (await client.post(url, content=b"body", headers={
                **headers, "Content-Type": "application/x-protobuf"})).status_code == 415
            assert (await client.post(url, json={"resourceMetrics": []}, headers=headers)).status_code == 200
            assert collector.receipts[-1]["count"] == 0
            malformed = payload("metrics", "run-44", "main")
            malformed["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]["asDouble"] = "NaN"
            assert (await client.post(url, json=malformed, headers=headers)).status_code == 400
            assert (await client.post(url, json=payload("metrics", "run-44", "main"),
                                      headers=headers)).status_code == 200
    assert len(collector.records) == 2


async def test_owned_listener_closes_and_state_rejects_foreign_pointer(tmp_path):
    collector = Collector("run-44", ["main"])
    async with EmbeddedServer(collector).running() as base:
        collector.base = base
        port = urlsplit(base).port
    assert port is not None
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    good = await run(tmp_path, Settings(), "signals", "local")
    assert state(tmp_path)["run_id"] == good["run_id"]
    (tmp_path / "latest.json").write_text(json.dumps({"run_id": "../foreign"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid Lesson 44 state"):
        state(tmp_path)




@pytest.mark.parametrize("bad_trace", [False, True])
async def test_injected_sdk_messages_and_real_collector_http(tmp_path, monkeypatch, bad_trace):
    from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, UserMessage
    from claude_agent_sdk.types import ToolResultBlock, ToolUseBlock

    import agent_lab.telemetry_lab as lab

    session_id = "11111111-1111-4111-8111-111111111111"
    result_id = "22222222-2222-4222-8222-222222222222"
    tool_id = "toolu_test_44"

    class InjectedClient:
        def __init__(self, options):
            self.options = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_response(self):
            from agent_lab.telemetry_lab import attrs, payload

            work = Path(self.options.cwd)
            notes = work / "notes.txt"
            pre = self.options.hooks["PreToolUse"][0].hooks[0]
            post = self.options.hooks["PostToolUse"][0].hooks[0]
            assert (await pre({"tool_name": "Read", "tool_input": {
                "file_path": str(notes)}}, tool_id, None))["hookSpecificOutput"]["permissionDecision"] == "allow"
            await post({"tool_name": "Read", "tool_input": {"file_path": str(notes)}}, tool_id, None)
            endpoint = self.options.env["OTEL_EXPORTER_OTLP_ENDPOINT"]
            run_id, lane = endpoint.split("/")[-2:]
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                for signal in ("metrics", "logs", "traces"):
                    body = payload(signal, run_id, lane)
                    key = {"metrics": "resourceMetrics", "logs": "resourceLogs",
                           "traces": "resourceSpans"}[signal]
                    scope_key = {"metrics": "scopeMetrics", "logs": "scopeLogs",
                                 "traces": "scopeSpans"}[signal]
                    leaf_key = {"metrics": "metrics", "logs": "logRecords",
                                "traces": "spans"}[signal]
                    for scope in body[key][0][scope_key]:
                        leaves = scope[leaf_key]
                        if signal == "metrics":
                            leaves = [point for metric in leaves for point in metric["sum"]["dataPoints"]]
                        for item in leaves:
                            item["attributes"] = attrs({"session.id": session_id, "tool_use_id": tool_id})
                            if bad_trace and signal == "traces":
                                item["traceId"] = "invalid"
                    response = await client.post(endpoint + "/v1/" + signal, json=body)
                    assert response.status_code == (400 if bad_trace and signal == "traces" else 200)
            yield SystemMessage(subtype="init", data={"session_id": session_id})
            yield AssistantMessage(content=[ToolUseBlock(id=tool_id, name="Read",
                input={"file_path": str(notes)})], model="test")
            yield UserMessage(content=[ToolResultBlock(tool_use_id=tool_id,
                content=notes.read_text(encoding="utf-8"))])
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                is_error=False, num_turns=1, session_id=session_id,
                total_cost_usd=0.001, uuid=result_id)

    monkeypatch.setattr(lab, "ClaudeSDKClient", InjectedClient)
    monkeypatch.setattr(lab, "require_live_access", lambda settings: None)
    monkeypatch.setattr(lab, "resolve_cli_path", lambda settings: "claude")
    report = await lab.live_action(tmp_path, Settings(), "signals")
    assert report["experiment_passed"] is not bad_trace
    assert all(receipt["sender"] == "subprocess" and receipt["count"] > 0
               for receipt in report["lanes"][0]["receipts"])





async def test_stop_closes_active_telemetry_listener(monkeypatch):
    import agent_lab.telemetry_lab as lab

    entered = asyncio.Event()
    created = []

    class ObservedCollector(Collector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    async def stalled_post(self, *args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(lab, "Collector", ObservedCollector)
    monkeypatch.setattr(httpx.AsyncClient, "post", stalled_post)
    task = asyncio.create_task(lab.local_action("signals"))
    await asyncio.wait_for(entered.wait(), 5)
    assert created and created[0].base
    port = urlsplit(created[0].base).port
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port is not None
    with pytest.raises(OSError):
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass

async def test_telemetry_run_cancel_ends_without_passed_summary(tmp_path, monkeypatch):
    import agent_lab.telemetry_lab as lab

    entered = asyncio.Event()

    async def held_action(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(lab, "local_action", held_action)
    runner = RunService(Settings(data_dir=tmp_path, timeout_seconds=10))
    handle = runner.start(44, RunRequest(mode="offline", lesson_options={"action": "signals"}))
    await asyncio.wait_for(entered.wait(), 5)
    await runner.cancel(handle)
    events = [event async for event in runner.events(handle)]
    assert events[-1].kind == "done" and events[-1].data["status"] == "cancelled"
    assert not list(tmp_path.rglob("c44-telemetry/latest.json"))
    await runner.close()

def test_saved_native_evidence_rejects_missing_and_foreign_records():
    path = Path(".lab-data/lesson-live-smoke/lesson-44-20261106T084709867568Z/report.json")
    if not path.is_file():
        pytest.skip("Live acceptance report is absent in a fresh checkout")
    record = next(row for row in json.loads(path.read_text(encoding="utf-8"))["scenarios"]
                  if row["case"] == "signals")
    good = record["experiment"]
    assert evaluate_live(good)
    missing = copy.deepcopy(good)
    missing["lanes"][0]["receipts"] = []
    assert not evaluate_live(missing)
    foreign = copy.deepcopy(good)
    for row in foreign["lanes"][0]["records"]:
        row["resource"]["lab.run"] = "foreign"
    assert not evaluate_live(foreign)


def test_cumulative_reducer_keeps_latest_sample():
    rows = [
        {"signal": "metrics", "resource": {"service.name": "a"}, "name": "cost",
         "unit": "USD", "kind": "sum", "temporality": 2, "attributes": {},
         "value": 0.02, "timestamp": 20},
        {"signal": "metrics", "resource": {"service.name": "a"}, "name": "cost",
         "unit": "USD", "kind": "sum", "temporality": 2, "attributes": {},
         "value": 0.01, "timestamp": 10},
        {"signal": "metrics", "resource": {"service.name": "b"}, "name": "cost",
         "unit": "USD", "kind": "sum", "temporality": 2, "attributes": {},
         "value": 9.0, "timestamp": 30},
    ]
    series = aggregate(rows)
    assert len(series) == 2
    assert next(item["value"] for item in series if item["resource"]["service.name"] == "a") == 0.02


async def test_routes_strict_and_local(tmp_path):
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/c44/facts")).status_code == 200
        assert (await client.get("/api/c44/state")).status_code == 404
        assert (await client.post("/api/c44/signals", json={"url": "https://foreign"})).status_code == 400
        assert (await client.post("/api/c44/signals", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c44/signals", json={"mode": "live",
                    "consent": True, "scenario": "missing"})).status_code == 400
        for action in ACTIONS:
            response = await client.post("/api/c44/" + action, json={})
            assert response.status_code == 200, response.text
            assert response.json()["experiment_passed"]
        assert (await client.get("/api/c44/state")).json()["action"] == "collector"
        assert (await client.get("/api/c44/code")).status_code == 200


def test_portal_live_requires_fresh_consent():
    with pytest.raises(LessonError, match="Confirm this fresh"):
        lesson_request(44, RunRequest(mode="live", lesson_options={"action": "signals"}))
    accepted = lesson_request(44, RunRequest(mode="live", lesson_options={
        "action": "signals", "consent": True}))
    assert accepted.lesson_options["consent"] is True


async def test_operation_slot_blocks_overlap(tmp_path, monkeypatch):
    import agent_lab.api_telemetry as routes

    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_run(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"action": "signals", "mode": "local", "source_label": "test fixture",
                "scenario": "normal", "run_id": "11111111-1111-4111-8111-111111111111",
                "lanes": [], "closed": True, "experiment_passed": True}

    monkeypatch.setattr(routes, "run", slow_run)
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/c44/signals", json={}))
        await asyncio.wait_for(entered.wait(), 3)
        assert (await client.get("/api/c44/state")).status_code == 409
        assert (await client.post("/api/c44/privacy", json={})).status_code == 409
        release.set()
        assert (await first).status_code == 200
