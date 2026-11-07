"""Strict Lesson 49 action, inspection and bounded saved-state routes."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.headless_lab import ACTIONS, LIMIT_CODES, local_action, save_passing
from agent_lab.runtime import RunService


class HeadlessAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"


def code() -> list[dict[str, Any]]:
    from agent_lab.config import ROOT

    sources = (("async def run_process(", 33, "How does the child receive EOF and bounded separate pipes?"),
               ("def mapped_exit(", 27, "Which host policy code follows an actual process outcome?"),
               ("async def worker_action(", 29, "Which HTTP and worker receipts prove one local job and drain?"))
    lines = (ROOT / "agent_lab/headless_lab.py").read_text(encoding="utf-8").splitlines()
    output = []
    for marker, length, question in sources:
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + length - 1)
        output.append({"file": "agent_lab/headless_lab.py", "start_line": start,
                       "end_line": end, "code": "\n".join(lines[start - 1:end]),
                       "question": question})
    return output


def files() -> list[dict[str, str]]:
    from agent_lab.config import ROOT

    selected = ("headless_clean.py", "headless_buggy.py", "headless_child.py",
                "headless_worker.py", "Dockerfile.headless.example",
                "dockerignore.headless.example", "offline-ci.headless.example.yml")
    return [{"name": name, "text": (ROOT / "agent_lab/content" / name).read_text(encoding="utf-8")}
            for name in selected]


def _read_state(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise HTTPException(409, "Unsafe headless summary file")
    if not path.exists():
        return None
    stat = path.lstat()
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
        raise HTTPException(409, "Unsafe headless summary file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Invalid headless summary file") from exc
    if not isinstance(value, dict) or value.get("lesson") != 49:
        raise HTTPException(409, "Invalid headless summary identity")
    return value


def install_headless_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "lesson-49"
    busy = asyncio.Lock()

    @app.get("/api/c49/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 49, "actions": list(ACTIONS),
                "local_only": ["limits", "deploy"], "limit_codes": list(LIMIT_CODES),
                "criterion": "CLI and SDK headless paths both exit successfully.",
                "native_ceiling_usd": 0.10,
                "local_source": "owned Python subprocesses",
                "live_source": "native CLI and SDK"}

    @app.get("/api/c49/files")
    async def inspect_files() -> list[dict[str, str]]:
        return files()

    @app.get("/api/c49/code")
    @app.get("/api/c49/source")
    async def source() -> list[dict[str, Any]]:
        return code()

    @app.get("/api/c49/state")
    async def state() -> dict[str, Any] | None:
        if busy.locked():
            raise HTTPException(409, "Lesson 49 action active")
        return _read_state(storage / "latest.json")

    async def execute(action: str, raw: Any) -> dict[str, Any]:
        try:
            body = HeadlessAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and (action not in {"headless", "ci"} or not body.consent or
                                    not runner.settings.enable_live or body.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded paid headless action with live access enabled.")
        if busy.locked():
            raise HTTPException(409, "Lesson 49 action active")
        async with busy:
            try:
                async with asyncio.timeout(180):
                    if body.mode == "live":
                        from agent_lab.headless_native import live_action

                        report = await live_action(action)
                    else:
                        report = await local_action(action, body.scenario)
                save_passing(report, storage)
                return report
            except TimeoutError as exc:
                raise HTTPException(409, "Headless action deadline exceeded") from exc
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
            endpoint.__name__ = "headless_" + selected
            return endpoint
        app.add_api_route("/api/c49/" + action, route(action), methods=["POST"])
