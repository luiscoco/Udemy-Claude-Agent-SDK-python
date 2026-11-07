"""Strict Lesson 48 security action routes."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.hardening_lab import ACTIONS, local_action, save_passing
from agent_lab.runtime import RunService


class HardeningAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed", "leaked"] = "normal"


def code() -> list[dict[str, Any]]:
    from agent_lab.config import ROOT

    sources = (("def child_environment(", "agent_lab/hardening_policy.py", 18,
                "Which values cross into the SDK child?"),
               ("def admission(", "agent_lab/hardening_policy.py", 22,
                "Which exact paths and commands are admitted?"),
               ("def rewrite_known_output(", "agent_lab/hardening_policy.py", 18,
                "Which known markers are removed before tool output returns?"))
    output = []
    for marker, path, length, question in sources:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        output.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return output


def _read_state(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise HTTPException(409, "Unsafe hardening summary file")
    if not path.exists():
        return None
    stat = path.lstat()
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
        raise HTTPException(409, "Unsafe hardening summary file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Invalid hardening summary file") from exc
    if not isinstance(value, dict) or value.get("lesson") != 48:
        raise HTTPException(409, "Invalid hardening summary identity")
    return value


def install_hardening_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "lesson-48"
    busy = asyncio.Lock()

    @app.get("/api/c48/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 48, "actions": list(ACTIONS),
                "scenarios": ["normal", "missing", "foreign", "failed", "leaked"],
                "criterion": "Guarded fixed probes have correlated denials, known-marker containment and unchanged outside files.",
                "limits": {"lane_usd": 0.10, "action_usd": 0.20},
                "local_source": "authored host effects", "live_source": "native SDK subprocess"}

    @app.get("/api/c48/state")
    async def state() -> dict[str, Any] | None:
        if busy.locked():
            raise HTTPException(409, "Lesson 48 action active")
        return _read_state(storage / "latest.json")

    @app.get("/api/c48/code")
    @app.get("/api/c48/source")
    async def source() -> list[dict[str, Any]]:
        return code()

    async def execute(action: str, raw: Any) -> dict[str, Any]:
        try:
            body = HardeningAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and (not body.consent or not runner.settings.enable_live or
                                    body.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded paid hardening action with live access enabled.")
        if busy.locked():
            raise HTTPException(409, "Lesson 48 action active")
        async with busy:
            try:
                async with asyncio.timeout(350):
                    if body.mode == "live":
                        from agent_lab.hardening_native import live_action

                        report = await live_action(action)
                    else:
                        report = await local_action(action, scenario=body.scenario)
                save_passing(report, storage)
                return report
            except TimeoutError as exc:
                raise HTTPException(409, "Hardening action deadline exceeded") from exc
            except (PermissionError, ValueError) as exc:
                raise HTTPException(409, str(exc)) from exc

    for action in ACTIONS:
        def route(selected: str) -> Any:
            async def endpoint(request: Request) -> dict[str, Any]:
                try:
                    raw = await request.json()
                except ValueError as exc:
                    raise HTTPException(400, "Invalid JSON body") from exc
                return await execute(selected, raw)
            endpoint.__name__ = "hardening_" + selected
            return endpoint
        app.add_api_route("/api/c48/" + action, route(action), methods=["POST"])
