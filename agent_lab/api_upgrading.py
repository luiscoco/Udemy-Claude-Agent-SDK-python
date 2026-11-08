"""Strict offline Lesson 55 inspection, assessment and simulated transitions."""

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ValidationError

from agent_lab.config import ROOT
from agent_lab.upgrading_lab import (
    CRITERION,
    SCENARIOS,
    RunInput,
    TransitionInput,
    criterion,
    fixture,
    run_upgrade,
    runtime_inventory,
    transition,
)


async def _body(request: Request, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Only fixed offline workshop inputs are accepted") from exc


def code_excerpts() -> list[dict[str, Any]]:
    anchors = (("agent_lab/upgrading_lab.py", "def runtime_inventory(", 29,
                "Which installed Python SDK facts are observed without running a model?"),
               ("agent_lab/upgrading_lab.py", "def adapt_stream(", 34,
                "Which required stream identities must match despite an additive event?"),
               ("agent_lab/upgrading_lab.py", "def transition(", 16,
                "Why can the simulation promote only after an eligible canary?"))
    result = []
    for path, marker, length, question in anchors:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        result.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return result


def install_upgrading_routes(app: FastAPI) -> None:
    @app.get("/api/c55/facts")
    async def facts() -> dict[str, Any]:
        data = fixture()
        return {"lesson": 55, "simulated": True, "mode": "offline", "modelCalls": 0,
                "inventory": runtime_inventory(), "scenarios": list(SCENARIOS),
                "baseline": data["baseline"],
                "limits": {"correctnessDrop": 0.02, "costGrowth": 0.20, "latencyGrowth": 0.25},
                "criterion": CRITERION, "command": "python scripts/upgrading_check.py",
                "realProcedure": ["Retain known-good artifact, manifest, lock, configuration, eval baseline and data snapshots.",
                                  "Review exact candidate release notes and runtime changes in an isolated checkout.",
                                  "Run clean locked install, typecheck, offline suite, build and real candidate SDK behavior tests.",
                                  "Repeat comparable real evaluations and use measured canary stop thresholds.",
                                  "Promote after review; roll back retained artifacts and test snapshot recovery."]}

    @app.get("/api/c55/code")
    async def code() -> list[dict[str, Any]]:
        return code_excerpts()

    @app.post("/api/c55/run")
    async def run(request: Request) -> dict[str, Any]:
        selected = await _body(request, RunInput)
        assert isinstance(selected, RunInput)
        report = run_upgrade(selected)
        return {"report": report, "check": "passed" if criterion(selected, report) else "needs-review",
                "criterion": CRITERION}

    @app.post("/api/c55/transition")
    async def move(request: Request) -> dict[str, Any]:
        selected = await _body(request, TransitionInput)
        assert isinstance(selected, TransitionInput)
        try:
            return transition(selected)
        except ValueError as exc:
            raise HTTPException(409, {"reason": str(exc),
                                      "assessment": run_upgrade(RunInput(scenario=selected.scenario))}) from exc
