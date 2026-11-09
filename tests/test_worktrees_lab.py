"""Real Git integration and conflict evidence for Lesson 57."""

import asyncio
import copy
import uuid
from pathlib import Path

import pytest

from agent_lab.worktrees_lab import RunInput, grade, load_report, run_workshop
from agent_lab.worktrees_native import exact_file, grade_native


@pytest.mark.asyncio
async def test_owned_independent_and_conflict(tmp_path: Path) -> None:
    independent = await run_workshop(RunInput(), tmp_path)
    assert independent["check"] == "passed" and grade(independent)
    assert len(independent["workers"]) == len(independent["integration"]) == 2
    assert independent["worktreeCount"] == 1
    assert load_report(tmp_path, independent["runId"])["report"] == independent
    conflict = await run_workshop(RunInput(scenario="conflict"), tmp_path)
    assert conflict["check"] == "needs-review" and not grade(conflict)
    assert conflict["conflict"] == {"worker": "alternative", "unmerged": ["greeting.mjs"],
                                    "pickExit": 1, "priorPicks": 1, "aborted": True}
    assert conflict["worktreeCount"] == 3 and not conflict["combinedTests"]
    assert load_report(tmp_path, conflict["runId"])["report"] == conflict


@pytest.mark.asyncio
async def test_grader_mutations_and_foreign_owner(tmp_path: Path) -> None:
    report = await run_workshop(RunInput(), tmp_path)
    for mutate in (
        lambda row: row["workers"][0].update(workerSHA=row["baseSHA"]),
        lambda row: row["workers"][1]["test"].update(exit=1),
        lambda row: row["integration"][1].update(parentSHA=row["baseSHA"]),
        lambda row: row["cleanup"][0].update(nonForce=False),
        lambda row: row.update(mainClean=False),
    ):
        altered = copy.deepcopy(report)
        mutate(altered)
        assert not grade(altered)
    marker = tmp_path / "lesson-57" / report["runId"] / ".owner"
    marker.write_text(str(uuid.uuid4()), encoding="ascii")
    with pytest.raises(PermissionError):
        load_report(tmp_path, report["runId"])


def test_exact_native_file_gate(tmp_path: Path) -> None:
    assigned = tmp_path / "greeting.mjs"
    assigned.write_text("base\n", encoding="utf-8")
    assert exact_file("Write", {"file_path": str(assigned)}, tmp_path, assigned.name)
    assert not exact_file("Bash", {"command": "echo x"}, tmp_path, assigned.name)
    assert not exact_file("Write", {"file_path": "../other"}, tmp_path, assigned.name)
    assert not exact_file("Write", {"file_path": "new.mjs"}, tmp_path, assigned.name)
    alias = tmp_path / "alias.mjs"
    try:
        alias.symlink_to(assigned)
        assert not exact_file("Write", {"file_path": str(alias)}, tmp_path, alias.name)
    except OSError:
        pass


def test_native_grader_requires_correlated_evidence() -> None:
    report = {"closed": True, "interrupted": False, "exception": None,
              "sdkQueries": 1, "modelCalls": None, "costUsd": 0.01,
              "frames": [{"kind": "init", "session": "s"},
                         {"kind": "hook", "id": "t", "tool": "Write", "admitted": True},
                         {"kind": "callback", "id": "t", "tool": "Write", "admitted": True},
                         {"kind": "call", "id": "t", "tool": "Write", "exact": True},
                         {"kind": "result", "id": "t", "isError": False},
                         {"kind": "terminal", "session": "s", "id": "r", "subtype": "success",
                          "isError": False, "costUsd": 0.01}]}
    assert grade_native(report)
    for mutate in (
        lambda row: row["frames"][2].update(id="foreign"),
        lambda row: row["frames"][4].update(isError=True),
        lambda row: row.update(costUsd=None),
        lambda row: row["frames"][3].update(exact=False),
    ):
        altered = copy.deepcopy(report)
        mutate(altered)
        assert not grade_native(altered)


@pytest.mark.asyncio
async def test_preinterrupted_retains_partial_report(tmp_path: Path) -> None:
    abort = asyncio.Event()
    abort.set()
    report = await run_workshop(RunInput(), tmp_path, abort)
    assert report["interrupted"] and report["check"] == "needs-review"
    assert load_report(tmp_path, report["runId"])["report"] == report


@pytest.mark.asyncio
async def test_direct_live_requires_consent_and_enabled_gate(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        await run_workshop(RunInput(mode="live"), tmp_path)
    with pytest.raises(PermissionError):
        await run_workshop(RunInput(mode="live", consent=True), tmp_path)


@pytest.mark.asyncio
async def test_worker_file_failures_settle_before_integration(tmp_path: Path) -> None:
    async def extra(name: str, path: Path, item: dict[str, str]) -> None:
        if name == "greeting":
            (path / "extra.mjs").write_text("export const x = 1;\n", encoding="utf-8")

    report = await run_workshop(RunInput(), tmp_path, prepared_hook=extra)
    assert report["settled"] and len(report["workers"]) == 2
    assert report["workers"][0]["error"] and report["workers"][1]["workerSHA"]
    assert not report["integration"] and report["check"] == "needs-review"
    assert report["worktreeCount"] == 3

    async def noop(name: str, path: Path, item: dict[str, str]) -> None:
        if name == "greeting":
            (path / item["file"]).write_bytes(b"export function greet(name) { return 'TODO'; }\n")

    no_change = await run_workshop(RunInput(), tmp_path, prepared_hook=noop)
    assert no_change["workers"][0]["changed"] == []
    assert not no_change["integration"] and no_change["check"] == "needs-review"


@pytest.mark.asyncio
async def test_dirty_main_blocks_all_picks(tmp_path: Path) -> None:
    async def dirty(repo: Path) -> None:
        (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    report = await run_workshop(RunInput(), tmp_path, before_integration=dirty)
    assert report["mainBefore"] == report["baseSHA"] and not report["mainCleanBefore"]
    assert not report["integration"] and report["worktreeCount"] == 3
    assert report["check"] == "needs-review"
