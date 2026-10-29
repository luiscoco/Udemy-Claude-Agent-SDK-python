"""Cumulative stage checks for the Evaluation Studio (stages 2-7 are M09-M14)."""

import pytest


def test_stage_1_starts_at_a_valid_stage(studio):
    assert isinstance(studio.STAGE, int) and 1 <= studio.STAGE <= 7


# M09: an honest answer and timeline


def text(value, parent=None):
    return {
        "type": "assistant",
        "content": [{"type": "text", "text": value}],
        "parent_tool_use_id": parent,
    }


def result(subtype="success", is_error=False):
    return {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "num_turns": 2,
        "total_cost_usd": 0.01,
    }


@pytest.mark.stage(2)
def test_summarize_run_separates_answer_from_the_final_result(studio):
    summary = studio.summarize_run([text("Hello "), text("world"), result()])
    assert summary["answer"] == "Hello world"
    assert summary["subtype"] == "success" and summary["is_error"] is False
    assert summary["turns"] == 2 and summary["cost_usd"] == 0.01
    assert summary["events"][-1]["label"] == "SDK result"


@pytest.mark.stage(2)
def test_summarize_run_ignores_subagent_text_and_counts_tool_calls(studio):
    tool_use = {
        "type": "assistant",
        "content": [
            {"type": "tool_use", "name": "mcp__claude_docs__search", "input": {}},
            {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "source_reviewer"}},
        ],
    }
    summary = studio.summarize_run(
        [text("inner", parent="toolu_1"), tool_use, text("outer"), result()]
    )
    assert summary["answer"] == "outer"
    assert (summary["mcp_tool_calls"], summary["specialist_calls"]) == (1, 1)


@pytest.mark.stage(2)
@pytest.mark.parametrize(
    ("messages", "subtype"),
    [
        ([text("partial"), result("error_max_turns", True)], "error_max_turns"),
        # A limit result followed by an iterator error is still a failed run.
        (
            [text("partial"), result("error_max_turns", True), {"type": "stream_error"}],
            "error_max_turns",
        ),
        ([text("partial"), {"type": "stream_error"}], "sdk_stream_error"),
        ([text("fluent but unfinished")], "sdk_stream_error"),
        ([text("ok"), result("success"), {"type": "stream_error"}], "success"),
    ],
)
def test_summarize_run_never_turns_a_failure_into_success(studio, messages, subtype):
    summary = studio.summarize_run(messages)
    assert summary["subtype"] == subtype and summary["is_error"] is True


@pytest.mark.stage(2)
def test_summarize_run_reports_missing_text(studio):
    assert "No assistant text" in studio.summarize_run([result()])["answer"]


# M10: instruction variants


@pytest.mark.stage(3)
def test_build_system_prompt_combines_variant_depth_and_source_rules(studio):
    prompt = studio.build_system_prompt("  Answer briefly.  ", "worked", "docs")
    assert prompt.startswith("Answer briefly.")
    assert studio.DEPTHS["worked"] in prompt
    assert "MCP" in prompt and "tool was called" in prompt
    assert "uncertainty" in studio.build_system_prompt("Answer.", "brief")


@pytest.mark.stage(3)
@pytest.mark.parametrize(
    ("variant", "depth", "mode"),
    [
        ("", "brief", "none"),
        ("x" * 2001, "brief", "none"),
        ("ok", "deep", "none"),
        ("ok", "brief", "web"),
        (None, "brief", "none"),
    ],
)
def test_build_system_prompt_rejects_invalid_parts(studio, variant, depth, mode):
    with pytest.raises(ValueError):
        studio.build_system_prompt(variant, depth, mode)


# M11: bounded live runs


@pytest.mark.stage(4)
def test_parse_run_options_accepts_offered_bounds(studio):
    options = studio.parse_run_options("guided", 8, 0.15, True, "  Why?  ")
    assert options == {
        "depth": "guided",
        "max_turns": 8,
        "max_budget_usd": 0.15,
        "specialist_review": True,
        "question": "Why?",
    }


@pytest.mark.stage(4)
@pytest.mark.parametrize(
    "arguments",
    [
        ("deep", 1, 0.05, False, ""),
        ("brief", 2, 0.05, False, ""),
        ("brief", True, 0.05, False, ""),
        ("brief", 1, 0.07, False, ""),
        ("brief", 3, 0.5, True, ""),
        ("brief", 8, 0.05, True, ""),
        ("brief", 8, 0.15, "yes", ""),
        ("brief", 1, 0.05, False, "x" * 2001),
    ],
)
def test_parse_run_options_rejects_unoffered_or_unsafe_bounds(studio, arguments):
    with pytest.raises(ValueError):
        studio.parse_run_options(*arguments)


# M12: external knowledge


@pytest.mark.stage(5)
def test_mcp_settings_for_each_mode(studio):
    assert studio.mcp_settings("none")["mcp_servers"] == {}
    docs = studio.mcp_settings("docs")
    assert docs["allowed_tools"] == ["mcp__claude_docs__*"]
    custom = studio.mcp_settings(
        "custom", "kb", "https://kb.example.com/mcp", "search, fetch, search"
    )
    assert custom["allowed_tools"] == ["mcp__kb__search", "mcp__kb__fetch"]
    assert custom["mcp_servers"] == {"kb": {"type": "http", "url": "https://kb.example.com/mcp"}}


@pytest.mark.stage(5)
@pytest.mark.parametrize(
    ("name", "url", "tools"),
    [
        ("kb", "http://kb.example.com/mcp", "search"),
        ("kb", "https://user:pw@kb.example.com/mcp", "search"),
        ("kb", "https://kb.example.com/mcp?token=abc", "search"),
        ("kb", "https://localhost/mcp", "search"),
        ("kb", "https://127.0.0.1/mcp", "search"),
        ("kb", "https://192.168.1.10/mcp", "search"),
        ("kb", "https://kb.example.com/mcp", ""),
        ("kb", "https://kb.example.com/mcp", "a,b,c,d,e,f"),
        ("kb", "https://kb.example.com/mcp", "bad tool"),
        ("1kb", "https://kb.example.com/mcp", "search"),
        ("claude_docs", "https://kb.example.com/mcp", "search"),
    ],
)
def test_mcp_settings_rejects_unsafe_custom_servers(studio, name, url, tools):
    with pytest.raises(ValueError):
        studio.mcp_settings("custom", name, url, tools)


@pytest.mark.stage(5)
def test_mcp_settings_rejects_unknown_modes(studio):
    with pytest.raises(ValueError):
        studio.mcp_settings("web")


# M13: review and evidence

RUN = {
    "id": "r1",
    "case_id": "first-query",
    "run_mode": "prepared",
    "subtype": "success",
    "criteria": ["Answers the question", "Names the final result"],
}


@pytest.mark.stage(6)
def test_review_record_labels_the_kind_of_run(studio):
    record = studio.review_record(RUN, [True, True], " Clear. ")
    assert record["kind"] == "prepared fixture" and record["passed"] is True
    assert record["note"] == "Clear." and record["criteria"][1]["met"] is True
    live = studio.review_record(
        RUN | {"run_mode": "live", "subtype": "error_max_turns"}, [True, True]
    )
    assert live["kind"] == "live SDK run" and live["passed"] is False


@pytest.mark.stage(6)
@pytest.mark.parametrize(
    ("run", "marks", "note"),
    [
        (RUN, [True], ""),
        (RUN, [True, "yes"], ""),
        (RUN, [True, True], "x" * 1001),
        (RUN | {"criteria": []}, [], ""),
        (RUN | {"run_mode": "simulated"}, [True, True], ""),
    ],
)
def test_review_record_rejects_incomplete_reviews(studio, run, marks, note):
    with pytest.raises(ValueError):
        studio.review_record(run, marks, note)


@pytest.mark.stage(6)
def test_export_evidence_keeps_fixtures_and_live_runs_apart(studio):
    prepared = studio.review_record(RUN, [True, True], "fine")
    live = studio.review_record(RUN | {"run_mode": "live"}, [True, False], "missed | one")
    markdown = studio.export_evidence([prepared, live])
    assert "prepared fixture" in markdown and "live SDK run" in markdown
    assert "not live" in markdown.lower()
    assert markdown.count("\n| first-query") == 2


# M14: regression suite and release decision


@pytest.mark.stage(7)
def test_release_decision_requires_an_explanation_for_each_regression(studio):
    baseline = {
        "a": {"subtype": "success", "passed": True},
        "b": {"subtype": "success", "passed": True},
    }
    candidate = {
        "a": {"subtype": "success", "passed": False},
        "b": {"subtype": "success", "passed": True},
    }
    blocked = studio.release_decision(baseline, candidate, {})
    assert blocked == {"regressions": ["a"], "missing": [], "unexplained": ["a"], "ready": False}
    explained = studio.release_decision(baseline, candidate, {"a": "Criterion clarified."})
    assert explained["ready"] is True and explained["regressions"] == ["a"]


@pytest.mark.stage(7)
def test_release_decision_flags_failures_and_missing_cases(studio):
    baseline = {
        "a": {"subtype": "success", "passed": None},
        "b": {"subtype": "success", "passed": None},
    }
    candidate = {"a": {"subtype": "error_max_turns", "passed": None}}
    decision = studio.release_decision(baseline, candidate, {"a": "turn limit"})
    assert decision["regressions"] == ["a"] and decision["missing"] == ["b"]
    assert decision["ready"] is False


@pytest.mark.stage(7)
def test_release_decision_ignores_improvements(studio):
    baseline = {"a": {"subtype": "error_max_turns", "passed": False}}
    candidate = {"a": {"subtype": "success", "passed": True}}
    assert studio.release_decision(baseline, candidate, {})["ready"] is True
