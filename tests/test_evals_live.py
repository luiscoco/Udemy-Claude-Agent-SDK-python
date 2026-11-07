"""Injected native receipts exercise real isolated host effects without paid calls."""

import asyncio

import pytest

import agent_lab.evals_live as live
from agent_lab.config import Settings
from agent_lab.desk_lab import local_chat
from agent_lab.evals_core import cases


@pytest.mark.asyncio
async def test_injected_agent_trials_use_isolated_host_effects_and_known_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "private_key", lambda: "injected-private-key")
    by_case = {row["caseId"]: row for row in cases()}

    async def fake_native(store, approver, *, customer, intent, message, on_approval, **_kwargs):
        report = await local_chat(store, approver, customer=customer, intent=intent,
                                  message=message, on_approval=on_approval)
        case_id = "denied-refund" if intent == "refund" else intent
        report.update({"visible_reply": by_case[case_id]["baselineReply"],
                       "observed_models": [live.HAIKU], "error_class": None,
                       "frames": [{"kind": "init", "session_id": "owned"},
                                  {"kind": "result", "session_id": "owned", "subtype": "success",
                                   "is_error": False, "cost_usd": 0.01}]})
        return report

    monkeypatch.setattr(live, "native_chat", fake_native)
    report = await live.native_eval(tmp_path, Settings(enable_live=True, data_dir=tmp_path),
                                    variant="baseline", trials=1, judge="heuristic",
                                    budget=1.0, consent=True)
    assert report["complete"] and len(report["rows"]) == 3
    assert report["modelCalls"] == 3 and report["actualBilledUsd"] == pytest.approx(0.03)
    assert all(row["business"]["scope"] and row["business"]["effect"] and row["business"]["money"]
               for row in report["rows"])
    assert all(row["source"] == "native-python-sdk/real-host-effects" for row in report["rows"])
    assert len(list((tmp_path / "isolated" / report["id"]).glob("*/store.json"))) == 3

    abort = asyncio.Event()
    abort.set()
    stopped = await live.native_eval(tmp_path, Settings(enable_live=True, data_dir=tmp_path),
                                      variant="baseline", trials=1, judge="heuristic",
                                      budget=1.0, consent=True, abort=abort)
    assert not stopped["complete"] and stopped["rows"] == [] and stopped["modelCalls"] == 0


@pytest.mark.asyncio
async def test_malformed_model_judge_keeps_known_partial_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "private_key", lambda: "injected-private-key")

    async def fake_native(store, approver, *, customer, intent, message, on_approval, **_kwargs):
        report = await local_chat(store, approver, customer=customer, intent=intent,
                                  message=message, on_approval=on_approval)
        report.update({"visible_reply": "I understand. Please contact support next.",
                       "observed_models": [live.HAIKU], "error_class": None,
                       "frames": [{"kind": "init", "session_id": "owned"},
                                  {"kind": "result", "session_id": "owned", "subtype": "success",
                                   "is_error": False, "cost_usd": 0.01}]})
        return report

    async def bad_judge(*_args, **_kwargs):
        return None, 0.005, "invalid-judge-terminal-or-schema", {"terminalCount": 1, "costUsd": 0.005}

    monkeypatch.setattr(live, "native_chat", fake_native)
    monkeypatch.setattr(live, "model_judge", bad_judge)
    report = await live.native_eval(tmp_path, Settings(enable_live=True, data_dir=tmp_path),
                                    variant="baseline", trials=1, judge="model",
                                    budget=1.0, consent=True)
    assert not report["complete"] and len(report["rows"]) == 1
    assert report["modelCalls"] == 2 and report["actualBilledUsd"] is None
    assert report["knownPartialCostUsd"] == pytest.approx(0.015)
    assert report["rows"][0]["judgeError"] == "invalid-judge-terminal-or-schema"
