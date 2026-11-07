"""Lesson 49 owned headless processes, explicit CI codes and local worker evidence."""

import asyncio
import json
import math
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from agent_lab.config import ROOT
from agent_lab.hardening_policy import OS_VARIABLES, digest

ACTIONS = ("headless", "ci", "limits", "deploy")
SCENARIOS = ("normal", "missing", "foreign", "failed")
CLEAN = (ROOT / "agent_lab/content/headless_clean.py").read_bytes()
BUGGY = (ROOT / "agent_lab/content/headless_buggy.py").read_bytes()
EXPECTED = {"clean": ("PASS", []), "buggy": ("FAIL", ["EVAL", "PERCENT"])}
LIMIT_CASES = ("success", "missing-result", "unsuccessful", "denied", "timeout", "missing-executable")
LIMIT_CODES = (0, 11, 11, 12, 124, 127)


def environment(home: Path) -> dict[str, str]:
    values = {key: value for key, value in os.environ.items() if key.upper() in OS_VARIABLES}
    values.update({"HOME": str(home), "USERPROFILE": str(home),
                   "APPDATA": str(home / "appdata"), "CLAUDE_CONFIG_DIR": str(home),
                   "AWS_EC2_METADATA_DISABLED": "true"})
    return values


def fixture(folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True)
    home = folder / "config"
    home.mkdir()
    sources = {"clean": folder / "clean.py", "buggy": folder / "buggy.py"}
    sources["clean"].write_bytes(CLEAN)
    sources["buggy"].write_bytes(BUGGY)
    child = folder / "child.py"
    child.write_bytes((ROOT / "agent_lab/content/headless_child.py").read_bytes())
    worker = folder / "worker.py"
    worker.write_bytes((ROOT / "agent_lab/content/headless_worker.py").read_bytes())
    return {"folder": folder, "home": home, "sources": sources,
            "hashes": {key: digest(path.read_bytes()) for key, path in sources.items()},
            "child": child, "worker": worker}


async def run_process(executable: Path, argv: list[str], *, cwd: Path,
                      env: dict[str, str], deadline_seconds: float = 4,
                      input_data: bytes | None = None) -> dict[str, Any]:
    """Spawn literal argv with EOF stdin, separately bounded pipes and owned cleanup."""
    try:
        process = await asyncio.create_subprocess_exec(
            str(executable), *argv, cwd=str(cwd), env=env,
            stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return {"actual_exit": None, "stdout": "", "stderr": "", "missing": True,
                "timed_out": False, "cancelled": False, "closed": False,
                "stdin_closed": True, "shell": False, "overflow": False}

    buffers: dict[str, list[bytes]] = {"stdout": [], "stderr": []}

    async def collect(stream: asyncio.StreamReader, name: str) -> None:
        length = 0
        while part := await stream.read(4096):
            length += len(part)
            if length > 65536:
                raise ValueError("Pipe exceeded 64 KB")
            buffers[name].append(part)

    timed_out = cancelled = overflow = False
    assert process.stdout is not None and process.stderr is not None
    stdout_task = asyncio.create_task(collect(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(collect(process.stderr, "stderr"))
    try:
        if input_data is not None:
            assert process.stdin is not None
            process.stdin.write(input_data)
            await process.stdin.drain()
            process.stdin.close()
        async with asyncio.timeout(deadline_seconds):
            await asyncio.gather(stdout_task, stderr_task, process.wait())
    except TimeoutError:
        timed_out = True
    except ValueError:
        overflow = True
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        if process.returncode is None:
            process.kill()
        await process.wait()
        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
    return {"actual_exit": process.returncode,
            "stdout": b"".join(buffers["stdout"]).decode("utf-8", "replace"),
            "stderr": b"".join(buffers["stderr"]).decode("utf-8", "replace"),
            "missing": False, "timed_out": timed_out, "cancelled": cancelled,
            "closed": process.returncode is not None,
            "stdin_closed": True, "shell": False, "overflow": overflow}


def parse_terminal(stdout: str) -> dict[str, Any] | None:
    values = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("type") == "result":
            values.append(item)
    return values[0] if len(values) == 1 else None


def mapped_exit(outcome: dict[str, Any], terminal: dict[str, Any] | None) -> int:
    if outcome.get("cancelled"):
        return 130
    if outcome.get("timed_out"):
        return 124
    if outcome.get("missing"):
        return 127
    if outcome.get("actual_exit") != 0 or outcome.get("overflow"):
        return 10
    if (not isinstance(terminal, dict) or terminal.get("is_error") is not False or
            not isinstance(terminal.get("cost_usd"), (int, float)) or
            not math.isfinite(terminal["cost_usd"]) or terminal["cost_usd"] < 0):
        return 11
    if not isinstance(terminal.get("permission_denials"), list) or terminal["permission_denials"]:
        return 12
    return 0


def report_valid(value: Any, run_id: str, fixture_name: str) -> bool:
    expected_verdict, expected_issues = EXPECTED[fixture_name]
    return (isinstance(value, dict) and set(value) == {"run", "verdict", "issues"} and
            value.get("run") == run_id and value.get("verdict") == expected_verdict and
            value.get("issues") == expected_issues)


async def local_query(operation: str, name: str, source: str, case: str,
                      root: Path) -> dict[str, Any]:
    owned = fixture(root / name)
    run_id = str(uuid.uuid4())
    verdict, issues = EXPECTED[source]
    executable = (owned["folder"] / "absent-python.exe") if case == "missing-executable" else Path(sys.executable)
    outcome = await run_process(executable,
                                [str(owned["child"]), case, run_id, verdict,
                                 "none" if not issues else ",".join(issues)],
                                cwd=owned["folder"], env=environment(owned["home"]),
                                deadline_seconds=0.4 if case == "timeout" else 4)
    terminal = parse_terminal(outcome["stdout"])
    code = mapped_exit(outcome, terminal)
    after = digest(owned["sources"][source].read_bytes())
    result = terminal.get("structured_output") if isinstance(terminal, dict) else None
    return {"id": run_id, "operation": operation, "name": name, "fixture": source,
            "source": "authored-process", "native": False,
            "fixture_sha256": owned["hashes"][source], "after_sha256": after,
            "process": outcome, "terminal": terminal, "policy_exit": code,
            "report_valid": report_valid(result, run_id, source),
            "ci_exit": 20 if code == 0 and source == "buggy" else code,
            "config_owned": True}


async def _read_event(process: asyncio.subprocess.Process, deadline_seconds: float = 3) -> dict[str, Any]:
    assert process.stdout is not None
    line = await asyncio.wait_for(process.stdout.readline(), deadline_seconds)
    if len(line) > 4096:
        raise ValueError("Worker IPC line exceeded limit")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("Worker IPC record is not an object")
    return value


async def _tcp_closed(port: int) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 0.5)
    except (OSError, TimeoutError):
        return True
    writer.close()
    await writer.wait_closed()
    return False


async def worker_action(operation: str, root: Path, *, release: bool = True) -> dict[str, Any]:
    owned = fixture(root / ("deploy" if release else "deadline"))
    run_id, control = str(uuid.uuid4()), secrets.token_urlsafe(24)
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(owned["worker"]), run_id, control, "1000", "2000",
        cwd=str(owned["folder"]), env=environment(owned["home"]),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    events: list[dict[str, Any]] = []
    port = 0
    task: asyncio.Task[httpx.Response] | None = None
    try:
        listening = await _read_event(process)
        events.append(listening)
        if listening.get("kind") != "listening" or listening.get("run") != run_id:
            raise ValueError("Worker listening identity missing")
        port = listening["port"]
        base = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            health = await client.get(base + "/health")
            ready = await client.get(base + "/ready")
            job = "owned-job"
            task = asyncio.create_task(client.post(base + "/job", json={"run": run_id, "job": job}))
            start = await _read_event(process)
            events.append(start)
            busy = await client.post(base + "/job", json={"run": run_id, "job": "second-job"})
            drain = await client.post(base + "/control/drain",
                                      json={"run": run_id, "control": control})
            draining = await _read_event(process)
            events.append(draining)
            not_ready = await client.get(base + "/ready")
            released = None
            if release:
                released = await client.post(base + "/control/release",
                                             json={"run": run_id, "control": control})
            job_response = await task
            end = await _read_event(process)
            events.append(end)
        closed_event = await _read_event(process)
        events.append(closed_event)
        await asyncio.wait_for(process.wait(), 3)
        closed_tcp = await _tcp_closed(port)
        result = {"operation": operation, "source": "owned-local-worker", "run": run_id,
                  "events": events, "health": health.status_code, "ready": ready.status_code,
                  "busy": busy.status_code, "drain": drain.status_code,
                  "not_ready": not_ready.status_code,
                  "release": released.status_code if released else None,
                  "job_status": job_response.status_code,
                  "job_response": job_response.json(), "exit": process.returncode,
                  "closed_tcp": closed_tcp, "stdin_closed": True,
                  "shell": False, "slot": listening.get("slot"),
                  "job_ms": listening.get("job_ms"), "drain_ms": listening.get("drain_ms")}
        return result
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if process.returncode is None:
            process.kill()
            await process.wait()


def evaluate(report: dict[str, Any]) -> bool:
    action = report.get("action")
    if (action not in ACTIONS or report.get("status") != "completed" or
            report.get("mode") not in {"local", "live"} or report.get("scenario") != "normal"):
        return False
    if action == "deploy":
        worker = report.get("worker", {})
        events = worker.get("events", [])
        return (worker.get("source") == "owned-local-worker" and
                [row.get("kind") for row in events] ==
                ["listening", "job-start", "draining", "job-end", "closed"] and
                all(row.get("run") == worker.get("run") for row in events) and
                worker.get("health") == 200 and worker.get("ready") == 200 and
                worker.get("busy") == 429 and worker.get("drain") == 200 and
                worker.get("not_ready") == 503 and worker.get("release") == 200 and
                worker.get("job_status") == 200 and worker.get("exit") == 0 and
                worker.get("closed_tcp") is True and worker.get("slot") == 1 and
                worker.get("job_ms") == 1000 and worker.get("drain_ms") == 2000 and
                worker.get("job_response") == {"run": worker.get("run"),
                                               "job": "owned-job", "status": 200})
    outcomes = report.get("outcomes", [])
    expected_names = {"headless": ("cli", "sdk"), "ci": ("clean", "buggy"),
                      "limits": LIMIT_CASES}[action]
    if ([row.get("name") for row in outcomes] != list(expected_names) or
            len({row.get("id") for row in outcomes}) != len(expected_names)):
        return False
    for row in outcomes:
        if (row.get("operation") != report.get("operation") or
                row.get("fixture_sha256") != row.get("after_sha256") or
                row.get("config_owned") is not True or
                row.get("source") != ("authored-process" if report["mode"] == "local"
                                      else "native-cli" if row["name"] == "cli" else "native-sdk")):
            return False
        process = row.get("process", {})
        if process.get("stdin_closed") is not True or process.get("shell") is not False:
            return False
    if action in {"headless", "ci"}:
        if any(row.get("policy_exit") != 0 or row.get("report_valid") is not True or
               row.get("process", {}).get("closed") is not True for row in outcomes):
            return False
        if action == "ci" and [row.get("ci_exit") for row in outcomes] != [0, 20]:
            return False
        return True
    return ([row.get("policy_exit") for row in outcomes] == list(LIMIT_CODES) and
            outcomes[-2]["process"].get("timed_out") is True and
            outcomes[-1]["process"].get("missing") is True and
            all(row["process"].get("closed") for row in outcomes[:-1]))


async def local_action(action: str, scenario: str = "normal") -> dict[str, Any]:
    if action not in ACTIONS or scenario not in SCENARIOS:
        raise ValueError("Unknown fixed headless option")
    operation = str(uuid.uuid4())
    root = ROOT / ".lab-data/headless-local" / operation
    root.mkdir(parents=True)
    report: dict[str, Any] = {"lesson": 49, "operation": operation, "action": action,
        "mode": "local", "source_label": "owned Python subprocesses", "native": False,
        "scenario": scenario, "status": "completed", "created_at": datetime.now(UTC).isoformat(),
        "check_scope": "Observed child close codes, machine reports and owned fixture effects."}
    if action == "deploy":
        report["worker"] = await worker_action(operation, root)
    else:
        specs = (("cli", "clean", "success"), ("sdk", "clean", "success")) if action == "headless" else (
            ("clean", "clean", "success"), ("buggy", "buggy", "success")) if action == "ci" else tuple(
                (case, "clean", case) for case in LIMIT_CASES)
        report["outcomes"] = [await local_query(operation, name, source, case, root)
                              for name, source, case in specs]
    if scenario == "missing":
        if action == "deploy":
            report["worker"]["events"].pop()
        else:
            report["outcomes"].pop()
    elif scenario == "foreign":
        if action == "deploy":
            report["worker"]["events"][1]["run"] = "foreign-run"
        else:
            report["outcomes"][0]["operation"] = "foreign-run"
    elif scenario == "failed":
        report["status"] = "failed"
    report["experiment_passed"] = evaluate(report)
    encoded = json.dumps(report, indent=2).encode()
    if len(encoded) > 500_000:
        raise ValueError("Headless evidence exceeds 500 KB")
    (root / "report.json").write_bytes(encoded)
    return report


def save_passing(report: dict[str, Any], storage: Path) -> None:
    if not report.get("experiment_passed"):
        return
    summary = {key: report[key] for key in ("lesson", "operation", "action", "mode")}
    data = json.dumps(summary, separators=(",", ":")).encode()
    if len(data) > 4096:
        raise ValueError("Headless summary exceeds limit")
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / "latest.json"
    if target.is_symlink():
        raise ValueError("Unsafe saved headless summary")
    if target.exists():
        stat = target.lstat()
        if not target.is_file() or stat.st_nlink != 1 or stat.st_size > 4096:
            raise ValueError("Unsafe saved headless summary")
    temporary = storage / ("latest-" + uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)


async def execute_lesson(root: Path, request: Any, settings: Any, emit: Any) -> dict[str, Any]:
    from agent_lab.models import Event, lesson_request

    request = lesson_request(49, request)
    choices = request.lesson_options
    if request.mode == "live":
        if not settings.enable_live:
            raise PermissionError("Enable bounded paid calls with LAB_ENABLE_LIVE=true")
        from agent_lab.headless_native import live_action

        report = await live_action(choices["action"])
        costs = [row["terminal"]["cost_usd"] for row in report.get("outcomes", [])
                 if isinstance(row.get("terminal"), dict) and
                 isinstance(row["terminal"].get("cost_usd"), (int, float))]
        if costs:
            await emit(Event(kind="result", data={"lesson_id": 49,
                                                   "total_cost_usd": sum(costs)}))
    else:
        scenario = {"success": "normal", "missing-evidence": "missing",
                    "wrong-identity": "foreign"}.get(request.scenario, request.scenario)
        report = await local_action(choices["action"], scenario)
    save_passing(report, root / "owned-headless-summary")
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 49, "result": proof}))
    return proof


async def local(root: Path, request: Any) -> dict[str, Any]:
    from agent_lab.config import Settings
    from agent_lab.models import Event

    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}),
                                Settings(), ignore)
