"""Free Lesson 58 local checks."""

from pathlib import Path

from agent_lab.tool_search_lab import (
    Config,
    PlanInput,
    RunInput,
    SearchInput,
    catalog,
    plan,
    prepared,
    search,
)


def main() -> None:
    assert len(catalog(Config())) == 64
    assert search(SearchInput())["references"][0] == "mcp__ops__billing_refund_invoice"
    assert not search(SearchInput(metadata="vague"))["references"]
    assert search(SearchInput(metadata="vague", query="select:billing_op_7"))["references"] == ["mcp__ops__billing_op_7"]
    assert plan(PlanInput())["loadedCount"] == 0
    assert plan(PlanInput(searchMode="false"))["loadedCount"] == 64
    report = prepared(RunInput(), Path(".lab-data"))
    assert report["check"] == "pass" and report["costUsd"] == 0
    print("Lesson 58 local catalog, search, plan and owned ledger: PASS")


if __name__ == "__main__":
    main()
