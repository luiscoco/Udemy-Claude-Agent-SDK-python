"""Owned, real-Git two-worker integration workshop for Lesson 57."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.config import ROOT

FIXTURE = ROOT / "fixtures/worktrees/workshop.json"
CRITERION = "Independent worktrees carry commits, integrate and clean up with successful host tests."
SHA = re.compile(r"^[0-9a-f]{40}$")


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["prepared", "live"] = "prepared"
    scenario: Literal["independent", "conflict"] = "independent"
    consent: bool = False
    budget: float = Field(default=1, ge=0.16, le=1)


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _owned(root: Path, run_id: str) -> Path:
    uuid.UUID(run_id)
    base = (root / "lesson-57").resolve()
    owned = base / run_id
    if owned.parent != base or owned.is_symlink():
        raise ValueError("Invalid owned run path")
    return owned


def _check_owner(owned: Path, run_id: str) -> None:
    if (not owned.is_dir() or owned.is_symlink() or owned.resolve() != owned or
            (owned / ".owner").read_text(encoding="ascii") != run_id):
        raise PermissionError("Owned run marker mismatch")


def _environment(owned: Path) -> dict[str, str]:
    home = owned / "home"
    home.mkdir()
    config = owned / "gitconfig"
    config.write_text("", encoding="ascii")
    hooks = owned / "hooks"
    hooks.mkdir()
    return {
        "PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""), "COMSPEC": os.environ.get("COMSPEC", ""),
        "HOME": str(home), "USERPROFILE": str(home), "TMP": str(home), "TEMP": str(home),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(config),
        "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Lesson Worker",
        "GIT_AUTHOR_EMAIL": "worker@example.invalid", "GIT_COMMITTER_NAME": "Lesson Worker",
        "GIT_COMMITTER_EMAIL": "worker@example.invalid", "GIT_OPTIONAL_LOCKS": "0",
    }


async def _command(owned: Path, run_id: str, cwd: Path, env: dict[str, str],
                   program: str, *args: str, abort: asyncio.Event | None = None,
                   ok: bool = True) -> dict[str, Any]:
    _check_owner(owned, run_id)
    if not cwd.is_relative_to(owned):
        raise PermissionError("Child command escaped owned run")
    if abort is not None and abort.is_set():
        raise asyncio.CancelledError
    argv = [program]
    if program == "git":
        argv += ["-c", "core.longpaths=true", "-c", f"core.hooksPath={owned / 'hooks'}",
                 "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
    argv += list(args)
    child = await asyncio.create_subprocess_exec(*argv, cwd=cwd, env=env,
                                                  stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(child.communicate(), 10)
    except (TimeoutError, asyncio.CancelledError):
        child.kill()
        await child.wait()
        raise
    if len(stdout) > 65536 or len(stderr) > 65536:
        raise ValueError("Child output exceeded bound")
    result = {"exit": child.returncode, "closed": child.returncode is not None,
              "out": stdout.decode(errors="replace"), "err": stderr.decode(errors="replace")[:500]}
    if ok and child.returncode:
        raise RuntimeError(f"{program} {args[0] if args else ''} exited {child.returncode}: {str(result['err'])[:120]}")
    return result


def _file_exact(path: Path, source: str) -> bool:
    try:
        stat = path.lstat()
        return (path.is_file() and not path.is_symlink() and stat.st_nlink == 1 and
                stat.st_size <= 1024 and path.read_bytes() == source.encode())
    except OSError:
        return False


def _node_binary() -> str:
    candidate = shutil.which("node")
    if candidate is None:
        raise FileNotFoundError("Node 24 is required")
    try:
        probe = subprocess.run([candidate, "--version"], capture_output=True, text=True,
                               timeout=3, check=False)
        if probe.returncode == 0 and probe.stdout.startswith("v24."):
            return candidate
    except (OSError, TimeoutError):
        pass
    # nvm-windows may expose an inactive .nodejs shim even with Node 24 installed.
    installs = Path(candidate).parent.parent / "installs"
    for binary in sorted(installs.glob("v24.*/node.exe"), reverse=True):
        if binary.is_file():
            return str(binary)
    raise FileNotFoundError("An active Node 24 executable is required")


def _sanitize(value: Any, owned: Path) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize(item, owned) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, owned) for item in value]
    if isinstance(value, str):
        return value.replace(str(owned), "[OWNED_RUN]").replace(str(owned).replace("\\", "/"), "[OWNED_RUN]")
    return value


async def run_workshop(selected: RunInput, root: Path, abort: asyncio.Event | None = None,
                       on_event: Any = None, native_worker: Any = None,
                       run_id: str | None = None, prepared_hook: Any = None,
                       before_integration: Any = None, allow_live: bool = False) -> dict[str, Any]:
    if not shutil.which("git"):
        raise FileNotFoundError("Git and Node are required")
    node_binary = _node_binary()
    if selected.mode == "live":
        if not allow_live or not selected.consent:
            raise PermissionError("Fresh consent and enabled live access are required")
        from agent_lab.headless_native import bundled_cli, private_key

        bundled_cli()
        private_key()
    if selected.mode == "live" and native_worker is None:
        from agent_lab.worktrees_native import native_worker as actual_worker
        native_worker = actual_worker
    run_id = run_id or str(uuid.uuid4())
    owned = _owned(root, run_id)
    owned.mkdir(parents=True, exist_ok=False)
    (owned / ".owner").write_text(run_id, encoding="ascii")
    env = _environment(owned)
    repo = owned / "repo"
    repo.mkdir()
    spec = fixture()
    names = ["greeting", "tax" if selected.scenario == "independent" else "alternative"]
    report: dict[str, Any] = {"runId": run_id, "source": "real-owned-git-workshop",
                              "mode": selected.mode, "scenario": selected.scenario, "status": "running",
                              "events": [], "workers": [], "integration": [], "combinedTests": [],
                              "cleanup": [], "errors": [], "interrupted": False, "settled": False,
                              "sdkQueries": 0, "modelCalls": 0 if selected.mode == "prepared" else None,
                              "reportedSdkUsd": 0 if selected.mode == "prepared" else None}
    git_lock = asyncio.Lock()

    async def event(kind: str, **details: Any) -> None:
        row = {"seq": len(report["events"]) + 1, "kind": kind, **details}
        report["events"].append(row)
        if on_event is not None:
            await on_event(row)

    async def git(cwd: Path, *args: str, ok: bool = True) -> dict[str, Any]:
        async with git_lock:
            return await _command(owned, run_id, cwd, env, "git", *args, abort=abort, ok=ok)

    async def node(cwd: Path, source: str) -> dict[str, Any]:
        return await _command(owned, run_id, cwd, env, node_binary, "--input-type=module", "-e", source,
                              abort=abort, ok=False)

    try:
        async with asyncio.timeout(90 if selected.mode == "live" else 30):
            await git(repo, "init", "-b", "main")
            for name, source in spec["base"].items():
                (repo / name).write_bytes(source.encode())
            await git(repo, "add", "--", *spec["base"].keys())
            await git(repo, "commit", "-m", "base")
            base = (await git(repo, "rev-parse", "HEAD"))["out"].strip()
            report["baseSHA"] = base
            await event("base-commit", sha=base)
            paths = {name: owned / name for name in names}
            for name in names:
                await git(repo, "worktree", "add", "-b", f"worker/{name}", str(paths[name]), base)
            await event("worktrees-created", branches=[f"worker/{name}" for name in names])

            async def worker(name: str) -> dict[str, Any]:
                item = spec["workers"][name]
                path = paths[name]
                row: dict[str, Any] = {"name": name, "branch": f"worker/{name}",
                                       "file": item["file"], "started": True, "error": None}
                await event("worker-start", name=name)
                try:
                    if selected.mode == "prepared":
                        (path / item["file"]).write_bytes(item["source"].encode())
                        if prepared_hook is not None:
                            await prepared_hook(name, path, item)
                    else:
                        row["native"] = await native_worker(path, item, owned, abort)
                        report["sdkQueries"] += 1
                    row["preCommitSHA"] = (await git(path, "rev-parse", "HEAD"))["out"].strip()
                    row["observedBranch"] = (await git(path, "symbolic-ref", "--short", "HEAD"))["out"].strip()
                    tracked = (await git(path, "diff", "--no-renames", "--name-only", "-z", "HEAD"))["out"].split("\0")
                    untracked = (await git(path, "ls-files", "--others", "--exclude-standard", "-z"))["out"].split("\0")
                    row["changed"] = sorted(set(filter(None, tracked + untracked)))
                    row["sourceExact"] = _file_exact(path / item["file"], item["source"])
                    if (row["preCommitSHA"] != base or row["observedBranch"] != row["branch"] or
                            row["changed"] != [item["file"]] or not row["sourceExact"] or
                            (selected.mode == "live" and not row["native"].get("passed"))):
                        raise ValueError("Worker identity, exact file or native evidence failed")
                    row["test"] = await node(path, item["tests"])
                    if row["test"]["exit"] != 0 or not row["test"]["closed"]:
                        raise ValueError("Worker behavior test failed")
                    row["diff"] = (await git(path, "diff", "--", item["file"]))["out"][:6000]
                    await git(path, "add", "--", item["file"])
                    await git(path, "commit", "-m", f"worker {name}")
                    row["workerSHA"] = (await git(path, "rev-parse", "HEAD"))["out"].strip()
                    row["parentSHA"] = (await git(path, "rev-parse", "HEAD^") )["out"].strip()
                    await event("worker-commit", name=name, sha=row["workerSHA"])
                except Exception as exc:
                    row["error"] = type(exc).__name__ + ": " + str(exc)[:160]
                    await event("worker-failed", name=name, error=row["error"])
                return row

            tasks = [asyncio.create_task(worker(name)) for name in names]
            settled = await asyncio.gather(*tasks, return_exceptions=True)
            report["workers"] = [row if isinstance(row, dict) else
                                 {"name": names[index], "error": type(row).__name__}
                                 for index, row in enumerate(settled)]
            report["settled"] = True
            if selected.mode == "live":
                costs = [row.get("native", {}).get("costUsd") for row in report["workers"]]
                report["reportedSdkUsd"] = sum(costs) if all(isinstance(cost, (int, float)) for cost in costs) else None
            if any(row.get("error") for row in report["workers"]):
                raise ValueError("One or more workers failed; integration blocked")
            if before_integration is not None:
                await before_integration(repo)
            report["mainBefore"] = (await git(repo, "rev-parse", "HEAD"))["out"].strip()
            report["mainCleanBefore"] = not (await git(repo, "status", "--porcelain"))["out"]
            if report["mainBefore"] != base or not report["mainCleanBefore"]:
                raise ValueError("Main changed before integration")
            for row in report["workers"]:
                result = await git(repo, "cherry-pick", row["workerSHA"], ok=False)
                if result["exit"]:
                    unmerged = (await git(repo, "diff", "--name-only", "--diff-filter=U"))["out"].splitlines()
                    report["conflict"] = {"worker": row["name"], "unmerged": unmerged,
                                          "pickExit": result["exit"], "priorPicks": len(report["integration"])}
                    await git(repo, "cherry-pick", "--abort")
                    report["conflict"]["aborted"] = True
                    report["status"] = "conflict"
                    await event("conflict-aborted", unmerged=unmerged)
                    break
                integrated = (await git(repo, "rev-parse", "HEAD"))["out"].strip()
                parent = (await git(repo, "rev-parse", "HEAD^") )["out"].strip()
                report["integration"].append({"worker": row["name"], "workerSHA": row["workerSHA"],
                                               "integratedSHA": integrated, "parentSHA": parent,
                                               "sourceExact": _file_exact(repo / row["file"], spec["workers"][row["name"]]["source"])})
                await event("integrated", worker=row["name"], sha=integrated)
                if not report["integration"][-1]["sourceExact"]:
                    raise ValueError("Integrated source mismatch")
            if report["status"] != "conflict":
                for name in ("greeting", "tax"):
                    result = await node(repo, spec["workers"][name]["tests"])
                    report["combinedTests"].append({"name": name, **result})
                    if result["exit"] != 0 or not result["closed"]:
                        raise ValueError("Combined behavior failed")
                for name in names:
                    path = paths[name]
                    clean = not (await git(path, "status", "--porcelain"))["out"]
                    if not clean:
                        raise ValueError("Dirty worker retained")
                    await git(repo, "worktree", "remove", str(path))
                    report["cleanup"].append({"worker": name, "clean": True,
                                              "nonForce": True, "absent": not path.exists()})
                report["status"] = "completed"
    except asyncio.CancelledError:
        report["interrupted"] = True
        report["errors"].append("Cancelled")
    except TimeoutError:
        report["interrupted"] = True
        report["errors"].append("Deadline exceeded")
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc)[:160])
    finally:
        try:
            report["mainHEAD"] = (await _command(owned, run_id, repo, env, "git", "rev-parse", "HEAD"))["out"].strip()
            report["mainClean"] = not (await _command(owned, run_id, repo, env, "git", "status", "--porcelain"))["out"]
            report["worktreeList"] = (await _command(owned, run_id, repo, env, "git", "worktree", "list", "--porcelain"))["out"]
            report["worktreeCount"] = report["worktreeList"].count("worktree ")
            report["workerRefs"] = {name: (await _command(owned, run_id, repo, env, "git", "rev-parse", f"refs/heads/worker/{name}"))["out"].strip() for name in names}
        except Exception as exc:
            report["errors"].append("Final observation: " + type(exc).__name__)
        if report["status"] == "running":
            report["status"] = "needs-review"
        report["check"] = "passed" if grade(report) else "needs-review"
        report = _sanitize(report, owned)
        _check_owner(owned, run_id)
        target = owned / "report.json"
        temporary = owned / "report.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    return report


def grade(report: dict[str, Any]) -> bool:
    try:
        if (report["source"] != "real-owned-git-workshop" or report["status"] != "completed" or
                report["scenario"] != "independent" or report["interrupted"] or report["errors"] or
                not report["settled"] or len(report["workers"]) != 2 or
                len(report["integration"]) != 2 or len(report["combinedTests"]) != 2 or
                len(report["cleanup"]) != 2 or not report["mainClean"] or
                report["worktreeCount"] != 1 or report["mainBefore"] != report["baseSHA"] or
                not report["mainCleanBefore"]):
            return False
        base = report["baseSHA"]
        if not SHA.fullmatch(base):
            return False
        starts = [row["seq"] for row in report["events"] if row["kind"] == "worker-start"]
        commits = [row["seq"] for row in report["events"] if row["kind"] == "worker-commit"]
        if len(starts) != 2 or len(commits) != 2 or max(starts) >= min(commits):
            return False
        prior = base
        for index, name in enumerate(("greeting", "tax")):
            worker = report["workers"][index]
            pick = report["integration"][index]
            if (worker["name"] != name or worker["branch"] != f"worker/{name}" or
                    worker["observedBranch"] != worker["branch"] or worker["preCommitSHA"] != base or
                    worker["parentSHA"] != base or worker["workerSHA"] == base or
                    not SHA.fullmatch(worker["workerSHA"]) or worker["changed"] != [worker["file"]] or
                    not worker["sourceExact"] or worker["test"]["exit"] != 0 or
                    not worker["test"]["closed"] or pick["worker"] != name or
                    pick["workerSHA"] != worker["workerSHA"] or pick["parentSHA"] != prior or
                    not pick["sourceExact"] or report["workerRefs"][name] != worker["workerSHA"] or
                    report["combinedTests"][index]["exit"] != 0 or
                    not report["combinedTests"][index]["closed"] or
                    report["cleanup"][index] != {"worker": name, "clean": True,
                                                   "nonForce": True, "absent": True}):
                return False
            prior = pick["integratedSHA"]
        if report["mainHEAD"] != prior:
            return False
        if report["mode"] == "prepared":
            return report["sdkQueries"] == report["modelCalls"] == report["reportedSdkUsd"] == 0
        return (report["mode"] == "live" and report["sdkQueries"] == 2 and
                report["modelCalls"] is None and all(row["native"]["passed"] for row in report["workers"]) and
                all(isinstance(row["native"]["costUsd"], (int, float)) and
                    0 <= row["native"]["costUsd"] <= 0.08 for row in report["workers"]) and
                report["reportedSdkUsd"] == sum(row["native"]["costUsd"] for row in report["workers"]) and
                report["reportedSdkUsd"] <= 0.16)
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def load_report(root: Path, run_id: str) -> dict[str, Any]:
    owned = _owned(root, run_id)
    if not owned.exists():
        raise FileNotFoundError(run_id)
    _check_owner(owned, run_id)
    path = owned / "report.json"
    stat = path.lstat()
    if path.is_symlink() or not path.is_file() or stat.st_nlink != 1 or stat.st_size >= 1_000_000:
        raise ValueError("Invalid owned report")
    raw = path.read_bytes()
    report = json.loads(raw)
    if report["runId"] != run_id:
        raise ValueError("Report identity mismatch")
    return {"source": "persisted-owned-report", "sha256": hashlib.sha256(raw).hexdigest(),
            "report": report}
