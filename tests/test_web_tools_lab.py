"""Lesson 42 URL boundaries, policy hooks and prepared web evidence."""

import copy
from pathlib import Path

import pytest

from agent_lab.config import Settings
from agent_lab.web_tools_lab import (
    ABOUT,
    FORBIDDEN,
    OVERLAY,
    REMOVED,
    WebPolicy,
    canonical_url,
    citation_labels,
    evaluate_lane,
    plan,
    run,
    search_family,
    state,
)


@pytest.mark.parametrize("url", ["http://nodejs.org/en/about", "https://nodejs.org.evil.test/en/about",
                                   "https://nodejs.org:444/en/about", "https://user@nodejs.org/en/about",
                                   "https://nodejs.org/en/about#part", FORBIDDEN])
def test_fetch_allowlist_refuses_alternates(url: str) -> None:
    assert canonical_url(url) is None
    assert canonical_url(ABOUT) == ABOUT
    assert search_family("https://docs.nodejs.org/en/about")


async def test_policy_rewrites_search_and_denies_foreign_fetch() -> None:
    policy = WebPolicy("test", 1, 2)
    outcome = await policy.pre({"tool_name": "WebSearch", "tool_input": {
        "query": "Node.js runtime", "allowed_domains": ["wrong.example"],
        "blocked_domains": ["nodejs.org"]}}, "search-id", None)
    effective = outcome["hookSpecificOutput"]["updatedInput"]
    assert effective["allowed_domains"] == ["nodejs.org"]
    assert "blocked_domains" not in effective
    denied = await policy.pre({"tool_name": "WebFetch", "tool_input": {
        "url": FORBIDDEN, "prompt": "Read"}}, "denied-id", None)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert citation_labels(ABOUT + " https://example.com/", {ABOUT}, [ABOUT]) == [
        {"url": ABOUT, "label": "fetched"}, {"url": FORBIDDEN, "label": "invalid"}]


@pytest.mark.parametrize("action", ["basics", "fetch-lab", "injection", "guard", "research"])
async def test_prepared_actions_correlate_calls_and_results(tmp_path: Path, action: str) -> None:
    report = await run(tmp_path, Settings(), action, "prepared")
    assert report["experiment_passed"], report
    assert all(lane["fixture"]["independently_reread"] for lane in report["lanes"])
    assert state(tmp_path)["run_id"] == report["run_id"]
    if action == "injection":
        unguarded, guarded = report["lanes"]
        assert unguarded["post"][0]["delivered_marker"] == OVERLAY
        assert guarded["post"][0]["delivered_marker"] == REMOVED


@pytest.mark.parametrize("scenario", ["missing", "foreign", "failed"])
async def test_prepared_negative_keeps_latest(tmp_path: Path, scenario: str) -> None:
    good = await run(tmp_path, Settings(), "basics", "prepared")
    bad = await run(tmp_path, Settings(), "basics", "prepared", scenario=scenario)
    assert not bad["experiment_passed"]
    assert state(tmp_path)["run_id"] == good["run_id"]


async def test_missing_public_page_needs_review(tmp_path: Path) -> None:
    report = await run(tmp_path, Settings(), "fetch-lab", "prepared", page="missing")
    assert not report["experiment_passed"]


async def test_evaluator_rejects_wrong_fetch_and_duplicate_post(tmp_path: Path) -> None:
    report = await run(tmp_path, Settings(), "basics", "prepared")
    lane = report["lanes"][0]
    wrong = copy.deepcopy(lane)
    wrong["calls"][1]["input"]["url"] = "https://nodejs.org/dist/index.json"
    assert not evaluate_lane("basics", plan("basics")[0], wrong)["experiment_passed"]
    repeated = copy.deepcopy(lane)
    repeated["post"][1] = copy.deepcopy(repeated["post"][0])
    assert not evaluate_lane("basics", plan("basics")[0], repeated)["experiment_passed"]
    bad_search = copy.deepcopy(lane)
    bad_search["post"][0]["invalid_urls"] = ["https://nodejs.org.evil.test/"]
    assert not evaluate_lane("basics", plan("basics")[0], bad_search)["experiment_passed"]
