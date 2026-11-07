"""Strict Lesson 52 evaluation routes with separate free and paid admission."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from agent_lab.config import ROOT
from agent_lab.evals_core import (
    BUSINESS,
    CRITERIA,
    EmptyInput,
    EvalInput,
    PairInput,
    PromoteInput,
    calibrate,
    cases,
    compare,
    fingerprint,
    synthetic_criterion,
    synthetic_report,
)
from agent_lab.evals_live import admission, native_eval
from agent_lab.evals_store import EvalStore, IneligibleRun, MissingRun
from agent_lab.runtime import RunService


def eval_code() -> list[dict[str, Any]]:
    markers = (
        ("agent_lab/evals_core.py", "def compare(", 42, "Which measured drops fail and which remain suspect?"),
        ("agent_lab/evals_core.py", "def calibrate(", 27, "Why do two lenient semantic misses remain visible?"),
        ("agent_lab/evals_store.py", "    def promote(", 30, "Which retained report can become a scoped baseline?"),
    )
    result = []
    for path, marker, length, question in markers:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        result.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return result


async def _body(request: Request, model: type[Any]) -> Any:
    try:
        return model.model_validate_json(json.dumps(await request.json()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "Invalid fixed evaluation body") from exc


class StopInput(EmptyInput):
    runId: uuid.UUID


def install_evals_routes(app: FastAPI, runner: RunService) -> None:
    store = EvalStore(runner.settings.data_dir / "lesson-52")
    active: dict[str, Any] = {}

    def reserve(action: str) -> tuple[uuid.UUID, asyncio.Event]:
        if active:
            raise HTTPException(409, "An evaluation mutation is already active")
        identifier, abort = uuid.uuid4(), asyncio.Event()
        active.update({"run": identifier, "action": action, "abort": abort,
                       "task": asyncio.current_task()})
        return identifier, abort

    def release(identifier: uuid.UUID) -> None:
        if active.get("run") == identifier:
            active.clear()

    @app.get("/api/c52/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 52, "cases": [{"caseId": row["caseId"], "prompt": row["prompt"]} for row in cases()],
                "criteria": list(CRITERIA), "business": list(BUSINESS),
                "variants": ["baseline", "cold-tone", "false-refund", "fix-findings"],
                "syntheticFingerprint": fingerprint("heuristic"),
                "freeDemo": True, "liveEnabled": runner.settings.enable_live,
                "scope": "Three fixed Ada support cases; synthetic results are authored fixture data, not measured model quality"}

    @app.get("/api/c52/code")
    async def code() -> list[dict[str, Any]]:
        return eval_code()

    @app.get("/api/c52/baseline")
    async def baseline(request: Request) -> dict[str, Any]:
        if set(request.query_params) - {"mode", "judge"}:
            raise HTTPException(400, "Unknown baseline query")
        mode = request.query_params.get("mode", "synthetic")
        judge = request.query_params.get("judge", "heuristic")
        try:
            report = store.baseline(mode, judge)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"mode": mode, "judge": judge, "report": report,
                "reviewHash": store.review(report)["reviewHash"] if report else None}

    @app.get("/api/c52/active")
    async def active_run() -> dict[str, Any]:
        if not active:
            raise HTTPException(404, "No active evaluation")
        return {"runId": str(active["run"]), "action": active["action"]}

    @app.post("/api/c52/demo")
    async def demo(request: Request) -> dict[str, Any]:
        selected: EvalInput = await _body(request, EvalInput)
        if selected.mode != "synthetic" or selected.judge != "heuristic":
            raise HTTPException(400, "The free demo uses synthetic heuristic evidence only")
        identifier, _abort = reserve("demo")
        try:
            baseline_report = synthetic_report("baseline", selected.trials)
            candidate = synthetic_report(selected.variant, selected.trials)
            comparison = compare(baseline_report, candidate)
            return {"runId": str(identifier), "baseline": baseline_report,
                    "candidate": candidate, "comparison": comparison,
                    "modelCalls": 0, "actualBilledUsd": 0,
                    "experiment_passed": synthetic_criterion(baseline_report, candidate, comparison)}
        finally:
            release(identifier)

    @app.post("/api/c52/calibrate")
    async def calibration(request: Request) -> dict[str, Any]:
        await _body(request, EmptyInput)
        identifier, _abort = reserve("calibrate")
        try:
            return {"runId": str(identifier), **calibrate(), "modelCalls": 0, "actualBilledUsd": 0}
        finally:
            release(identifier)

    @app.post("/api/c52/run")
    async def run(request: Request) -> dict[str, Any]:
        selected: EvalInput = await _body(request, EvalInput)
        if selected.mode == "synthetic" and selected.judge != "heuristic":
            raise HTTPException(400, "Synthetic actions use the disclosed heuristic only")
        if selected.mode == "live":
            try:
                admission(runner.settings, trials=selected.trials, judge=selected.judge,
                          budget=selected.budget, consent=selected.consent)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
        identifier, abort = reserve("run")
        try:
            async with asyncio.timeout(180):
                if selected.mode == "synthetic":
                    candidate = synthetic_report(selected.variant, selected.trials)
                else:
                    candidate = await native_eval(store.root, runner.settings,
                                                  variant=selected.variant, trials=selected.trials,
                                                  judge=selected.judge, budget=selected.budget,
                                                  consent=selected.consent, abort=abort)
                store.save(candidate)
                base = store.baseline(selected.mode, selected.judge)
                comparison = compare(base, candidate)
                return {"runId": str(identifier), "baseline": base, "candidate": candidate,
                        "comparison": comparison, "review": store.review(candidate),
                        "experiment_passed": (base is not None and
                                              synthetic_criterion(base, candidate, comparison)
                                              if selected.mode == "synthetic" else False)}
        except TimeoutError as exc:
            raise HTTPException(409, "Evaluation deadline exceeded; inspect retained partial work") from exc
        finally:
            release(identifier)

    @app.post("/api/c52/promote")
    async def promote(request: Request) -> dict[str, Any]:
        selected: PromoteInput = await _body(request, PromoteInput)
        identifier, _abort = reserve("promote")
        try:
            try:
                return {"runId": str(identifier), **store.promote(selected.runId,
                                                                 selected.expectedHash, selected.note)}
            except MissingRun as exc:
                raise HTTPException(404, str(exc)) from exc
            except IneligibleRun as exc:
                raise HTTPException(409, str(exc)) from exc
        finally:
            release(identifier)

    @app.post("/api/c52/pairwise")
    async def pairwise(request: Request) -> dict[str, Any]:
        selected: PairInput = await _body(request, PairInput)
        identifier, _abort = reserve("pairwise")
        try:
            try:
                return {"runId": str(identifier), **store.pairwise(selected.left, selected.right,
                                                                  selected.caseId)}
            except MissingRun as exc:
                raise HTTPException(404, str(exc)) from exc
            except IneligibleRun as exc:
                raise HTTPException(409, str(exc)) from exc
        finally:
            release(identifier)

    @app.post("/api/c52/stop")
    async def stop(request: Request) -> dict[str, Any]:
        selected: StopInput = await _body(request, StopInput)
        if active.get("run") != selected.runId:
            raise HTTPException(409, "Active evaluation does not match")
        active["abort"].set()
        if active["action"] == "run" and active.get("task") is not None:
            active["task"].cancel()
        return {"stopping": True, "runId": str(selected.runId)}
