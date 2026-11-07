"""Strict Lesson 47 orchestration action routes."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.orchestra_lab import ACTIONS, ROWS, local_action, save_passing
from agent_lab.runtime import RunService


class OrchestraAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    limit: Literal[1, 2] = 2
    scenario: Literal["normal", "missing", "foreign", "failed", "cancel-worker",
                      "missing-file", "wrong-report"] = "normal"


def code() -> list[dict[str, Any]]:
    from agent_lab.config import ROOT

    sources = (("class FairLimiter:", 22, "How is a queued worker given a reserved slot?"),
               ("def check_report(", 12, "Which report line matches fixture truth?"),
               ("def analyst_gate(", 8, "Why does the host still check a second stop?"))
    lines = (ROOT / "agent_lab/orchestra_lab.py").read_text(encoding="utf-8").splitlines()
    output = []
    for marker, length, question in sources:
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length)
        output.append({"file": "agent_lab/orchestra_lab.py", "start_line": start,
                       "end_line": end, "code": "\n".join(lines[start - 1:end]), "question": question})
    return output


def _read_state(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise HTTPException(409, "Unsafe orchestration summary file")
    if not path.exists():
        return None
    stat = path.lstat()
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
        raise HTTPException(409, "Unsafe orchestration summary file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Invalid orchestration summary file") from exc
    if not isinstance(value, dict) or value.get("lesson") != 47:
        raise HTTPException(409, "Invalid orchestration summary identity")
    return value


def install_orchestra_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "lesson-47"
    busy = asyncio.Lock()

    @app.get("/api/c47/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 47, "actions": list(ACTIONS), "limits": [1, 2],
                "sales": {region: list(rows) for region, rows in ROWS.items()},
                "criterion": "A completed worker matches its start and an independent host verdict.",
                "local_source": "authored host fixture over owned CSV files",
                "live_source": "native SDK with host checks"}

    @app.get("/api/c47/state")
    async def state() -> dict[str, Any] | None:
        if busy.locked():
            raise HTTPException(409, "Lesson 47 action active")
        return _read_state(storage / "latest.json")

    @app.get("/api/c47/code")
    @app.get("/api/c47/source")
    async def source() -> list[dict[str, Any]]:
        return code()

    async def execute(action: str, raw: Any) -> dict[str, Any]:
        try:
            body = OrchestraAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and (not body.consent or not runner.settings.enable_live or
                                    body.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded paid orchestration action with live access enabled.")
        if busy.locked():
            raise HTTPException(409, "Lesson 47 action active")
        async with busy:
            try:
                async with asyncio.timeout(180):
                    if body.mode == "live":
                        from agent_lab.orchestra_native import live_action

                        report = await live_action(action, limit=body.limit)
                    else:
                        report = await local_action(action, limit=body.limit, scenario=body.scenario)
                save_passing(report, storage)
                return report
            except TimeoutError as exc:
                raise HTTPException(409, "Orchestration action deadline exceeded") from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    for action in ACTIONS:
        def route(selected: str) -> Any:
            async def endpoint(request: Request) -> dict[str, Any]:
                try:
                    raw = await request.json()
                except ValueError as exc:
                    raise HTTPException(400, "Invalid JSON body") from exc
                return await execute(selected, raw)
            endpoint.__name__ = "orchestra_" + selected
            return endpoint
        app.add_api_route("/api/c47/" + action, route(action), methods=["POST"])
