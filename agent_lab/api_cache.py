"""Strict Lesson 46 cache-action routes with fresh live consent."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_lab.cache_lab import (
    ACTIONS,
    POLICIES,
    PREFIXES,
    TTLS,
    live_action,
    local_action,
    save_passing,
)
from agent_lab.cache_wire import RATES_2026_10_19
from agent_lab.runtime import RunService


class CacheAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local", "live"] = "local"
    consent: bool = False
    scenario: Literal["normal", "missing", "foreign", "failed"] = "normal"
    ttl: Literal["5m", "1h", "off"] = "5m"
    prefix: Literal["stable", "changed", "tool", "dynamic", "short"] = "stable"
    policy: Literal["cap", "allow"] = "cap"


def code() -> list[dict[str, Any]]:
    from agent_lab.config import ROOT

    sources = (
        ("agent_lab/cache_wire.py", "def normalized_usage(", "Which counters must exist?"),
        ("agent_lab/cache_wire.py", "def breakpoints(", "Where can a cache breakpoint appear?"),
        ("agent_lab/cache_lab.py", "def evaluate_native(", "Which native and wire identities are joined?"),
    )
    output: list[dict[str, Any]] = []
    for path, marker, question in sources:
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        start = next(index for index, line in enumerate(lines, 1) if line.startswith(marker))
        end = min(len(lines), start + 22)
        output.append({"file": path, "start_line": start, "end_line": end,
                       "code": "\n".join(lines[start - 1:end]), "question": question})
    return output


def _read_state(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise HTTPException(409, "Unsafe cache summary file")
    if not path.exists():
        return None
    stat = path.lstat()
    if path.is_symlink() or not path.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
        raise HTTPException(409, "Unsafe cache summary file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Invalid cache summary file") from exc
    if not isinstance(value, dict) or value.get("lesson") != 46:
        raise HTTPException(409, "Invalid cache summary identity")
    return value


def install_cache_routes(app: FastAPI, runner: RunService) -> None:
    storage = runner.settings.data_dir / "lesson-46"
    busy = asyncio.Lock()

    @app.get("/api/c46/facts")
    async def facts() -> dict[str, Any]:
        return {"lesson": 46, "actions": list(ACTIONS), "ttl": list(TTLS),
                "prefix": list(PREFIXES), "policy": list(POLICIES),
                "criterion": "Two successful turns in one lane expose finite cache and usage counters; no guaranteed cache saving.",
                "rates_as_of": "2026-10-19", "models": list(RATES_2026_10_19),
                "local_source": "authored host HTTP fixture", "live_source": "native SDK subprocess through owned observer"}

    @app.get("/api/c46/state")
    async def state() -> dict[str, Any] | None:
        if busy.locked():
            raise HTTPException(409, "Lesson 46 action active")
        return _read_state(storage / "latest.json")

    @app.get("/api/c46/code")
    @app.get("/api/c46/source")
    async def source() -> list[dict[str, Any]]:
        return code()

    async def execute(action: str, raw: Any) -> dict[str, Any]:
        try:
            body = CacheAction.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, exc.errors(include_context=False, include_input=False)) from exc
        if body.mode == "live" and (not body.consent or not runner.settings.enable_live or
                                    body.scenario != "normal"):
            raise HTTPException(403, "Confirm this bounded paid cache action with live access enabled.")
        if busy.locked():
            raise HTTPException(409, "Lesson 46 action active")
        async with busy:
            try:
                async with asyncio.timeout(180):
                    report = (await live_action(action, ttl=body.ttl, prefix=body.prefix,
                                                policy=body.policy) if body.mode == "live" else
                              await local_action(action, ttl=body.ttl, prefix=body.prefix,
                                                 policy=body.policy, scenario=body.scenario))
                save_passing(report, storage)
                return report
            except TimeoutError as exc:
                raise HTTPException(409, "Cache action deadline exceeded") from exc
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
            endpoint.__name__ = "cache_" + selected.replace("-", "_")
            return endpoint
        app.add_api_route("/api/c46/" + action, route(action), methods=["POST"])
