"""Lesson 35's host and SDK storage boundaries."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

import httpx
import pytest
from claude_agent_sdk import SessionStoreEntry

from agent_lab.api import create_app
from agent_lab.config import ROOT, Settings
from agent_lab.models import LessonError, RunRequest, lesson_request
from agent_lab.runtime import RunService
from agent_lab.session_store_lab import local_store, save_transcript
from agent_lab.sqlite_session_store import SQLiteSessionStore


@pytest.mark.parametrize("action", ["commit", "interrupted", "resume", "durable-resume"])
async def test_local_storage_actions(tmp_path: Path, action: str) -> None:
    proof = await local_store(tmp_path / "work", RunRequest(lesson_options={"action": action}))
    report = proof["experiment"]
    assert proof["experiment_passed"]
    assert report["host_transcript"]["host_boundary_verified"]
    assert report["mirror_verified"]
    assert report["session_verified"]
    assert report["mirrored_entry_types"].count("user") == (2 if action in {"resume", "durable-resume"} else 1)
    assert report["host_transcript"]["temporary_exists"] is (action == "interrupted")
    assert report["store_reopened"] is (action == "durable-resume")


@pytest.mark.parametrize("scenario", ["missing-evidence", "wrong-identity", "changed-host", "wrong-answer"])
async def test_storage_evidence_failures(tmp_path: Path, scenario: str) -> None:
    proof = await local_store(tmp_path / "work", RunRequest(scenario=scenario))
    assert not proof["experiment_passed"]


async def test_wrong_resumed_answer_needs_review(tmp_path: Path) -> None:
    proof = await local_store(tmp_path / "work", RunRequest(scenario="wrong-answer", lesson_options={"action": "resume"}))
    assert not proof["experiment_passed"]


@pytest.mark.parametrize("options,passed", [
    ({"action": "durable-resume", "flush": "batched"}, True),
    ({"action": "durable-resume", "fault": "delay-load"}, True),
    ({"enabled": False}, False),
    ({"fault": "reject-append"}, False),
])
async def test_store_controls(tmp_path: Path, options: dict, passed: bool) -> None:
    proof = await local_store(tmp_path / "work", RunRequest(lesson_options=options))
    assert proof["experiment_passed"] is passed
    report = proof["experiment"]
    if options.get("fault") == "reject-append":
        assert report["mirror_errors"] > 0
        assert report["missing_uuid_count"] > 0
    if options.get("fault") == "delay-load":
        assert any(item["method"] == "load" and item["elapsed_ms"] >= 100 for item in report["store_observations"])


def test_host_replace_boundary(tmp_path: Path) -> None:
    interrupted = save_transcript(tmp_path, "interrupted")
    assert interrupted["before_hash"] == interrupted["after_hash"]
    assert interrupted["temporary_exists"]
    committed = save_transcript(tmp_path, "commit")
    assert committed["before_hash"] != committed["after_hash"]
    assert not committed["temporary_exists"]


def test_strict_store_inputs() -> None:
    with pytest.raises(LessonError):
        lesson_request(35, RunRequest(prompt="arbitrary"))
    with pytest.raises(ValueError):
        lesson_request(35, RunRequest(lesson_options={"action": "unknown"}))
    with pytest.raises(LessonError):
        lesson_request(35, RunRequest(mode="live", scenario="missing-evidence"))


async def test_sqlite_store_survives_new_process_and_scopes_keys(tmp_path: Path) -> None:
    path = tmp_path / "session-store.sqlite3"
    store = SQLiteSessionStore(path)
    key = {"project_key": "project-a", "session_id": "session-a"}
    entry = cast(SessionStoreEntry, {"type": "user", "uuid": "one", "message": "saved"})
    marker = cast(SessionStoreEntry, {"type": "title", "message": "repeatable"})
    await store.append(key, [entry, marker])
    await store.append(key, [entry, marker])
    await store.append({**key, "subpath": "agent/one"}, [entry])
    await store.append({"project_key": "project-b", "session_id": "session-a"}, [entry])
    assert await store.load(key) == [entry, marker, marker]
    assert await store.list_subkeys(key) == ["agent/one"]
    assert len(await store.list_sessions("project-a")) == 1
    summaries = await store.list_session_summaries("project-a")
    assert len(summaries) == 1
    assert summaries[0]["session_id"] == "session-a"
    assert summaries[0]["mtime"] == (await store.list_sessions("project-a"))[0]["mtime"]
    script = (
        "import asyncio,json,sys; from pathlib import Path; "
        "from agent_lab.sqlite_session_store import SQLiteSessionStore; "
        "s=SQLiteSessionStore(Path(sys.argv[1])); "
        "print(json.dumps(asyncio.run(s.load({'project_key':'project-a','session_id':'session-a'}))))"
    )
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await child.communicate()
    assert child.returncode == 0, stderr.decode()
    assert json.loads(stdout) == [entry, marker, marker]
    await store.delete(key)
    assert await store.load(key) is None
    assert await store.list_subkeys(key) == []
    assert await store.list_session_summaries("project-a") == []
    assert len(await store.list_sessions("project-b")) == 1


async def test_scoped_session_store_routes(tmp_path: Path) -> None:
    app = create_app(RunService(Settings(data_dir=tmp_path)), with_ui=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/c35/run", json={"mode": "live"})).status_code == 403
        assert (await client.post("/api/c35/run", json={"lesson_options": {"fault": "delay-load"}})).status_code == 422
        result = (await client.post("/api/c35/run", json={"lesson_options": {"action": "durable-resume"}})).json()
        assert result["status"] == "completed"
        assert result["experiment"]["experiment_passed"]
        key = {"run_id": result["run_id"], "control_token": result["control_token"]}
        assert (await client.get("/api/c35/db", params={**key, "control_token": "invalid-token-000000"})).status_code == 403
        db = (await client.get("/api/c35/db", params=key)).json()
        assert db["uuid_coverage_verified"] and db["missing_uuid_count"] == 0
        entries = (await client.get("/api/c35/entries", params=key)).json()
        assert len(entries["local_uuids"]) == 2
        assert len(entries["stored_entries"]) == 4
        assert (await client.post("/api/c35/failures", json=key)).json()["mirror_errors"] == 0
        assert len((await client.get("/api/c35/code")).json()["sections"]) == 3
        assert len((await client.post("/api/c35/manage", json={**key, "action": "list"})).json()["sessions"]) == 1
        deleted = (await client.post("/api/c35/manage", json={**key, "action": "delete"})).json()
        assert deleted["sessions"] == []
        assert (await client.get("/api/c35/db", params=key)).json()["experiment_passed"] is False
        assert (await client.post("/api/c35/reset", json=key)).json() == {"reset": True}
        assert (await client.get("/api/c35/db", params=key)).status_code == 403


def test_reviewed_lesson35_narration_source_identity() -> None:
    manifest = json.loads((ROOT / "agent_lab/content/lesson_35_narration.json").read_text(encoding="utf-8"))
    assert manifest["lesson"] == 35
    assert manifest["status"] == "reviewed-script"
    assert manifest["audio_status"] == "recorded-needs-listening"
    assert len(manifest["sections"]) == 3
    for section in manifest["sections"]:
        path = (ROOT / section["path"]).resolve()
        assert path.is_relative_to(ROOT / "agent_lab")
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        assert hashlib.sha256(source.encode()).hexdigest() == section["reviewed_source_sha256"]
        assert 1 <= section["start_line"] <= section["end_line"] <= len(source.splitlines())
        assert section["spoken_text"]
