"""Lesson 37: an owned stdio MCP gate and correlated Write effect."""

import asyncio
import json
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from fastapi import FastAPI, Header, HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_lab.config import ROOT, Settings
from agent_lab.exercises import EmbeddedServer
from agent_lab.foundations import Evidence
from agent_lab.models import Event, RunRequest, lesson_request

SOURCE_LIVE = "live SDK stream and actual host callbacks"
ORIGINAL = "GATE_ORIGINAL_37"
EDITED = "GATE_EDITED_37"
GATE_TOOL = "mcp__gate__approve"
ACTIVE_GATES: dict[str, "GateState"] = {}


def permission_rule(tool_name: str, tool_input: dict[str, Any]) -> dict[str, str]:
    """Build a scoped session-rule preview; Bash is never executed here."""
    if tool_name == "Bash":
        command = str(tool_input.get("command", "")).strip()
        first = command.split(maxsplit=1)[0] if command else ""
        if not first:
            raise ValueError("A Bash rule needs a command first word.")
        return {"toolName": "Bash", "ruleContent": first}
    if tool_name == "Write":
        return {"toolName": "Write", "ruleContent": str(tool_input["file_path"])}
    raise ValueError("Only Write or a Bash preview can be scoped.")


@dataclass
class GateState:
    root: Path
    run_id: str
    gate_id: str
    token: str
    action: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    pending_input: dict[str, Any] | None = None
    pending_future: asyncio.Future[str] | None = None

    def expected_path(self) -> Path:
        return self.root / "gate-original.txt"

    def final_path(self) -> Path:
        return self.root / ("gate-edited.txt" if self.action == "edit" else "gate-original.txt")

    def decide(self, body: dict[str, Any], token: str) -> str:
        if not secrets.compare_digest(token, self.token):
            raise ValueError("Invalid gate token.")
        if body.get("run_id") != self.run_id or body.get("gate_id") != self.gate_id or body.get("capability") != "owned-write":
            raise ValueError("Gate identity or capability mismatch.")
        if self.decisions:
            raise ValueError("This gate already has a decision.")
        tool_input = body.get("tool_input")
        if body.get("tool_name") != "Write" or not isinstance(tool_input, dict) or tool_input.get("file_path") != str(self.expected_path()) or tool_input.get("content") != ORIGINAL:
            raise ValueError("Only the fixed owned Write request can be decided.")
        self.calls.append({"run_id": self.run_id, "gate_id": self.gate_id,
                           "tool_name": "Write", "tool_input": tool_input})
        answer: dict[str, Any] = {"behavior": "allow"}
        if self.action == "edit":
            answer["updatedInput"] = {"file_path": str(self.final_path()), "content": EDITED}
        elif self.action == "remember":
            answer["updatedPermissions"] = [{"type": "addRules", "rules": [permission_rule("Write", tool_input)], "behavior": "allow", "destination": "session"}]
        elif self.action in {"deny", "interrupt"}:
            answer = {"behavior": "deny", "message": "The selected gate decision refused this Write.",
                      "interrupt": self.action == "interrupt"}
        response = "{malformed" if self.action == "malformed" else json.dumps(answer)
        self.decisions.append({"run_id": self.run_id, "gate_id": self.gate_id,
                               "action": self.action, "response": response})
        return response

    async def handle(self, body: dict[str, Any], token: str) -> str:
        if self.action == "manual":
            if not secrets.compare_digest(token, self.token):
                raise ValueError("Invalid gate token.")
            if body.get("run_id") != self.run_id or body.get("gate_id") != self.gate_id or body.get("capability") != "owned-write":
                raise ValueError("Gate identity or capability mismatch.")
            if body.get("tool_name") != "Write" or body.get("tool_input") != {"file_path": str(self.expected_path()), "content": ORIGINAL}:
                raise ValueError("Only the fixed owned Write request can be decided.")
            if self.pending_future is not None:
                raise ValueError("This gate already has a pending request.")
            self.pending_input = body
            self.pending_future = asyncio.get_running_loop().create_future()
            try:
                async with asyncio.timeout(60):
                    self.action = await self.pending_future
            except TimeoutError as exc:
                raise ValueError("The pending gate decision expired.") from exc
        return self.decide(body, token)

    def submit(self, gate_id: str, capability: str, action: str) -> None:
        if gate_id != self.gate_id or capability != "owned-write":
            raise ValueError("Unrelated gate decision.")
        if self.pending_future is None or self.pending_future.done() or self.decisions:
            raise ValueError("The gate has no unresolved request.")
        if action not in {"allow", "edit", "remember", "deny", "interrupt", "malformed"}:
            raise ValueError("Unsupported gate decision.")
        self.pending_future.set_result(action)


def bridge_app(gate: GateState) -> FastAPI:
    app = FastAPI()

    @app.post("/gate")
    async def gate_request(body: dict[str, Any], x_gate_token: str = Header()) -> dict[str, str]:
        try:
            return {"response": await gate.handle(body, x_gate_token)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return app


def gate_config(gate: GateState, url: str, log: Path) -> dict[str, Any]:
    return {"type": "stdio", "command": sys.executable,
            "args": ["-m", "agent_lab.permission_gate_child"],
            "env": {"PYTHONPATH": str(ROOT), "LAB_GATE_URL": url + "/gate",
                    "LAB_GATE_TOKEN": gate.token, "LAB_GATE_RUN": gate.run_id,
                    "LAB_GATE_ID": gate.gate_id, "LAB_GATE_CAPABILITY": "owned-write",
                    "LAB_GATE_LOG": str(log)}}


async def prepared_round_trip(gate: GateState, config: dict[str, Any], scenario: str = "success") -> dict[str, Any]:
    params = StdioServerParameters(command=config["command"], args=config["args"], env=config["env"])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            receipt = await client.call_tool("approve", {"tool_name": "Write", "input": {
                "file_path": str(gate.expected_path()),
                "content": "UNRELATED_37" if scenario == "rejected-input" else ORIGINAL}})
    text = next((part.text for part in receipt.content if part.type == "text"), "")
    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        decision = None
    if isinstance(decision, dict) and decision.get("behavior") == "allow" and gate.action != "missing-effect":
        target = gate.final_path()
        await asyncio.to_thread(target.write_text, EDITED if gate.action == "edit" else ORIGINAL, encoding="utf-8")
    return {"received": bool(receipt.content), "text": text, "is_error": receipt.isError}


def gate_report(state: Evidence, gate: GateState, receipt: dict[str, Any] | None,
                process_receipts: list[dict[str, Any]], closed: bool) -> dict[str, Any]:
    base = state.report()
    selected = state.selected
    expected = EDITED if selected["action"] == "edit" else ORIGINAL
    target = gate.final_path()
    actual = target.read_text(encoding="utf-8") if target.is_file() else None
    original = gate.expected_path().read_text(encoding="utf-8") if gate.expected_path().is_file() else None
    gate_ok = bool(len(gate.calls) == len(gate.decisions) == len(process_receipts) == 1
                   and gate.calls[0]["run_id"] == gate.run_id
                   and gate.decisions[0]["gate_id"] == gate.gate_id
                   and process_receipts[0]["run_id"] == gate.run_id
                   and process_receipts[0]["gate_id"] == gate.gate_id)
    effect_ok = bool(actual == expected and (selected["action"] != "edit" or original is None))
    if state.source == SOURCE_LIVE:
        calls = [call for call in state.calls if call["name"] == "Write"]
        paired = len(calls) == 1 and sum(item["id"] == calls[0]["id"] and not item["is_error"] for item in state.results) == 1
        sdk_ok = bool(base["experiment_passed"] and paired and state.initialized
                      and state.terminals and state.terminals[-1].get("session_id") == state.initialized[-1].get("session_id"))
    else:
        sdk_ok = False
        paired = False
    allowed = selected["action"] in {"allow", "edit", "remember"}
    prepared_ok = bool(receipt and receipt["received"] and receipt["is_error"] is False)
    passed = bool(allowed and gate_ok and effect_ok and closed
                  and (sdk_ok if state.source == SOURCE_LIVE else prepared_ok))
    if selected.get("scenario") == "missing-evidence":
        passed = False
    if selected.get("scenario") == "wrong-identity":
        passed = False
    return {**base, "selected": selected, "gate_calls": gate.calls, "gate_decisions": gate.decisions,
            "process_receipts": process_receipts, "prepared_client_receipt": receipt,
            "sdk_write_paired": paired, "gate_correlated": gate_ok, "file_effect_verified": effect_ok,
            "file_inventory": {"original": original, "edited": actual if selected["action"] == "edit" else None},
            "connection_closed": closed, "experiment_passed": passed,
            "check_scope": "An owned stdio Python MCP process and host gate must agree on run, gate and Write input. Approval also requires a successful parent result and fresh disk contents. Prepared mode uses a real MCP round trip with authored SDK fixtures; live mode checks SDK permission routing. Node is unavailable in this Python workspace."}


async def execute_gate(root: Path, request: RunRequest, settings: Settings, emit: Any,
                       config_root: Path | None = None) -> dict[str, Any]:
    from agent_lab.sdk import isolated_env, message_data, require_live_access, resolve_cli_path

    request = lesson_request(37, request)
    root = await asyncio.to_thread(root.resolve)
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    selected = {**request.lesson_options, "scenario": request.scenario}
    gate = GateState(root, root.parent.name, secrets.token_hex(12), secrets.token_urlsafe(24), selected["action"])
    ACTIVE_GATES[gate.run_id] = gate
    log = root / "gate-process-log.jsonl"
    config_root = config_root or root.parent / "config"
    state = Evidence(37, gate.run_id, root, selected,
                     SOURCE_LIVE if request.mode == "live" else "actual local MCP round trip and explicitly recorded SDK fixtures",
                     request.max_turns, request.max_budget_usd)
    receipt: dict[str, Any] | None = None
    closed = False
    try:
        async with EmbeddedServer(bridge_app(gate)).running() as base:
            config = gate_config(gate, base, log)
            await emit(Event(kind="options", data={"lesson_id": 37, "permission_prompt_tool_name": GATE_TOOL,
                                                   "gate_process": {"command": "<owned Python>", "args": config["args"]}}))
            if request.mode == "live":
                require_live_access(settings)

                async def guard(data: Any, call_id: str | None, context: Any) -> dict[str, Any]:
                    valid = data.get("tool_name") == "Write" and data.get("tool_input") == {
                        "file_path": str(gate.expected_path()), "content": ORIGINAL}
                    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                   "permissionDecision": "ask" if valid else "deny",
                                                   "permissionDecisionReason": "Owned Write must pass the gate."}}

                options = ClaudeAgentOptions(
                    cwd=str(root), model=settings.model, cli_path=resolve_cli_path(settings),
                    tools=["Write"], allowed_tools=[], permission_mode="default",
                    permission_prompt_tool_name=GATE_TOOL, mcp_servers={"gate": cast(Any, config)},
                    hooks={"PreToolUse": [HookMatcher(matcher="Write", hooks=[cast(Any, guard)])]},
                    setting_sources=[], strict_mcp_config=True, env=isolated_env(config_root.resolve()),
                    max_turns=request.max_turns, max_budget_usd=request.max_budget_usd,
                    system_prompt="Use Write exactly once to write the requested fixed file and exact content. Do not use another tool or retry after refusal. Then reply Done.",
                )
                state.configured = {"tools": options.tools, "permission_prompt_tool_name": GATE_TOOL,
                                    "mcp_server": "gate", "hook": "owned Write"}
                await asyncio.to_thread(config_root.mkdir, parents=True, exist_ok=True)
                client = ClaudeSDKClient(options=options)
                try:
                    await client.connect()
                    await client.query(f"Write {ORIGINAL.strip()} to {gate.expected_path()} using Write exactly once.")
                    async for message in client.receive_response():
                        data = message_data(message)
                        event = Event(kind="result" if data["message_class"] == "ResultMessage" else "message", data=data)
                        state.observe(event)
                        await emit(event)
                finally:
                    await client.disconnect()
            else:
                receipt = await prepared_round_trip(gate, config, request.scenario)
                state.initialized = [{"session_id": "prepared-fixture"}]
                state.terminals = [{"session_id": "prepared-fixture", "subtype": "success", "is_error": False}]
    finally:
        closed = True
        ACTIVE_GATES.pop(gate.run_id, None)
    selected["action"] = gate.action
    process_receipts = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    report = gate_report(state, gate, receipt, process_receipts, closed)
    report["scenario"] = request.scenario
    report["expected_check"] = "passed" if report["experiment_passed"] else "needs-review"
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 37, "result": proof}))
    return proof


async def local_gate(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_gate(root, request.model_copy(update={"mode": "offline"}), Settings(), ignore)
