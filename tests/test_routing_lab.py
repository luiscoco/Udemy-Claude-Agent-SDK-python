"""Lesson 59 fixed task and routing acceptance checks."""

import copy

import httpx
import pytest
from fastapi import FastAPI

from agent_lab.api_routing import install_routing_routes
from agent_lab.routing_lab import (
    BY_ID,
    STRATEGIES,
    TASKS,
    RoutingInput,
    answer_key,
    check_suite,
    facts,
    grade_answer,
    needs_escalation,
    prepared,
    rule_tier,
)
from agent_lab.routing_native import assess_special, usage_snapshot


def test_fixed_keys_rules_and_confident_error() -> None:
    assert len(TASKS) == len(BY_ID) == 13
    assert [task.id for task in TASKS] == list(BY_ID)
    assert {t.id for t in TASKS if rule_tier(t.id) != t.tier} == {"vowels", "multiply", "power-mod"}
    assert answer_key("sort") == "1,10,9"
    assert answer_key("power-mod") == "049"
    assert answer_key("lineup") == "DACEB"
    assert answer_key("positions") == "Eli,Alex,Cal,Dee,Bea,Fay"
    assert grade_answer("power-mod", "001")["accepted"] is False
    assert needs_escalation("power-mod", {"answer": "001", "confidence": .99}) is False


def test_all_prepared_strategies_have_expected_teaching_outcomes() -> None:
    selected = RoutingInput(strategies=list(STRATEGIES))
    report = prepared(selected)
    assert len(report["rows"]) == 8 * 13
    assert report["sdkQueries"] == report["reportedSdkUsd"] == 0
    assert {key for key, value in report["metrics"].items() if value["accepted"] == 13} == set(STRATEGIES) - {"light", "cascade"}
    assert report["check"]["status"] == "needs-review"
    assert report["metrics"]["classifier"]["classifierCostUsd"] > 0
    assert report["metrics"]["classifier"]["classifierDurationMs"] > 0
    assert sum(row["escalated"] for row in report["rows"] if row["strategy"] == "review") == 13
    assert not next(row for row in report["rows"] if row["strategy"] == "cascade" and row["taskId"] == "power-mod")["escalated"]
    rules = prepared(RoutingInput())
    assert rules["check"]["status"] == "pass"


def test_incomplete_or_forged_answer_cannot_pass() -> None:
    selected = RoutingInput(taskIds=["invoice", "power-mod"])
    report = prepared(selected)
    assert report["check"]["status"] == "pass"
    for mutate in (lambda v: v["rows"].pop(),
                   lambda v: v["rows"][0]["output"].update(answer="wrong"),
                   lambda v: v["config"].update(runId="old"),
                   lambda v: v.update(interrupted=True)):
        value = copy.deepcopy(report)
        mutate(value)
        assert check_suite(value, selected)["status"] == "needs-review"


def test_special_assessor_requires_correlated_native_evidence() -> None:
    from agent_lab.routing_lab import prepared_task

    rows = []
    for variant in ("alias", "remapped-alias", "explicit-id"):
        row = prepared_task("invoice", "standard")
        call = row["history"][0]
        model = call["billing"]["models"][0]
        call["source"] = "native-sdk"
        call["rawTerminal"] = {"total_cost_usd": call["billing"]["cumulativeCostUsd"],
                               "model_usage": {model["rawModel"]: {
                                   "inputTokens": model["inputTokens"],
                                   "outputTokens": model["outputTokens"],
                                   "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                                   "costUSD": model["costUsd"],
                                   "canonicalModel": model["canonicalModel"]}}}
        call["billing"] = usage_snapshot(call["rawTerminal"])
        call["toolEvidence"] = {"inits": [{"sessionId": call["sessionId"]}]}
        row["variant"] = variant
        rows.append(row)
    report = {"mode": "live", "source": "native-sdk-special", "kind": "resolution",
              "status": "success", "errors": [], "rows": rows, "sdkQueries": 3,
              "reportedSdkUsd": sum(row["history"][0]["billing"]["cumulativeCostUsd"] for row in rows)}
    assert assess_special(report, 1)["passed"]
    for mutate in (lambda v: v["rows"].pop(),
                   lambda v: v["rows"][0]["output"].update(answer="wrong"),
                   lambda v: v["rows"][0]["history"][0]["rawTerminal"].update(total_cost_usd=9),
                   lambda v: v["rows"][1]["history"][0].update(queryId=v["rows"][0]["history"][0]["queryId"]),
                   lambda v: v["rows"][0]["history"][0].update(closed=False),
                   lambda v: v["rows"][0]["history"][0]["toolEvidence"]["inits"][0].update(sessionId="foreign"),
                   lambda v: v.update(mode="prepared")):
        value = copy.deepcopy(report)
        mutate(value)
        assert not assess_special(value, 1)["passed"]
    delegate = copy.deepcopy(report)
    delegate["kind"] = "delegate"
    delegate["rows"] = [delegate["rows"][0]]
    delegate["rows"][0]["taskId"] = "lineup"
    delegate["rows"][0]["output"]["answer"] = "DACEB"
    delegate["rows"][0]["history"][0]["output"]["answer"] = "DACEB"
    delegate["rows"][0]["grade"] = grade_answer("lineup", "DACEB")
    delegate["sdkQueries"] = 1
    delegate["reportedSdkUsd"] = delegate["rows"][0]["history"][0]["billing"]["cumulativeCostUsd"]
    delegate["rows"][0]["delegation"] = {"observed": True,
        "admissions": [{"callId": "x", "tool": "StructuredOutput", "admitted": True}],
        "calls": [{"callId": "x", "tool": "StructuredOutput"}],
        "results": [{"callId": "x", "isError": False}]}
    assert not assess_special(delegate, 1)["passed"]
    delegate["rows"][0]["delegation"]["admissions"][0]["tool"] = "Agent"
    delegate["rows"][0]["delegation"]["calls"][0]["tool"] = "Agent"
    assert assess_special(delegate, 1)["passed"]


@pytest.mark.parametrize("payload", [
    {"strategies": ["rules", "rules"]}, {"taskIds": ["invoice", "invoice"]},
    {"strategies": ["unknown"]}, {"taskIds": ["other"]},
    {"mode": "live", "strategies": ["rules", "light"]},
    {"mode": "live", "taskIds": [task.id for task in TASKS[:4]]},
    {"prompt": "arbitrary"},
])
def test_strict_request_rejects_unbounded_controls(payload: dict) -> None:
    with pytest.raises(ValueError):
        RoutingInput.model_validate(payload)


@pytest.mark.asyncio
async def test_api_facts_plan_code_and_prepared_run(tmp_path) -> None:
    class Settings:
        data_dir = tmp_path
        enable_live = False

    class Runner:
        settings = Settings()

    app = FastAPI()
    install_routing_routes(app, Runner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        facts_reply = await client.get("/api/c59/facts")
        assert facts_reply.status_code == 200
        assert len(facts_reply.json()["tasks"]) == 13
        assert (await client.get("/api/c59/plan?bad=1")).status_code == 400
        assert (await client.get("/api/c59/models")).json()["source"] == "configured-local"
        assert (await client.get("/api/c59/models?native=1")).status_code == 400
        assert (await client.get("/api/c59/models?native=1&consent=1")).status_code == 403
        code = (await client.get("/api/c59/code")).json()
        assert len(code) == 3 and all(row["start_line"] > 0 for row in code)
        run = await client.post("/api/c59/run", json={"taskIds": ["invoice"]})
        assert run.status_code == 200 and run.json()["check"]["status"] == "pass"
        assert (await client.post("/api/c59/run", json={"mode": "live", "taskIds": ["invoice"]})).status_code == 403
        assert (await client.post("/api/c59/run", json={"prompt": "injection"})).status_code == 400
        assert (await client.post("/api/c59/stop", json={"runId": run.json()["runId"]})).status_code == 404
        assert facts()["models"]["light"].startswith("claude-haiku")
