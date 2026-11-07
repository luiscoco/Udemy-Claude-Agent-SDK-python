"""Lesson 46's free producer uses authenticated HTTP and rejects corrupt evidence."""

import asyncio

import httpx
import pytest

from agent_lab.cache_lab import CacheObserver, evaluate_local, evaluate_native, local_action
from agent_lab.cache_wire import HAIKU, SONNET
from agent_lab.exercises import EmbeddedServer


@pytest.mark.asyncio
async def test_local_cache_actions_are_two_measured_turns() -> None:
    for action in ("anatomy", "switches", "breakers", "model-switch"):
        report = await local_action(action)
        assert report["experiment_passed"]
        assert len(report["turns"]) == 2
        assert all(row["status"] == 200 for row in report["receipts"])
        assert report["native"] is False
        assert report["turns"][1]["usage"]["read"] == 1200
    assert (await local_action("switches", ttl="off"))["turns"][1]["usage"]["read"] == 0
    assert (await local_action("breakers", prefix="changed"))["turns"][1]["usage"]["read"] == 0
    for scenario in ("missing", "foreign", "failed"):
        assert not (await local_action("anatomy", scenario=scenario))["experiment_passed"]


@pytest.mark.asyncio
async def test_all_fixed_local_cache_variants_are_bounded() -> None:
    for ttl in ("5m", "1h", "off"):
        report = await local_action("switches", ttl=ttl)
        assert report["experiment_passed"]
        assert len(report["receipts"]) == 2
        assert report["turns"][0]["usage"]["write1h"] == (1200 if ttl == "1h" else 0)
    for prefix in ("stable", "changed", "tool", "dynamic", "short"):
        report = await local_action("breakers", prefix=prefix)
        assert report["experiment_passed"]
        assert report["native"] is False
    for policy in ("cap", "allow"):
        report = await local_action("model-switch", policy=policy)
        assert report["experiment_passed"]
        assert report["native"] is False


@pytest.mark.asyncio
async def test_observer_rejects_bad_credentials_and_closes_listener() -> None:
    observer = CacheObserver("operation", "ownednonce", "anatomy", "5m", "stable")
    async with EmbeddedServer(observer).running() as base:
        observer.port = int(base.rsplit(":", 1)[1])
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.post(base + "/v1/messages", json={})
            assert response.status_code == 401
            assert observer.receipts == []
    async with httpx.AsyncClient(timeout=0.5, trust_env=False) as client:
        with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
            await client.post(base + "/v1/messages", json={})


def test_evaluator_rejects_mutated_identity() -> None:
    # Construct the passing report through the real local transport, then mutate
    # only the correlated identity, leaving its narrative and counters untouched.
    report = asyncio.run(local_action("anatomy"))
    report["receipts"][1]["message_id"] = "msg_foreign"
    assert not evaluate_local(report)


def test_native_evaluator_requires_independent_usage_and_allows_cold_cap_switch() -> None:
    def usage() -> dict:
        return {"input_tokens": 1, "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0, "output_tokens": 1}

    frames = []
    receipts = []
    for turn, model in ((1, HAIKU), (2, SONNET)):
        frames.extend([
            {"kind": "init", "turn": turn, "session_id": "session-46", "model": model},
            {"kind": "assistant", "turn": turn, "message_id": f"msg_{turn}",
             "session_id": "session-46", "model": model},
            {"kind": "result", "turn": turn, "session_id": "session-46",
             "subtype": "success", "is_error": False,
             "total_cost_usd": turn * 0.001, "usage": usage()},
        ])
        receipts.append({"operation": "operation-46", "turn": turn, "status": 200,
                         "authenticated": True, "nonce_match": True,
                         "message_id": f"msg_{turn}", "model": model,
                         "usage": {"input": 1, "write5m": 0, "write1h": 0,
                                   "read": 0, "output": 1}})
    frames.append({"kind": "switch-result", "accepted": True})
    report = {"operation": "operation-46", "action": "model-switch", "policy": "cap",
              "source_label": "native SDK subprocess", "closed": True, "forwarded": 2,
              "frames": frames, "receipts": receipts,
              "hooks": [{"kind": "pre-model-switch", "source": "native-hook",
                         "from_model": HAIKU, "to_model": SONNET,
                         "prompt_cache_warm": False, "estimated_cache_write_usd": 0.01,
                         "decision": "allow"},
                        {"kind": "post-model-switch", "source": "native-hook",
                         "from_model": HAIKU, "to_model": SONNET}]}
    assert evaluate_native(report)
    frames[5]["usage"] = {**usage(), "cache_read_input_tokens": 3}
    assert not evaluate_native(report)
