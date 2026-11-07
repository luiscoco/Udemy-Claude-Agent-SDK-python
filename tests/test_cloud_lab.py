"""Lesson 45 authored local actions and evidence validation."""

import copy
import uuid

import pytest

from agent_lab.cloud_lab import evaluate_local, evaluate_native, local_action
from agent_lab.cloud_wire import HAIKU, PROFILE


@pytest.mark.asyncio
@pytest.mark.parametrize("action,expected", [
    ("catalog", 5), ("same", 5), ("auth", 1), ("models", 1), ("failures", 2),
])
async def test_five_local_actions(action: str, expected: int) -> None:
    result = await local_action(action)
    assert result["experiment_passed"] and len(result["lanes"]) == expected
    assert all(lane["listener_closed"] and lane["forwarded"] == 0 for lane in result["lanes"])


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_case", ["sigv4", "bearer", "wif", "foundry", "gateway"])
async def test_fixed_auth_cases(auth_case: str) -> None:
    result = await local_action("auth", auth_case=auth_case)
    assert result["experiment_passed"]
    assert result["lanes"][0]["rejected_statuses"] == [401, 401]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_case", ["alias", "profile", "region"])
async def test_fixed_model_cases(model_case: str) -> None:
    assert (await local_action("models", model_case=model_case))["experiment_passed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["missing", "foreign", "failed"])
async def test_faults_alter_evidence(scenario: str) -> None:
    result = await local_action("same", scenario=scenario)
    assert not result["experiment_passed"]


@pytest.mark.asyncio
async def test_uncorrelated_receipt_cannot_pass() -> None:
    report = await local_action("same")
    tampered = copy.deepcopy(report)
    tampered["lanes"][0]["response_id"] = "msg_foreign"
    assert not evaluate_local(tampered)


def test_native_identity_chain_and_profile_usage() -> None:
    run_id, session, terminal_id = (str(uuid.uuid4()) for _ in range(3))
    message_id = "msg_owned_45"
    report = {"run_id": run_id, "provider": "bedrock", "mode": "live", "closed": True,
              "inspect_only": False, "model_case": "profile", "auth_case": "bearer",
              "marker": "L45-OWNED", "forwarded": 1,
              "frames": [{"kind": "catalog", "account_provider": "bedrock", "models": [
                  {"value": "haiku", "display_name": "Haiku"}]},
                  {"kind": "init", "session_id": session, "model": PROFILE},
                  {"kind": "assistant", "id": message_id, "model": HAIKU, "session_id": session},
                  {"kind": "result", "uuid": terminal_id, "session_id": session,
                   "subtype": "success", "is_error": False, "cost_usd": 0.001,
                   "model_usage": [PROFILE]}],
              "receipts": [{"run_id": run_id, "provider": "bedrock", "lane": "bedrock",
                            "kind": "model", "status": 200, "upstream_status": 200,
                            "auth_verdict": True, "canonical_model": HAIKU,
                            "marker_seen": "L45-OWNED", "wire_model": PROFILE,
                            "message_id": message_id, "auth_kind": "bearer"}]}
    assert evaluate_native(report)
    tampered = copy.deepcopy(report)
    tampered["receipts"][0]["message_id"] = "msg_foreign"
    assert not evaluate_native(tampered)
    tampered = copy.deepcopy(report)
    tampered["receipts"][0]["auth_verdict"] = False
    assert not evaluate_native(tampered)
    tampered = copy.deepcopy(report)
    tampered["receipts"][0]["wire_model"] = HAIKU
    assert not evaluate_native(tampered)
    auth = copy.deepcopy(report)
    auth["auth_probes_required"] = True
    auth["auth_probe_statuses"] = [401, 401]
    auth["receipts"].extend([{**auth["receipts"][0], "kind": "catalog", "status": 401,
                               "auth_verdict": False, "upstream_status": None} for _ in range(2)])
    assert evaluate_native(auth)
    auth["auth_probe_statuses"] = [401]
    assert not evaluate_native(auth)
