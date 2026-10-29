"""Completed Agent Evaluation Studio contracts for all seven stages.

Check your work:      uv run agent-lab studio check
Compare a reference:  uv run agent-lab studio check --reference   (never marks your work done)

Stages M08-M14 are numbered 1-7 here. Each prompt is in
mini_projects/evaluation_studio/prompts/. The Evaluation Studio page
(http://127.0.0.1:8080/studio) runs this file, so every stage you finish unlocks a feature.
"""

import ipaddress
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

# All contracts are implemented; `agent-lab studio check` verifies every stage.
STAGE = 7
DEPTHS = {
    "brief": "Give a compact explanation and one check.",
    "guided": "Explain in clear steps, with a small example when useful.",
    "worked": "Teach from first principles with a minimal code example, then how to verify it.",
}
TURN_CHOICES = (1, 3, 5, 8, 12)
BUDGET_CHOICES = (0.05, 0.15, 0.3, 0.5)
DOCS_MCP_URL = "https://code.claude.com/docs/mcp"
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def summarize_run(messages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Stage 2 (M09): turn SDK messages into an honest answer and timeline.

    Messages are dicts: {"type": "assistant", "content": [blocks], "parent_tool_use_id"},
    {"type": "user", "content": [tool_result blocks]}, {"type": "system", "subtype": "init",
    "mcp_servers": [...]}, {"type": "result", "subtype", "is_error", "num_turns",
    "total_cost_usd"} and {"type": "stream_error"} when the iterator raised.

    Return {"answer", "events": [{"label", "detail"}], "subtype", "is_error", "turns",
    "cost_usd", "mcp_tool_calls", "specialist_calls"}. Collect top-level text only; the run
    is an error unless the final result has subtype "success", is_error false, and no stream
    error followed. Without a result, the subtype is "sdk_stream_error".
    """
    answer, events = "", []
    final: Mapping[str, Any] | None = None
    stream_failed = False
    mcp_calls = specialist_calls = 0
    for message in messages:
        kind = message.get("type")
        if kind == "system" and message.get("subtype") == "init":
            for server in message.get("mcp_servers") or []:
                events.append(("MCP connection", f"{server.get('name')}: {server.get('status')}"))
        elif kind == "assistant":
            for block in message.get("content") or []:
                if block.get("type") == "text" and not message.get("parent_tool_use_id"):
                    answer += block.get("text", "")
                elif block.get("type") == "tool_use":
                    name = str(block.get("name", ""))
                    mcp_calls += name.startswith("mcp__")
                    agent = (block.get("input") or {}).get("subagent_type")
                    specialist_calls += name in {"Agent", "Task"} and bool(agent)
                    events.append(("Tool requested", f"Specialist: {agent}" if agent else name))
        elif kind == "user":
            for block in message.get("content") or []:
                if block.get("type") == "tool_result":
                    failed = block.get("is_error")
                    events.append(("Tool result", "error" if failed else "returned a result"))
        elif kind == "result":
            final = message
        elif kind == "stream_error":
            stream_failed = True
            events.append(
                ("SDK stream stopped", "after a final result" if final else "before a final result")
            )
    subtype = str(final.get("subtype")) if final else "sdk_stream_error"
    is_error = stream_failed or final is None or bool(final.get("is_error")) or subtype != "success"
    events.append(("Assistant text received", f"{len(answer)} characters"))
    events.append(
        ("SDK result", f"{subtype} - {'incomplete or failed' if is_error else 'completed'}")
    )
    return {
        "answer": answer or "No assistant text was returned. Inspect the result and timeline.",
        "events": [{"label": label, "detail": detail} for label, detail in events],
        "subtype": subtype,
        "is_error": is_error,
        "turns": final.get("num_turns") if final else None,
        "cost_usd": final.get("total_cost_usd") if final else None,
        "mcp_tool_calls": mcp_calls,
        "specialist_calls": specialist_calls,
    }


def build_system_prompt(variant: object, depth: object, mcp_mode: object = "none") -> str:
    """Stage 3 (M10): join the variant (1-2000 characters), the DEPTHS instruction, a source
    rule for mcp_mode (none, docs or custom), and a rule against claiming unseen tool calls.
    Raise ValueError for anything invalid."""
    if not isinstance(variant, str) or not variant.strip() or len(variant) > 2000:
        raise ValueError("The instruction variant must be 1 to 2000 characters.")
    if not isinstance(depth, str) or depth not in DEPTHS:
        raise ValueError(f"Depth must be one of {', '.join(DEPTHS)}.")
    if not isinstance(mcp_mode, str) or mcp_mode not in {"none", "docs", "custom"}:
        raise ValueError("Source mode must be none, docs or custom.")
    source = (
        "No external source is configured. Be explicit about uncertainty."
        if mcp_mode == "none"
        else "Use the connected MCP source when relevant and say what was retrieved; if no "
        "tool is called, say the answer is unverified by that source."
    )
    return "\n".join(
        [
            variant.strip(),
            DEPTHS[str(depth)],
            source,
            "Do not claim a tool was called unless its result is visible in this run.",
        ]
    )


def parse_run_options(
    depth: object,
    max_turns: object,
    max_budget_usd: object,
    specialist_review: object = False,
    question: object = "",
) -> dict[str, Any]:
    """Stage 4 (M11): accept only DEPTHS, TURN_CHOICES and BUDGET_CHOICES (no booleans).
    Specialist review needs at least 5 turns and 0.15 USD. The question is at most 2000
    characters. Return {"depth", "max_turns", "max_budget_usd", "specialist_review",
    "question"} with the question trimmed."""
    if not isinstance(depth, str) or depth not in DEPTHS:
        raise ValueError("Choose a valid answer depth.")
    if (
        not isinstance(max_turns, int)
        or isinstance(max_turns, bool)
        or max_turns not in TURN_CHOICES
    ):
        raise ValueError(f"Turns must be one of {TURN_CHOICES}.")
    if (
        not isinstance(max_budget_usd, int | float)
        or isinstance(max_budget_usd, bool)
        or max_budget_usd not in BUDGET_CHOICES
    ):
        raise ValueError(f"The budget threshold must be one of {BUDGET_CHOICES} USD.")
    if not isinstance(specialist_review, bool):
        raise ValueError("Specialist review must be true or false.")
    if specialist_review and (max_turns < 5 or max_budget_usd < 0.15):
        raise ValueError("Specialist review needs at least 5 turns and a 0.15 USD threshold.")
    if not isinstance(question, str) or len(question) > 2000:
        raise ValueError("Keep the question under 2000 characters.")
    return {
        "depth": depth,
        "max_turns": max_turns,
        "max_budget_usd": max_budget_usd,
        "specialist_review": specialist_review,
        "question": question.strip(),
    }


def _public_host(host: str) -> bool:
    host = host.rstrip(".")  # "localhost." is still localhost
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    # 2130706433, 0x7f.0.0.1 and 127.1 are not domains: URL parsers turn them into 127.0.0.1.
    return not all(re.fullmatch(r"0x[0-9a-f]*|[0-9]+", label) for label in host.split("."))



def mcp_settings(
    mode: object, name: object = "", url: object = "", tools: object = ""
) -> dict[str, Any]:
    """Stage 5 (M12): return {"mcp_servers", "allowed_tools", "source_label"}.

    none: no servers. docs: the official docs server at DOCS_MCP_URL with
    "mcp__claude_docs__*". custom: a short name (letter first, not claude_docs), a public
    HTTPS URL without credentials, query or fragment (no localhost or private addresses),
    and one to five exact tool names, allowed as mcp__<name>__<tool>. Also refuse hosts that
    URL parsers turn into loopback: a trailing dot ("localhost."), *.localhost, and numeric
    forms such as 2130706433, 0x7f.0.0.1 or 127.1.
    """
    if mode == "none":
        return {"mcp_servers": {}, "allowed_tools": [], "source_label": "No external source"}
    if mode == "docs":
        return {
            "mcp_servers": {"claude_docs": {"type": "http", "url": DOCS_MCP_URL}},
            "allowed_tools": ["mcp__claude_docs__*"],
            "source_label": "Official Claude documentation MCP",
        }
    if mode != "custom":
        raise ValueError("Source mode must be none, docs or custom.")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name == "claude_docs":
        raise ValueError("Use a short server name that starts with a letter.")
    if not isinstance(url, str) or len(url) > 500:
        raise ValueError("Enter a valid HTTPS MCP URL.")
    parsed = urlparse(url)
    port = parsed.port  # Also validate an explicitly supplied port.
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
        or parsed.query
        or parsed.fragment
        or not _public_host(parsed.hostname or "")
    ):
        raise ValueError("Use a public HTTPS URL without credentials, query tokens or fragments.")
    if not isinstance(tools, str):
        raise ValueError("List the exact MCP tools to allow.")
    names = list(dict.fromkeys(part.strip() for part in tools.split(",") if part.strip()))
    if not 1 <= len(names) <= 5 or not all(TOOL.fullmatch(tool) for tool in names):
        raise ValueError("List one to five exact MCP tool names, separated by commas.")
    return {
        "mcp_servers": {name: {"type": "http", "url": url}},
        "allowed_tools": [f"mcp__{name}__{tool}" for tool in names],
        "source_label": f"Custom MCP: {name} ({parsed.hostname})",
    }


def review_record(run: Mapping[str, Any], marks: object, note: object = "") -> dict[str, Any]:
    """Stage 6 (M13): one boolean mark per run["criteria"] and a note under 1000 characters.
    Return {"run_id", "case_id", "kind", "subtype", "criteria", "passed", "note"}; kind is
    "live SDK run" or "prepared fixture", and passed needs every mark and a success result."""
    criteria = run.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("The run has no review criteria.")
    if not isinstance(marks, list) or len(marks) != len(criteria):
        raise ValueError(f"Mark each of the {len(criteria)} criteria.")
    if not all(isinstance(mark, bool) for mark in marks):
        raise ValueError("Each criterion mark must be true or false.")
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError("Keep the note under 1000 characters.")
    if run.get("run_mode") not in {"prepared", "live"}:
        raise ValueError("The run mode must be prepared or live.")
    return {
        "run_id": run.get("id"),
        "case_id": run.get("case_id"),
        "kind": "live SDK run" if run["run_mode"] == "live" else "prepared fixture",
        "subtype": run.get("subtype"),
        "criteria": [
            {"text": text, "met": mark} for text, mark in zip(criteria, marks, strict=True)
        ],
        "passed": all(marks) and run.get("subtype") == "success" and not run.get("is_error", False),
        "note": note.strip(),
    }


def export_evidence(records: Iterable[Mapping[str, Any]]) -> str:
    """Stage 6 (M13): a Markdown table of reviewed runs that says prepared fixtures are not
    live validations."""
    rows = list(records)
    lines = [
        "# Evaluation evidence",
        "",
        f"{len(rows)} reviewed runs. Prepared fixtures are not live model validations.",
        "",
        "| Case | Kind | Result | Review | Note |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        note = str(row.get("note", "")).replace("|", "/").replace("\n", " ")
        review = "passed" if row.get("passed") else "needs work"
        lines.append(
            f"| {row.get('case_id')} | {row.get('kind')} | {row.get('subtype')} | {review} | {note} |"
        )
    return "\n".join(lines) + "\n"


def release_decision(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
    explanations: Mapping[str, str],
) -> dict[str, Any]:
    """Stage 7 (M14): compare suites keyed by case id with {"subtype", "passed"} outcomes.

    A regression is success -> anything else, or passed True -> False. Return
    {"regressions", "missing", "unexplained", "ready"}: ready only when no baseline case is
    missing and every regression has a nonempty explanation.
    """
    missing = sorted(set(baseline) - set(candidate))
    regressions = []
    for case_id, before in baseline.items():
        after = candidate.get(case_id)
        if after is None:
            continue
        got_worse = before.get("subtype") == "success" and after.get("subtype") != "success"
        review_dropped = before.get("passed") is True and after.get("passed") is False
        if got_worse or review_dropped:
            regressions.append(case_id)
    unexplained = [
        case_id for case_id in regressions if not str(explanations.get(case_id, "")).strip()
    ]
    return {
        "regressions": regressions,
        "missing": missing,
        "unexplained": unexplained,
        "ready": not missing and not unexplained,
    }
