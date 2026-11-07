"""Lesson 39: owned project configuration roots and SDK origin observations."""

import asyncio
import dataclasses
import hashlib
import json
import os
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    UserMessage,
)
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
from claude_agent_sdk.types import PermissionResultDeny, ToolResultBlock, ToolUseBlock

from agent_lab.config import Settings
from agent_lab.models import Event, RunRequest, lesson_request
from agent_lab.sdk import isolated_env, require_live_access, resolve_cli_path

SOURCE_LIVE = "live SDK initialization, owned hook log and actual host files"
CHOICES = {"trusted", "branch", "docs"}
ROOTS = {"trusted", "branch", "omitted", "relative", "missing", "file"}


async def command(*args: str, cwd: Path, home: Path, deadline: float = 10) -> str:
    env = os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(home / "empty-gitconfig"),
               GIT_TERMINAL_PROMPT="0")
    proc = await asyncio.create_subprocess_exec(*args, cwd=cwd, env=env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), deadline)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.communicate()
        raise
    if proc.returncode:
        raise RuntimeError(f"Owned Git command failed ({proc.returncode}): {stderr.decode(errors='replace')[:300]}")
    return stdout.decode(errors="replace")


def hook_program(path: Path) -> None:
    path.write_text('''import json, os, sys
from pathlib import Path
data = json.load(sys.stdin)
root = Path(__file__).resolve().parent
row = {"run_id": root.name, "session_id": data.get("session_id"),
       "event": data.get("hook_event_name"), "marker": sys.argv[1],
       "project_dir": os.getenv("CLAUDE_PROJECT_DIR"), "cwd": os.getcwd(),
       "settings_marker": os.getenv("LAB_PROJECT_MARKER"),
       "local_marker": os.getenv("LAB_LOCAL_MARKER"),
       "pid": os.getpid()}
with (root / "hooks.jsonl").open("a", encoding="utf-8") as out:
    out.write(json.dumps(row) + "\\n")
''', encoding="utf-8")


async def fixture(base: Path) -> dict[str, Path]:
    base = await asyncio.to_thread(base.resolve)
    await asyncio.to_thread(base.mkdir, parents=True, exist_ok=False)
    hook = base / "hook.py"
    hook_program(hook)
    trusted = base / "trusted"
    trusted.mkdir()
    await command("git", "init", "-q", str(trusted), cwd=base, home=base)
    (trusted / "notes.txt").write_text("Trusted checkout notes.\n", encoding="utf-8")
    await command("git", "add", "notes.txt", cwd=trusted, home=base)
    await command("git", "-c", "user.name=Lab", "-c", "user.email=lab@example.invalid",
                  "-c", "core.hooksPath=NUL", "commit", "-qm", "fixture", cwd=trusted, home=base)
    branch, docs = base / "branch", base / "docs"
    await command("git", "worktree", "add", "-qb", "lesson-branch", str(branch), cwd=trusted, home=base)
    await command("git", "worktree", "add", "-q", "--detach", str(docs), cwd=trusted, home=base)
    for name, checkout, allow in (("TRUSTED", trusted, False), ("BRANCH", branch, True)):
        dot = checkout / ".claude"
        dot.mkdir()
        commands = dot / "commands"
        commands.mkdir()
        (commands / f"l39-{name.lower()}.md").write_text(f"Report {name} command origin.\n", encoding="utf-8")
        skill = dot / "skills" / "l39-origin"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: l39-origin\ndescription: {name} origin fixture\n---\n{name} skill origin.\n", encoding="utf-8")
        local = name + "_LOCAL"
        quoted_hook = f'"{sys.executable}" "{hook}" {name}'
        settings = {"permissions": {"deny" if not allow else "allow": ["Bash"]},
                    "env": {"LAB_PROJECT_MARKER": name},
                    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": quoted_hook}]}]}}
        (dot / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        (dot / "settings.local.json").write_text(json.dumps({"env": {"LAB_LOCAL_MARKER": local}}), encoding="utf-8")
        (checkout / "CLAUDE.md").write_text(f"{name} memory marker.\n", encoding="utf-8")
    (base / "not-a-directory.txt").write_text("file root", encoding="utf-8")
    return {"trusted": trusted, "branch": branch, "docs": docs, "base": base}


def root_value(paths: dict[str, Path], selected: str) -> str | None:
    if selected == "omitted":
        return None
    if selected in {"trusted", "branch"}:
        return str(paths[selected])
    if selected == "relative":
        return "../trusted"
    if selected == "missing":
        return str(paths["base"] / "missing")
    if selected == "file":
        return str(paths["base"] / "not-a-directory.txt")
    raise ValueError("Unknown configuration root selection.")


def options(paths: dict[str, Path], config: Path, settings: Settings, *,
            cwd: str, root: str, sources: str, live: bool, takeover: bool = False) -> ClaudeAgentOptions:
    if cwd not in CHOICES or root not in ROOTS or sources not in {"project-local", "none"}:
        raise ValueError("Invalid fixed lesson 39 selection.")
    selected = root_value(paths, root)
    extra: dict[str, str | None] = {"no-session-persistence": None}
    if selected is not None:
        extra["project-config-root"] = selected
    return ClaudeAgentOptions(
        cwd=str(paths[cwd]), model=settings.model,
        cli_path=resolve_cli_path(settings) if live else None,
        tools=["Bash"] if takeover else [], allowed_tools=[], mcp_servers={},
        strict_mcp_config=True, setting_sources=["project", "local"] if sources == "project-local" else [],
        env=isolated_env(config), extra_args=extra, max_turns=3, max_budget_usd=0.10,
    )


def dry_flags(paths: dict[str, Path], settings: Settings) -> dict[str, Any]:
    rows = []
    for root in ("omitted", "trusted", "relative"):
        opts = options(paths, paths["base"] / "config", settings, cwd="branch",
                       root=root, sources="project-local", live=False)
        transport = SubprocessCLITransport(prompt="", options=opts)
        transport._cli_path = "inert-cli"  # type: ignore[attr-defined]
        argv = transport._build_command()
        values = [argv[index + 1] for index, arg in enumerate(argv[:-1]) if arg == "--project-config-root"]
        rows.append({"root": root, "argv": argv, "project_config_root_values": values,
                     "expected": root_value(paths, root), "serialized": values == ([] if root == "omitted" else [root_value(paths, root)])})
    return {"rows": rows, "inert_process": True, "sdk_called": False,
            "all_serialized": all(row["serialized"] for row in rows)}


def file_hashes(paths: dict[str, Path]) -> dict[str, str]:
    result = {}
    for name in ("trusted", "branch"):
        for filename in (".claude/settings.json", ".claude/settings.local.json", "CLAUDE.md",
                         f".claude/commands/l39-{name.lower()}.md",
                         ".claude/skills/l39-origin/SKILL.md"):
            path = paths[name] / filename
            if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 16_384:
                raise ValueError("Unsafe fixture file.")
            result[f"{name}/{filename}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def hook_rows(base: Path) -> list[dict[str, Any]]:
    path = base / "hooks.jsonl"
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 16_384:
        raise ValueError("Unsafe hook log.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def prepared_hook(paths: dict[str, Path], origin: str, session_id: str) -> None:
    """Run the same fixed hook child against owned settings files with labelled input."""
    project = paths[origin]
    project_values = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))["env"]
    local_values = json.loads((project / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["env"]
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("ANTHROPIC_", "AWS_", "AZURE_", "GOOGLE_", "INWORLD_"))}
    env.update(project_values, **local_values, CLAUDE_PROJECT_DIR=str(project))
    proc = await asyncio.create_subprocess_exec(sys.executable, str(paths["base"] / "hook.py"),
        origin.upper(), cwd=project, env=env, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    payload = json.dumps({"session_id": session_id, "hook_event_name": "SessionStart"}).encode()
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(payload), 5)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.communicate()
        raise
    if proc.returncode:
        raise RuntimeError(f"Owned hook failed: {stderr.decode(errors='replace')[:200]}")


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    choice = report["selected"]
    init, results, hooks = report["initialization"], report["results"], report["hook_log"]
    expected_origin = choice["root"] if choice["root"] != "omitted" else choice["cwd"]
    if expected_origin in {"relative", "missing", "file"}:
        expected_origin = "trusted"
    expected_marker = expected_origin.upper()
    same = bool(len(init) == 1 and len(results) == 1
                and init[0].get("session_id") == results[0].get("session_id")
                and init[0].get("cwd") == report["paths"][choice["cwd"]]
                and results[0].get("subtype") == "success" and not results[0].get("is_error"))
    inventory = init[0].get("slash_commands") or [] if init else []
    expected_command = "l39-" + expected_origin.lower()
    other_command = "l39-branch" if expected_marker == "TRUSTED" else "l39-trusted"
    if choice["sources"] == "none" or expected_origin == "docs":
        origin = not hooks and not any(item.startswith("l39-") for item in inventory)
    else:
        origin = bool(len(hooks) == 1 and all(row.get("run_id") == report["run_id"]
                                    and row.get("session_id") == init[0].get("session_id")
                                    and row.get("marker") == expected_marker
                                    and row.get("event") == "SessionStart"
                                    and row.get("settings_marker") == expected_marker
                                    and row.get("local_marker") == expected_marker + "_LOCAL"
                                    and Path(str(row.get("project_dir"))).resolve() == Path(report["paths"][expected_origin.lower()]).resolve()
                                    and Path(str(row.get("cwd"))).resolve() == Path(report["paths"][expected_origin.lower()]).resolve()
                                    for row in hooks)) if init else False
        origin = bool(origin and expected_command in inventory and other_command not in inventory)
    intact = report["before_hashes"] == report["after_hashes"]
    passed = bool(same and origin and intact and report["connection_closed"]
                  and report["scenario"] == "success")
    return {**report, "identity_matched": same, "origin_matched": origin,
            "fixture_intact": intact, "experiment_passed": passed,
            "expected_check": "passed" if passed else "needs-review"}


async def execute(base: Path, request: RunRequest, settings: Settings, emit: Any) -> dict[str, Any]:
    request = lesson_request(39, request)
    selected = request.lesson_options
    run_id = uuid.uuid4().hex
    paths = await fixture(base / run_id)
    config = paths["base"] / "config"
    config.mkdir()
    before = file_hashes(paths)
    report: dict[str, Any] = {"run_id": run_id, "mode": request.mode,
        "selected": selected, "scenario": request.scenario,
        "paths": {key: str(value) for key, value in paths.items() if key != "base"},
        "initialization": [], "results": [], "hook_log": [],
        "before_hashes": before, "after_hashes": {}, "connection_closed": False}
    if request.mode == "live":
        require_live_access(settings)
        opts = options(paths, config, settings, cwd=selected["cwd"], root=selected["root"],
                       sources=selected["sources"], live=True)
        async with ClaudeSDKClient(options=opts) as client:
            await client.query("Reply in one sentence: what is a Python project configuration root?")
            async for message in client.receive_response():
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    report["initialization"].append({"session_id": message.data.get("session_id"),
                                                      "cwd": message.data.get("cwd"),
                                                      "tools": message.data.get("tools"),
                                                      "slash_commands": message.data.get("slash_commands")})
                elif isinstance(message, ResultMessage):
                    report["results"].append({"session_id": message.session_id,
                                              "subtype": message.subtype, "is_error": message.is_error,
                                              "cost_usd": message.total_cost_usd})
                    await emit(Event(kind="result", data={"lesson_id": 39, "session_id": message.session_id,
                                                          "subtype": message.subtype, "is_error": message.is_error,
                                                          "total_cost_usd": message.total_cost_usd}))
        report["connection_closed"] = True
    else:
        sid = "prepared-" + secrets.token_hex(8)
        origin = selected["root"] if selected["root"] != "omitted" else selected["cwd"]
        report["initialization"].append({"session_id": sid, "cwd": str(paths[selected["cwd"]]),
                                         "tools": [], "slash_commands": ["l39-" + origin] if selected["sources"] == "project-local" and origin != "docs" else [], "authored_fixture": True})
        report["results"].append({"session_id": sid, "subtype": "success", "is_error": False,
                                  "cost_usd": None, "authored_fixture": True})
        if selected["sources"] == "project-local" and origin != "docs":
            await prepared_hook(paths, origin, sid)
        report["connection_closed"] = True
    report["hook_log"] = hook_rows(paths["base"])
    report["after_hashes"] = file_hashes(paths)
    if request.scenario == "missing-evidence":
        report["hook_log"].clear()
    elif request.scenario == "wrong-identity":
        report["results"][0]["session_id"] = "foreign"
    elif request.scenario == "interrupted":
        report["connection_closed"] = False
    elif request.scenario == "failed":
        report["results"][0]["is_error"] = True
    elif request.scenario == "wrong-hook" and report["hook_log"]:
        report["hook_log"][0]["marker"] = "FOREIGN"
    elif request.scenario == "duplicate-hook" and report["hook_log"]:
        report["hook_log"].append(dict(report["hook_log"][0]))
    elif request.scenario == "duplicate-result":
        report["results"].append(dict(report["results"][0]))
    elif request.scenario == "missing-command":
        report["initialization"][0]["slash_commands"] = []
    elif request.scenario == "changed-fixture":
        report["after_hashes"]["trusted/.claude/settings.json"] = "tampered"
    checked = evaluate(report)
    proof = {"experiment": checked, "experiment_passed": checked["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 39, "result": proof}))
    return proof


async def local(base: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    selected = lesson_request(39, request).lesson_options
    runner = takeover if selected["action"] == "takeover" else execute
    return await runner(base, request.model_copy(update={"mode": "offline"}), Settings(), ignore)


def exact_command(nonce: str) -> str:
    return f'python -c "from pathlib import Path; Path(\'proof-{nonce}.txt\').write_text(\'{nonce}\')"'


def trust_owned_config(config: Path, paths: dict[str, Path]) -> None:
    entries = {str(paths[name]).replace("\\", "/"): {"hasTrustDialogAccepted": True}
               for name in ("trusted", "branch")}
    (config / ".claude.json").write_text(json.dumps({"projects": entries}), encoding="utf-8")


def takeover_report(report: dict[str, Any]) -> dict[str, Any]:
    selected = report["selected"]
    expected_origin = "TRUSTED" if selected["root"] == "trusted" else "BRANCH"
    init = report["initialization"]
    terminals = report["results"]
    expected_path = report["paths"][expected_origin.lower()]
    hooked = bool(init and len(report["hook_log"]) == 1 and all(
        row.get("run_id") == report["run_id"]
        and row.get("session_id") == init[0].get("session_id") and row.get("marker") == expected_origin
        and row.get("event") == "SessionStart"
        and row.get("settings_marker") == expected_origin
        and row.get("local_marker") == expected_origin + "_LOCAL"
        and Path(str(row.get("project_dir"))).resolve() == Path(expected_path).resolve()
        and Path(str(row.get("cwd"))).resolve() == Path(expected_path).resolve()
        for row in report["hook_log"]))
    clean = report["before_hashes"] == report["after_hashes"]
    success = bool(len(init) == len(terminals) == 1 and terminals[0].get("session_id") == init[0].get("session_id")
                   and init[0].get("cwd") == report["paths"]["branch"]
                   and terminals[0].get("subtype") == "success" and terminals[0].get("is_error") is False)
    calls, tool_results = report["tool_calls"], report["tool_results"]
    proof = report["proof_file"] == report["nonce"]
    no_fallback = not report["fallback_denials"]
    if selected["root"] == "omitted":
        effect = bool(len(calls) == len(tool_results) == 1
                      and calls[0]["name"] == "Bash" and calls[0]["input"] == {"command": report["command"]}
                      and tool_results[0]["id"] == calls[0]["id"] and not tool_results[0]["is_error"]
                      and report["pre_events"] == [{"id": calls[0]["id"], "valid": True}]
                      and report["branch_allow_rule"] and proof and no_fallback)
        status = "branch-settings-allowed"
    elif "Bash" not in (init[0].get("tools") or []) if init else False:
        effect = bool(not calls and not tool_results and not report["pre_events"]
                      and not report["fallback_denials"] and not proof
                      and report["trusted_deny_rule"])
        status = "trusted-tool-unavailable"
    else:
        effect = bool(calls and tool_results and not proof and no_fallback
                      and tool_results[0]["is_error"] and report["permission_denials"])
        status = "trusted-permission-denied"
    passed = bool(hooked and clean and success and effect and report["connection_closed"]
                  and report["scenario"] == "success")
    return {**report, "origin_matched": hooked, "fixture_intact": clean,
            "terminal_matched": success, "takeover_outcome": status,
            "effect_matched": effect, "experiment_passed": passed,
            "expected_check": "passed" if passed else "needs-review"}


async def takeover(base: Path, request: RunRequest, settings: Settings, emit: Any) -> dict[str, Any]:
    request = lesson_request(39, request)
    selected = request.lesson_options
    if selected["cwd"] != "branch" or selected["root"] not in {"trusted", "omitted"} or selected["sources"] != "project-local":
        raise ValueError("Takeover uses branch cwd, enabled project/local sources, and trusted or omitted root.")
    if request.mode == "live":
        require_live_access(settings)
    run_id = uuid.uuid4().hex
    paths = await fixture(base / run_id)
    config = paths["base"] / "config"
    config.mkdir()
    trust_owned_config(config, paths)
    nonce = secrets.token_hex(8)
    fixed = exact_command(nonce)
    target = paths["branch"] / f"proof-{nonce}.txt"
    before = file_hashes(paths)
    report: dict[str, Any] = {"run_id": run_id, "mode": request.mode, "selected": selected,
        "scenario": request.scenario, "nonce": nonce, "command": fixed,
        "paths": {key: str(value) for key, value in paths.items() if key != "base"},
        "requested_tools": ["Bash"],
        "trusted_deny_rule": "Bash" in json.loads((paths["trusted"] / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"].get("deny", []),
        "branch_allow_rule": "Bash" in json.loads((paths["branch"] / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"].get("allow", []),
        "initialization": [], "results": [], "tool_calls": [], "tool_results": [],
        "pre_events": [], "permission_denials": [], "fallback_denials": [],
        "hook_log": [], "proof_file": None, "before_hashes": before,
        "after_hashes": {}, "connection_closed": False}

    async def pre(data: dict[str, Any], call_id: str | None, context: Any) -> dict[str, Any]:
        valid = data.get("tool_name") == "Bash" and data.get("tool_input") == {"command": fixed}
        report["pre_events"].append({"id": call_id, "valid": valid})
        if valid:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": "Only the owned exact probe is permitted."}}

    async def fallback(tool_name: str, input: dict[str, Any], context: Any) -> PermissionResultDeny:
        report["fallback_denials"].append({"tool_name": tool_name})
        return PermissionResultDeny(message="No host fallback permission for this command.")

    if request.mode == "live":
        opts = options(paths, config, settings, cwd="branch", root=selected["root"],
                       sources="project-local", live=True, takeover=True)
        opts = dataclasses.replace(opts, hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[pre])]},  # type: ignore[list-item]
                                   can_use_tool=fallback, system_prompt="Call Bash exactly once with the exact command supplied by the user. Do not add quotes, options, prefixes, or retries. Then reply Done.")
        try:
            async with ClaudeSDKClient(options=opts) as client:
                await client.query("Call Bash exactly once with this exact command: " + fixed)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        report["initialization"].append({"session_id": message.data.get("session_id"),
                            "cwd": message.data.get("cwd"), "tools": message.data.get("tools")})
                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                report["tool_calls"].append({"id": block.id, "name": block.name, "input": block.input})
                    elif isinstance(message, UserMessage):
                        for part in message.content:
                            if isinstance(part, ToolResultBlock):
                                report["tool_results"].append({"id": part.tool_use_id, "is_error": part.is_error})
                                if part.is_error and not report["fallback_denials"]:
                                    report["permission_denials"].append({"id": part.tool_use_id})
                    elif isinstance(message, ResultMessage):
                        report["results"].append({"session_id": message.session_id,
                            "subtype": message.subtype, "is_error": message.is_error,
                            "cost_usd": message.total_cost_usd})
                        await emit(Event(kind="result", data={"lesson_id": 39,
                            "total_cost_usd": message.total_cost_usd}))
            report["connection_closed"] = True
        finally:
            report["hook_log"] = hook_rows(paths["base"])
    else:
        sid = "prepared-" + secrets.token_hex(8)
        report["initialization"].append({"session_id": sid, "cwd": str(paths["branch"]),
            "tools": ["Bash"] if selected["root"] == "omitted" else [], "authored_fixture": True})
        report["results"].append({"session_id": sid, "subtype": "success", "is_error": False,
                                  "cost_usd": None, "authored_fixture": True})
        marker = "BRANCH" if selected["root"] == "omitted" else "TRUSTED"
        await prepared_hook(paths, marker.lower(), sid)
        report["hook_log"] = hook_rows(paths["base"])
        if selected["root"] == "omitted":
            report["pre_events"].append({"id": "prepared-call", "valid": True})
            await command("python", "-c", f"from pathlib import Path; Path('proof-{nonce}.txt').write_text('{nonce}')",
                          cwd=paths["branch"], home=paths["base"])
            report["tool_calls"].append({"id": "prepared-call", "name": "Bash",
                                         "input": {"command": fixed}, "authored_fixture": True})
            report["tool_results"].append({"id": "prepared-call", "is_error": False,
                                           "authored_fixture": True})
        report["connection_closed"] = True
    if target.exists() and (target.is_symlink() or target.stat().st_nlink != 1 or target.stat().st_size > 128):
        raise ValueError("Unsafe proof file.")
    report["proof_file"] = target.read_text(encoding="utf-8") if target.is_file() else None
    report["after_hashes"] = file_hashes(paths)
    if request.scenario == "missing-evidence":
        report["hook_log"].clear()
    elif request.scenario == "wrong-identity":
        report["results"][0]["session_id"] = "foreign"
    elif request.scenario == "interrupted":
        report["connection_closed"] = False
    elif request.scenario == "failed":
        report["results"][0]["is_error"] = True
    elif request.scenario == "wrong-hook" and report["hook_log"]:
        report["hook_log"][0]["marker"] = "FOREIGN"
    elif request.scenario == "duplicate-hook" and report["hook_log"]:
        report["hook_log"].append(dict(report["hook_log"][0]))
    elif request.scenario == "duplicate-result":
        report["results"].append(dict(report["results"][0]))
    elif request.scenario == "changed-fixture":
        report["after_hashes"]["trusted/.claude/settings.json"] = "tampered"
    elif request.scenario == "wrong-effect":
        report["proof_file"] = "wrong"
    checked = takeover_report(report)
    proof_result = {"experiment": checked, "experiment_passed": checked["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 39, "result": proof_result}))
    return proof_result


async def startup(base: Path, root: str, settings: Settings) -> dict[str, Any]:
    """Launch the actual CLI with an invalid root and no provider credentials."""
    if root not in {"relative", "missing", "file"}:
        raise ValueError("Startup probes accept only fixed invalid roots.")
    run_id = uuid.uuid4().hex
    paths = await fixture(base / run_id)
    config = paths["base"] / "config"
    config.mkdir()
    opts = options(paths, config, settings, cwd="branch", root=root,
                   sources="project-local", live=False)
    transport = SubprocessCLITransport(prompt="", options=opts)
    transport._cli_path = resolve_cli_path(settings)  # type: ignore[attr-defined]
    argv = transport._build_command()
    allowed_env = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
                   "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC", "LANG"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed_env}
    env.update(isolated_env(config))
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9"
    proc = await asyncio.create_subprocess_exec(*argv, cwd=paths["branch"], env=env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 12)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        stdout, stderr = await proc.communicate()
        timed_out = True
    error = stderr.decode(errors="replace")[-1000:]
    result = {"run_id": run_id, "mode": "startup", "root": root,
              "selected_root": root_value(paths, root), "cwd": str(paths["branch"]),
              "exit_code": proc.returncode, "timed_out": timed_out,
              "stderr_excerpt": error, "stdout_bytes": len(stdout),
              "provider_credentials_present": False, "provider_base": "http://127.0.0.1:9",
              "config_dir": str(config), "normal_success": proc.returncode == 0 and not timed_out,
              "startup_failure_observed": bool(proc.returncode and error and not timed_out)}
    return result
