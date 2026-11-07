"""Lesson 48 exact policy, real local effects and bounded evidence."""

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
import pytest

from agent_lab.exercises import EmbeddedServer
from agent_lab.hardening_lab import ACTIONS, LeakCollector, evaluate, local_action
from agent_lab.hardening_native import ModelObserver
from agent_lab.hardening_policy import (
    admission,
    child_environment,
    contains_marker,
    fixed_command,
    inspect_environment,
    parse_fixed_command,
    rewrite_known_output,
)


def test_fixed_argv_admission_environment_and_known_marker_limit(tmp_path: Path) -> None:
    work, outside, home = (tmp_path / name for name in ("work", "outside", "home"))
    for path in (work, outside, home):
        path.mkdir()
    script = work / "probe.py"
    script.write_text("pass\n")
    url = "http://127.0.0.1:43120/owned/nonce"
    canonical = fixed_command(script, "environment")
    assert parse_fixed_command(canonical, Path(sys.executable), script, ("environment", url))
    assert parse_fixed_command(f'"{sys.executable}" "{script}" environment',
                               Path(sys.executable), script, ("environment", url))
    for changed in (canonical + " extra", canonical + "; echo leak", canonical + "\n",
                    canonical.replace("environment", "$(whoami)"),
                    canonical.replace(sys.executable.replace("\\", "/"), "python")):
        assert parse_fixed_command(changed, Path(sys.executable), script,
                                   ("environment", url)) is None
    assert admission("Read", {"file_path": str(work / ".env")}, guarded=False,
                     work=work, outside=outside, executable=Path(sys.executable),
                     script=script, collector_url=url)[0]
    assert not admission("Read", {"file_path": str(work / ".env")}, guarded=True,
                         work=work, outside=outside, executable=Path(sys.executable),
                         script=script, collector_url=url)[0]
    assert not admission("Bash", {"command": fixed_command(script, url)}, guarded=True,
                         work=work, outside=outside, executable=Path(sys.executable),
                         script=script, collector_url=url)[0]
    env = child_environment(home, "child", url, contrast=False,
                            synthetic_application_value="LAB48_ENV_fixture")
    inspected = inspect_environment(env, "LAB48_ENV_fixture", "child", "host")
    assert not inspected["synthetic_inherited"] and inspected["generated_differs_from_host"]
    assert not any(name in env for name in ("AWS_SECRET_ACCESS_KEY", "LAB_APPLICATION_SECRET"))
    rewritten, receipt = rewrite_known_output({"content": "LAB48_FILE_fixture"},
                                               ("LAB48_FILE_fixture",))
    assert rewritten == {"content": "[REDACTED]"}
    assert receipt["found_count"] == 1 and receipt["after_contains"] is False
    encoded = base64.b64encode(b"LAB48_FILE_fixture").decode()
    untouched, limited = rewrite_known_output({"content": encoded}, ("LAB48_FILE_fixture",))
    assert untouched["content"] == encoded and limited["after_contains"] is True
    assert contains_marker(encoded, ("LAB48_FILE_fixture",))


@pytest.mark.asyncio
async def test_local_actions_have_real_effects_and_guarded_denials() -> None:
    for action in ACTIONS:
        report = await local_action(action)
        assert report["experiment_passed"], action
        assert evaluate(report)
        assert report["native"] is False
        assert all(lane["closed"] for lane in report["lanes"])
        assert all(lane["baseline_receipt"] for lane in report["lanes"])
        assert all(value is False for key, value in report["lanes"][1]["snapshot"].items()
                   if key in {"file_canary_exposed", "outside_canary_exposed",
                              "env_canary_exposed", "outside_write", "collector_leak"})
        assert "LAB48_FILE_" not in json.dumps(report)
        assert "LAB48_OUTSIDE_" not in json.dumps(report)
        assert "LAB48_ENV_" not in json.dumps(report)
    permissions = await local_action("permissions")
    assert permissions["lanes"][0]["snapshot"]["outside_write"]
    assert not permissions["lanes"][1]["snapshot"]["outside_write"]
    lockdown = await local_action("lockdown")
    assert lockdown["lanes"][0]["environment"]["synthetic_inherited"]
    assert not lockdown["lanes"][1]["environment"]["synthetic_inherited"]
    secrets = await local_action("secrets")
    assert secrets["lanes"][1]["calls"][0]["post"]["found_count"] > 0
    injection = await local_action("injection")
    assert injection["lanes"][1]["calls"][0]["label"] == "ticket"
    assert injection["lanes"][1]["calls"][0]["pre_allowed"]


@pytest.mark.asyncio
async def test_corrupt_local_scenarios_fail() -> None:
    for scenario in ("missing", "foreign", "failed", "leaked"):
        assert not (await local_action("secrets", scenario))["experiment_passed"]


@pytest.mark.asyncio
async def test_collector_exact_path_host_limit_and_tcp_closure() -> None:
    collector = LeakCollector("nonce48", ("LAB48_FILE_fixture",))
    async with EmbeddedServer(collector).running() as base:
        collector.port = int(base.rsplit(":", 1)[1])
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.post(base + "/owned/nonce48", content=b"baseline")).status_code == 200
            assert (await client.post(base + "/owned/other", content=b"x")).status_code == 404
            assert (await client.post(base + "/owned/nonce48", headers={"Origin": "http://x"},
                                      content=b"x")).status_code == 404
            assert (await client.post(base + "/owned/nonce48", content=b"x" * 4097)).status_code == 413
            assert len(collector.hits) == 1
    with pytest.raises(OSError):
        reader, writer = await asyncio.open_connection("127.0.0.1", collector.port)
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_model_observer_rejects_unauthorized_or_unowned_requests() -> None:
    observer = ModelObserver("operation", "nonce48", ("LAB48_FILE_fixture",), "host-private-key")
    observer.port = 43129
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observer),
                                 base_url="http://127.0.0.1:43129") as client:
        assert (await client.post("/v1/other", json={})).status_code == 404
        assert (await client.post("/v1/messages", json={})).status_code == 401
        assert (await client.post("/v1/messages", headers={"x-api-key": observer.child_key},
                                  json={"model": "other", "prompt": "nonce48"})).status_code == 403
        assert (await client.post("/v1/messages", headers={"x-api-key": observer.child_key,
                                                           "Origin": "http://attacker"},
                                  json={"model": "claude-haiku-4-5-20251001",
                                        "prompt": "nonce48"})).status_code == 404
    assert observer.receipts == []
