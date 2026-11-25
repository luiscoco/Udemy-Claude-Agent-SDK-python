"""Bounded, owned native SDK observations for Lesson 59."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from pathlib import Path
from typing import Any, cast

from agent_lab.headless_native import native_environment, private_key
from agent_lab.routing_lab import (
    BY_ID,
    DEEP,
    LIGHT,
    MODELS,
    RoutingInput,
    check_suite,
    grade_answer,
    metrics,
    needs_escalation,
    rule_tier,
)

ANSWER_SCHEMA = {"type": "object", "properties": {
    "answer": {"type": "string", "minLength": 1, "maxLength": 200},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["answer", "confidence"], "additionalProperties": False}
CLASSIFIER_SCHEMA = {"type": "object", "properties": {
    "tier": {"type": "string", "enum": ["light", "standard", "deep"]}},
    "required": ["tier"], "additionalProperties": False}


def valid_output(value: Any, classifier: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    if classifier:
        return set(value) == {"tier"} and value["tier"] in MODELS
    if set(value) != {"answer", "confidence"}:
        return False
    answer, confidence = value["answer"], value["confidence"]
    return (isinstance(answer, str) and 1 <= len(answer.strip()) <= 200
            and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            and math.isfinite(confidence) and 0 <= confidence <= 1)


def usage_snapshot(result: Any) -> dict[str, Any]:
    """Keep raw model names and require a coherent reported total."""
    cost = result.get("total_cost_usd") if isinstance(result, dict) else getattr(result, "total_cost_usd", None)
    raw = result.get("model_usage") if isinstance(result, dict) else getattr(result, "model_usage", None)
    models = []
    valid = isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0
    if not isinstance(raw, dict) or not raw:
        valid = False
    else:
        for name, row in raw.items():
            if not isinstance(row, dict):
                valid = False
                continue
            values = {"inputTokens": row.get("inputTokens"),
                      "outputTokens": row.get("outputTokens"),
                      "cacheReadTokens": row.get("cacheReadInputTokens"),
                      "cacheCreationTokens": row.get("cacheCreationInputTokens"),
                      "costUsd": row.get("costUSD")}
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
                   for v in values.values()):
                valid = False
            models.append({"rawModel": name, "canonicalModel": row.get("canonicalModel"),
                           **values})
    if valid and abs(sum(row["costUsd"] for row in models) - cost) > 1e-6:
        valid = False
    return {"valid": valid, "costBasis": "sdk-query-pipeline-estimate", "cumulativeCostUsd": cost,
            "models": models}


def assess_special(report: dict[str, Any], budget: float) -> dict[str, Any]:
    """Recompute fixed special evidence; never awards the routing-suite criterion."""
    errors: list[str] = []
    kind = report.get("kind")
    rows = report.get("rows", [])
    expected_count = 1 if kind == "delegate" else 3 if kind == "resolution" else 0
    if (report.get("mode") != "live" or report.get("source") != "native-sdk-special"
            or report.get("status") != "success" or report.get("errors") or
            len(rows) != expected_count):
        errors.append("Complete fixed native special report required")
    if kind == "resolution" and [row.get("variant") for row in rows] != [
            "alias", "remapped-alias", "explicit-id"]:
        errors.append("All ordered alias variants required")
    queries: set[str] = set()
    results: set[str] = set()
    cost = 0.0
    for row in rows:
        task_id = "lineup" if kind == "delegate" else "invoice"
        output = row.get("output")
        if (row.get("status") != "success" or not isinstance(output, dict) or
                not valid_output(output) or
                not grade_answer(task_id, output["answer"])["accepted"] or
                row.get("grade") != grade_answer(task_id, output["answer"])):
            errors.append("Independent answer grade must pass")
        history = row.get("history", [])
        if len(history) != 1:
            errors.append("One terminal per fixed query required")
            continue
        call = history[0]
        observed = usage_snapshot(call.get("rawTerminal"))
        billing = call.get("billing", {})
        if (call.get("source") != "native-sdk" or call.get("status") != "success" or
                call.get("subtype") != "success" or call.get("isError") or
                not call.get("closed") or not observed["valid"] or observed != billing or
                call.get("output") != output):
            errors.append("Closed native terminal and recomputed usage required")
        try:
            query_id = str(uuid.UUID(call.get("queryId")))
            result_id = str(uuid.UUID(call.get("resultId")))
            session_id = str(uuid.UUID(call.get("sessionId")))
        except (TypeError, ValueError, AttributeError):
            errors.append("Valid query/result/session identities required")
            continue
        if query_id in queries or result_id in results:
            errors.append("Distinct query and result identities required")
        queries.add(query_id)
        results.add(result_id)
        if not call.get("toolEvidence", {}).get("inits") or any(
                init.get("sessionId") != session_id for init in call["toolEvidence"]["inits"]):
            errors.append("Stable correlated native session required")
        amount = billing.get("cumulativeCostUsd")
        if not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 <= amount <= .100001:
            errors.append("Known bounded query cost required")
        else:
            cost += amount
        if kind == "resolution" and row.get("variant") != "alias" and not any(
                model.get("rawModel") == MODELS["standard"] or
                model.get("canonicalModel") == MODELS["standard"]
                for model in billing.get("models", [])):
            errors.append("Remapped and explicit variants must observe configured model")
        if kind == "delegate":
            d = row.get("delegation", {})
            if not d.get("observed") or not any(
                    a.get("admitted") and a.get("tool") in {"Agent", "Task"} and
                    any(c.get("callId") == a.get("callId") and c.get("tool") == a.get("tool")
                        for c in d.get("calls", [])) and
                    any(r.get("callId") == a.get("callId") and not r.get("isError")
                        for r in d.get("results", [])) for a in d.get("admissions", [])):
                errors.append("Matched admitted expert call/result required")
    if (report.get("sdkQueries") != len(queries) or
            not isinstance(report.get("reportedSdkUsd"), (int, float)) or
            abs(cost - report["reportedSdkUsd"]) > 1e-6 or cost > budget):
        errors.append("Known cumulative special cost must match budget")
    return {"passed": not errors, "errors": errors, "criterionAwarded": False}


async def _query(owned: Path, task_id: str, stage: str, tier: str,
                 *, review: bool = False, always_review: bool = False,
                 effort: str | None = None,
                 abort: asyncio.Event | None = None,
                 model_override: str | None = None,
                 default_sonnet_override: str | None = None) -> list[dict[str, Any]]:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
    )

    query_id = str(uuid.uuid4())
    folder = owned / query_id
    folder.mkdir(parents=True, exist_ok=False)
    home = folder / "config"
    home.mkdir()
    env = native_environment(home, private_key())
    env["CLAUDE_CODE_MAX_RETRIES"] = "0"
    if default_sonnet_override:
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = default_sonnet_override
    classifier = stage == "classifier"
    schema = CLASSIFIER_SCHEMA if classifier else ANSWER_SCHEMA
    admissions: list[dict[str, Any]] = []

    async def hook(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        allowed = bool(call_id and data.get("tool_name") == "StructuredOutput"
                       and valid_output(data.get("tool_input"), classifier))
        admissions.append({"callId": call_id, "tool": data.get("tool_name"), "admitted": allowed})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "ask" if allowed else "deny",
                "permissionDecisionReason": "Only the selected structured schema is permitted"}}

    async def callback(name: str, value: dict[str, Any], context: Any) -> Any:
        allowed = bool(context.tool_use_id and name == "StructuredOutput"
                       and valid_output(value, classifier))
        return PermissionResultAllow() if allowed else PermissionResultDeny(message="Outside selected schema")

    kwargs: dict[str, Any] = {}
    if effort:
        kwargs["effort"] = effort
    requested = model_override or MODELS[tier]
    options = ClaudeAgentOptions(cwd=folder, env=env, model=requested, tools=[],
                                 allowed_tools=[], mcp_servers={}, strict_mcp_config=True,
                                 setting_sources=[], continue_conversation=False,
                                 extra_args={"no-session-persistence": None},
                                 max_turns=4, max_budget_usd=0.10,
                                 output_format={"type": "json_schema", "schema": schema},
                                 hooks={"PreToolUse": [HookMatcher(hooks=[cast(Any, hook)])]},
                                 can_use_tool=callback, **kwargs)
    prompt = (f"Classify the complexity tier of this fixed task as light, standard or deep. "
              f"Return only the schema object. Task: {BY_ID[task_id].prompt}"
              if classifier else
              f"Solve this fixed task. Return only the schema object with the exact answer and your confidence. "
              f"Task: {BY_ID[task_id].prompt}")
    history: list[dict[str, Any]] = []
    inits: list[str] = []
    async with asyncio.timeout(90):
        async with ClaudeSDKClient(options=options) as client:
            async def turn(text: str, turn_stage: str, requested_model: str) -> dict[str, Any]:
                start = time.perf_counter()
                await client.query(text)
                result = None
                async for message in client.receive_response():
                    if abort and abort.is_set():
                        raise asyncio.CancelledError
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        inits.append(message.data.get("session_id", ""))
                        if len(inits) > 8 or len(set(inits)) != 1:
                            raise ValueError("Unstable native session identity")
                    elif isinstance(message, ResultMessage):
                        if result is not None:
                            raise ValueError("Unexpected extra terminal")
                        result = message
                    elif isinstance(message, AssistantMessage):
                        pass
                elapsed = round((time.perf_counter() - start) * 1000, 3)
                if result is None:
                    return {"queryId": query_id, "stage": turn_stage, "status": "no-result",
                            "closed": False, "durationMs": elapsed, "source": "native-sdk"}
                billing = usage_snapshot(result)
                output = result.structured_output if (result.subtype == "success" and not result.is_error) else None
                status = ("success" if output is not None and valid_output(output, classifier)
                          and billing["valid"] and inits and result.session_id == inits[0]
                          and result.uuid else "failed")
                return {"queryId": query_id, "sessionId": result.session_id,
                        "resultId": result.uuid, "stage": turn_stage, "source": "native-sdk",
                        "status": status, "closed": True, "subtype": result.subtype,
                        "isError": result.is_error, "model": requested_model, "effort": effort,
                        "output": output, "durationMs": elapsed, "billing": billing,
                        "rawTerminal": {"total_cost_usd": result.total_cost_usd,
                                        "model_usage": result.model_usage},
                        "toolEvidence": {"inits": [{"sessionId": x} for x in inits],
                                         "admissions": admissions.copy()}}

            first = await turn(prompt, stage, requested)
            history.append(first)
            if first["status"] != "success":
                return history
            if review:
                should_switch = always_review or needs_escalation(task_id, first["output"])
                if should_switch:
                    await client.set_model(DEEP)
                    next_prompt = (f"Review this fixed task independently and return the answer schema. "
                                   f"Task: {BY_ID[task_id].prompt} First draft: {first['output']['answer']}")
                    second = await turn(next_prompt, "review", DEEP)
                    second["modelSwitch"] = {"source": "native-setModel-control",
                                             "acknowledged": True, "model": DEEP}
                    history.append(second)
    return history


async def live(selected: RoutingInput, root: Path, run_id: str | None = None,
               abort: asyncio.Event | None = None) -> dict[str, Any]:
    if selected.mode != "live" or not selected.consent:
        raise PermissionError("Fresh native consent required")
    strategy = selected.strategies[0]
    reservation = len(selected.taskIds) * (2 if strategy == "classifier" else 1) * 0.10
    if selected.budget + 1e-9 < reservation:
        raise ValueError("Budget is below the bounded query reservation")
    run_id = run_id or str(uuid.uuid4())
    owned = root / "lesson-59" / run_id
    owned.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    interrupted = False
    try:
        async with asyncio.timeout(240):
            for task_id in selected.taskIds:
                if abort and abort.is_set():
                    raise asyncio.CancelledError
                if strategy == "classifier":
                    history = await _query(owned, task_id, "classifier", "light", abort=abort)
                    if history[-1]["status"] != "success":
                        errors.append(f"{task_id}: classifier failed")
                        break
                    tier = history[-1]["output"]["tier"]
                    history.extend(await _query(owned, task_id, "solve", tier, abort=abort))
                else:
                    tier = ("light" if strategy in {"light", "cascade", "review"} else
                            rule_tier(task_id) if strategy == "rules" else
                            "deep" if strategy == "deep-low" else strategy)
                    history = await _query(owned, task_id, "solve",
                                           tier, review=strategy in {"cascade", "review"},
                                           always_review=strategy == "review",
                                           effort="low" if strategy == "deep-low" else None,
                                           abort=abort)
                final = history[-1]
                output = final.get("output")
                row = {"taskId": task_id, "strategy": strategy,
                       "intendedTier": BY_ID[task_id].tier, "selectedTier": tier,
                       "history": history, "status": final["status"], "output": output,
                       "grade": grade_answer(task_id, output["answer"]) if isinstance(output, dict) and valid_output(output) else None,
                       "escalated": any(c["stage"] == "review" for c in history),
                       "durationMs": sum(c["durationMs"] for c in history)}
                rows.append(row)
                if row["status"] != "success":
                    errors.append(f"{task_id}: native execution failed")
                    break
    except (asyncio.CancelledError, TimeoutError) as exc:
        interrupted = True
        errors.append(type(exc).__name__)
    except Exception as exc:
        errors.append(f"Native {type(exc).__name__}")
    by_query = {call["queryId"]: call for row in rows for call in row["history"]}
    known = [call.get("billing", {}).get("cumulativeCostUsd") for call in by_query.values()]
    reported = round(sum(known), 8) if all(isinstance(x, (int, float)) for x in known) else None
    report = {"lesson": 59, "runId": run_id, "config": {**selected.model_dump(), "runId": run_id},
              "mode": "live", "source": "native-sdk", "status": "success" if not errors else "failed",
              "rows": rows, "metrics": {strategy: metrics(rows, "sdk-query-pipeline-estimate")} if rows else {},
              "errors": errors, "interrupted": interrupted, "sdkQueries": len(by_query),
              "reportedSdkUsd": reported}
    report["check"] = check_suite(report, selected)
    return report


async def native_models(root: Path, run_id: str | None = None) -> dict[str, Any]:
    """Read installed CLI initialization metadata without sending a user turn."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    run_id = run_id or str(uuid.uuid4())
    owned = root / "lesson-59" / "models" / run_id
    owned.mkdir(parents=True, exist_ok=False)
    home = owned / "config"
    home.mkdir()
    options = ClaudeAgentOptions(cwd=owned, env=native_environment(home, private_key()),
                                 model=MODELS["light"], tools=[], allowed_tools=[],
                                 mcp_servers={}, strict_mcp_config=True, setting_sources=[],
                                 extra_args={"no-session-persistence": None},
                                 max_turns=1, max_budget_usd=.10)
    async with asyncio.timeout(20):
        async with ClaudeSDKClient(options=options) as client:
            info = await client.get_server_info() or {}
    raw = info.get("models")
    valid = isinstance(raw, list) and bool(raw) and all(
        isinstance(row, dict) and isinstance(row.get("value"), str)
        and isinstance(row.get("resolvedModel"), str)
        and isinstance(row.get("displayName"), str) for row in raw)
    report = {"lesson": 59, "runId": run_id, "source": "native-sdk-initialization",
              "status": "success" if valid else "needs-review", "models": [
                  {"value": row["value"], "resolvedModel": row["resolvedModel"],
                   "displayName": row["displayName"],
                   "supportedEffortLevels": row.get("supportedEffortLevels", [])}
                  for row in (raw or [])] if valid else [], "modelInputTurns": 0,
              "note": "Installed CLI alias resolution, not account entitlement or a billing guarantee."}
    return report


async def resolution(root: Path, *, mode: str, consent: bool, budget: float,
                     run_id: str | None = None) -> dict[str, Any]:
    """Three fixed invoice alias observations, separate from suite acceptance."""
    from agent_lab.routing_lab import prepared_task

    if mode not in {"prepared", "live"} or not .3 <= budget <= 1:
        raise ValueError("Invalid special probe configuration")
    if mode == "live" and not consent:
        raise PermissionError("Fresh paid consent required")
    run_id = run_id or str(uuid.uuid4())
    rows: list[dict[str, Any]] = []
    variants = (("alias", "sonnet", None),
                ("remapped-alias", "sonnet", MODELS["standard"]),
                ("explicit-id", MODELS["standard"], None))
    owned = root / "lesson-59" / "resolution" / run_id
    owned.mkdir(parents=True, exist_ok=False)
    for variant, model, override in variants:
        if mode == "prepared":
            row = prepared_task("invoice", "standard")
            row["history"][0]["model"] = model
            row["history"][0]["source"] = "scripted-special-fixture"
        else:
            try:
                history = await _query(owned, "invoice", "solve", "standard",
                                       model_override=model,
                                       default_sonnet_override=override)
            except Exception as exc:
                history = []
                rows.append({"variant": variant, "status": "failed",
                             "error": type(exc).__name__, "history": []})
                break
            final = history[-1]
            output = final.get("output")
            row = {"taskId": "invoice", "history": history, "status": final["status"],
                   "output": output, "grade": grade_answer("invoice", output["answer"])
                   if isinstance(output, dict) and valid_output(output) else None}
        row["variant"] = variant
        rows.append(row)
        if row["status"] != "success":
            break
    by_query = {call["queryId"]: call for row in rows for call in row["history"]}
    costs = [call.get("billing", {}).get("cumulativeCostUsd") for call in by_query.values()]
    known = round(sum(costs), 8) if all(isinstance(cost, (int, float)) for cost in costs) else None
    accepted = (len(rows) == 3 and all(row["status"] == "success" and
               row.get("grade", {}).get("accepted") for row in rows))
    if mode == "live" and accepted:
        accepted = all(any(model.get("rawModel") == MODELS["standard"] or
                               model.get("canonicalModel") == MODELS["standard"]
                               for model in row["history"][-1]["billing"]["models"])
                       for row in rows[1:])
    report: dict[str, Any] = {"lesson": 59, "runId": run_id, "kind": "resolution", "mode": mode,
            "source": "scripted-special-fixture" if mode == "prepared" else "native-sdk-special",
            "status": "success" if accepted and (mode == "prepared" or known is not None and known <= budget) else "needs-review",
            "rows": rows, "sdkQueries": len(by_query) if mode == "live" else 0,
            "reportedSdkUsd": known if mode == "live" else 0,
            "criterionAwarded": False,
            "note": "Alias observations do not award the routing-suite check or guarantee account entitlement."}
    report["check"] = assess_special(report, budget) if mode == "live" else {"passed": False,
                                                "criterionAwarded": False,
                                                "reason": "Prepared illustration only"}
    if mode == "live" and not report["check"]["passed"]:
        report["status"] = "needs-review"
    return report


async def delegate(root: Path, *, mode: str, consent: bool, budget: float,
                   run_id: str | None = None) -> dict[str, Any]:
    """Observe one fixed named expert spawn with correlated native tool evidence."""
    from claude_agent_sdk import (
        AgentDefinition,
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        SystemMessage,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    from agent_lab.routing_lab import prepared_task

    if mode not in {"prepared", "live"} or not .3 <= budget <= 1:
        raise ValueError("Invalid special probe configuration")
    if mode == "live" and not consent:
        raise PermissionError("Fresh paid consent required")
    run_id = run_id or str(uuid.uuid4())
    if mode == "prepared":
        row = prepared_task("lineup", "deep")
        row["history"][0]["source"] = "scripted-special-fixture"
        row["delegation"] = {"observed": False, "source": "scripted-special-fixture",
                             "admissions": [], "calls": [], "results": []}
        return {"lesson": 59, "runId": run_id, "kind": "delegate", "mode": "prepared",
                "source": "scripted-special-fixture", "status": "success", "rows": [row],
                "sdkQueries": 0, "reportedSdkUsd": 0, "criterionAwarded": False,
                "note": "Scripted expert illustration; no native delegation observed."}
    owned = root / "lesson-59" / "delegate" / run_id
    owned.mkdir(parents=True, exist_ok=False)
    home = owned / "config"
    home.mkdir()
    env = native_environment(home, private_key())
    env["CLAUDE_CODE_MAX_RETRIES"] = "0"
    query_id = str(uuid.uuid4())
    advertised: set[str] = set()
    inits: list[str] = []
    admissions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    terminal = None

    async def hook(data: dict[str, Any], call_id: str | None, _context: Any) -> dict[str, Any]:
        name = data.get("tool_name")
        value = data.get("tool_input")
        if not isinstance(value, dict):
            value = {}
        agent_tool = (name in {"Agent", "Task"} and
                      bool(advertised.intersection({"Agent", "Task"})))
        prompt = value.get("prompt")
        restricted = any(value.get(key) for key in ("run_in_background", "resume", "isolation", "team_name"))
        allowed_agent = bool(call_id and agent_tool and value.get("subagent_type") == "expert"
                             and isinstance(prompt, str) and 0 < len(prompt) <= 3000
                             and not restricted and
                             sum(row["admitted"] for row in admissions if row["tool"] in {"Agent", "Task"}) < 2)
        allowed_schema = bool(call_id and name == "StructuredOutput" and valid_output(value))
        admitted = allowed_agent or allowed_schema
        admissions.append({"callId": call_id, "tool": name, "admitted": admitted,
                           "advertisedNameMatch": agent_tool, "requestedAgent": value.get("subagent_type"),
                           "promptLength": len(prompt) if isinstance(prompt, str) else None,
                           "restrictedFlags": restricted})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "permissionDecision": "ask" if admitted else "deny",
                "permissionDecisionReason": "Only bounded expert and selected answer schema are permitted"}}

    async def callback(name: str, value: dict[str, Any], context: Any) -> Any:
        admitted = any(row["callId"] == context.tool_use_id and row["tool"] == name and row["admitted"]
                       for row in admissions)
        return PermissionResultAllow() if admitted else PermissionResultDeny(message="Outside expert observation")

    options = ClaudeAgentOptions(cwd=owned, env=env, model=LIGHT,
                                 tools=["Agent"], allowed_tools=[],
                                 agents={"expert": AgentDefinition(
                                     description="Fixed lineup puzzle expert",
                                     prompt="Solve the supplied fixed lineup puzzle. No files, tools or delegation.",
                                     tools=[], model=DEEP)},
                                 mcp_servers={}, strict_mcp_config=True, setting_sources=[],
                                 extra_args={"no-session-persistence": None},
                                 output_format={"type": "json_schema", "schema": ANSWER_SCHEMA},
                                 max_turns=4, max_budget_usd=.10,
                                 hooks={"PreToolUse": [HookMatcher(hooks=[cast(Any, hook)])]},
                                 can_use_tool=callback)
    started = time.perf_counter()
    error = None
    try:
        async with asyncio.timeout(90):
            stream = query(prompt=("Use the advertised Agent or Task tool to ask expert to solve this "
                                   "fixed lineup puzzle in the foreground. Task: "
                                   f"{BY_ID['lineup'].prompt} Return the answer schema."),
                           options=options)
            async for message in stream:
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    inits.append(message.data.get("session_id", ""))
                    advertised.update(message.data.get("tools") or [])
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            calls.append({"callId": block.id, "tool": block.name})
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            results.append({"callId": block.tool_use_id,
                                            "isError": block.is_error is True})
                elif isinstance(message, ResultMessage):
                    if terminal is not None:
                        raise ValueError("Unexpected extra terminal")
                    terminal = message
    except Exception as exc:
        error = type(exc).__name__
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    billing = usage_snapshot(terminal) if terminal is not None else {"valid": False,
                                                                     "cumulativeCostUsd": None, "models": []}
    output = (terminal.structured_output if terminal is not None and terminal.subtype == "success"
              and not terminal.is_error else None)
    observed = any(row["admitted"] and row["tool"] in {"Agent", "Task"}
                   and any(call["callId"] == row["callId"] and call["tool"] == row["tool"] for call in calls)
                   and any(result["callId"] == row["callId"] and not result["isError"] for result in results)
                   for row in admissions)
    status = ("success" if error is None and terminal is not None and terminal.uuid and
              terminal.subtype == "success" and not terminal.is_error and
              isinstance(output, dict) and valid_output(output) and billing["valid"] and len(set(inits)) == 1 and
              inits[0] == terminal.session_id and observed and
              grade_answer("lineup", output["answer"])["accepted"] else "needs-review")
    call = {"queryId": query_id, "sessionId": terminal.session_id if terminal else None,
            "resultId": terminal.uuid if terminal else None, "stage": "delegate",
            "source": "native-sdk", "status": status, "closed": terminal is not None,
            "subtype": terminal.subtype if terminal else None,
            "isError": terminal.is_error if terminal else True, "model": LIGHT,
            "output": output, "durationMs": elapsed, "billing": billing,
            "rawTerminal": {"total_cost_usd": terminal.total_cost_usd,
                            "model_usage": terminal.model_usage} if terminal else None,
            "toolEvidence": {"inits": [{"sessionId": sid} for sid in inits],
                             "advertised": sorted(advertised)}}
    row = {"taskId": "lineup", "status": status, "output": output,
           "grade": grade_answer("lineup", output["answer"]) if isinstance(output, dict) and valid_output(output) else None,
           "history": [call], "delegation": {"observed": observed, "admissions": admissions,
                                               "calls": calls, "results": results}}
    report = {"lesson": 59, "runId": run_id, "kind": "delegate", "mode": "live",
            "source": "native-sdk-special", "status": status, "errors": [error] if error else [],
            "rows": [row], "sdkQueries": 1 if terminal is not None else 0,
            "reportedSdkUsd": billing["cumulativeCostUsd"], "criterionAwarded": False,
            "note": "A matching native tool result does not independently audit the expert's execution."}
    report["check"] = assess_special(report, budget)
    if not report["check"]["passed"]:
        report["status"] = "needs-review"
    return report
