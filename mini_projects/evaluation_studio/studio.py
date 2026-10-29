"""Your Agent Evaluation Studio contracts. Implement one stage at a time, then raise STAGE.

Check your work:      uv run agent-lab studio check
Compare a reference:  uv run agent-lab studio check --reference   (never marks your work done)

Stages M08-M14 are numbered 1-7 here. Each prompt is in
mini_projects/evaluation_studio/prompts/. The Evaluation Studio page
(http://127.0.0.1:8080/studio) runs this file, so every stage you finish unlocks a feature.
"""

from collections.abc import Iterable, Mapping
from typing import Any

# Raise this after each stage passes; tests for later stages are skipped until you do.
STAGE = 1
DEPTHS = {
    "brief": "Give a compact explanation and one check.",
    "guided": "Explain in clear steps, with a small example when useful.",
    "worked": "Teach from first principles with a minimal code example, then how to verify it.",
}
TURN_CHOICES = (1, 3, 5, 8, 12)
BUDGET_CHOICES = (0.05, 0.15, 0.3, 0.5)
DOCS_MCP_URL = "https://code.claude.com/docs/mcp"


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
    raise NotImplementedError("TODO M09: implement summarize_run")


def build_system_prompt(variant: object, depth: object, mcp_mode: object = "none") -> str:
    """Stage 3 (M10): join the variant (1-2000 characters), the DEPTHS instruction, a source
    rule for mcp_mode (none, docs or custom), and a rule against claiming unseen tool calls.
    Raise ValueError for anything invalid."""
    raise NotImplementedError("TODO M10: implement build_system_prompt")


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
    raise NotImplementedError("TODO M11: implement parse_run_options")


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
    raise NotImplementedError("TODO M12: implement mcp_settings")


def review_record(run: Mapping[str, Any], marks: object, note: object = "") -> dict[str, Any]:
    """Stage 6 (M13): one boolean mark per run["criteria"] and a note under 1000 characters.
    Return {"run_id", "case_id", "kind", "subtype", "criteria", "passed", "note"}; kind is
    "live SDK run" or "prepared fixture", and passed needs every mark and a success result."""
    raise NotImplementedError("TODO M13: implement review_record")


def export_evidence(records: Iterable[Mapping[str, Any]]) -> str:
    """Stage 6 (M13): a Markdown table of reviewed runs that says prepared fixtures are not
    live validations."""
    raise NotImplementedError("TODO M13: implement export_evidence")


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
    raise NotImplementedError("TODO M14: implement release_decision")
