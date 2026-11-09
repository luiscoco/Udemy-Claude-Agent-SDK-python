"""Install Lesson 57 Git integration teaching and explained questions."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "agent_lab/content/lessons.json"
TOURS = ROOT / "agent_lab/content/code_tours.json"


def question(prompt: str, right: str, wrong_a: str, wrong_b: str, why: str) -> dict:
    return {"prompt": prompt, "options": [
        {"text": right, "explanation": "Correct. " + why},
        {"text": wrong_a, "explanation": "No. " + why},
        {"text": wrong_b, "explanation": "No. " + why}], "correct": 0}


def main() -> None:
    lessons = json.loads(LESSONS.read_text(encoding="utf-8"))
    item = next(row for row in lessons if row["id"] == 57)
    source = ("import asyncio\n"
              "from pathlib import Path\n"
              "from agent_lab.worktrees_lab import RunInput, grade, run_workshop\n"
              "\n"
              "async def main() -> None:\n"
              "    independent = await run_workshop(RunInput(), Path('.lab-data'))\n"
              "    assert grade(independent)\n"
              "    conflict = await run_workshop(RunInput(scenario='conflict'), Path('.lab-data'))\n"
              "    assert conflict['status'] == 'conflict'\n"
              "    assert conflict['conflict']['unmerged'] == ['greeting.mjs']\n"
              "    assert not grade(conflict)\n"
              "\n"
              "asyncio.run(main())\n")
    item.update({
        "prerequisites": [47, 51],
        "concept_brief": "Each worker edits a separate Git worktree and branch from one base commit. The host waits for both workers, validates exact assigned bytes and Node behavior, commits each worker, then cherry-picks sequentially into main. Worktrees share Git metadata; file-tool permission remains a separate gate.",
        "lab_brief": "Run the real local Git workshop in Independent mode to inspect two worker commits, successful host tests, serial integration and clean removal. Conflict mode makes both workers edit greeting.mjs from one base and retains the original worktrees after aborting the second conflicting pick. Optional live mode replaces fixed worker edits with two bounded SDK file workers; host validation still decides.",
        "preparation": ["Install Git and Node 24; the free workshop runs local Git and Node child processes without model calls or remote operations.",
                        "Optional live mode needs a private Anthropic key, enabled backend and fresh consent for two SDK workers."],
        "steps": [{"title": "Understand the goal", "text": "Separate worker checkouts and coordinator integration duties."},
                  {"title": "Prepare your exercise", "text": "Select Independent and predict the branch and original commit for each assigned file."},
                  {"title": "Run one example", "text": "Run the prepared local workshop and inspect the two worker receipts."},
                  {"title": "Verify the evidence", "text": "Compare original worker SHAs, serial integrated SHAs, host tests, clean removals and the single remaining main worktree."},
                  {"title": "Try the challenge", "text": "Run Conflict and explain why the host aborts only the second pick and retains both original worker worktrees."}],
        "inspect": "Independent starts both workers before either commit, checks each exact file and Node behavior, records original and integrated commits, then removes clean worker worktrees without force. Conflict records an actual unmerged greeting.mjs on the second pick and aborts it.",
        "expected": "Independent passes with two worker commits whose parents equal the base, two serial picks with a parent chain, successful worker and combined Node assertions, clean main and exactly one worktree. Conflict needs review, retains three worktrees and both original refs, and runs no combined tests or cleanup.",
        "evidence_criterion": "Independent worktrees carry commits, integrate and clean up with successful host tests.",
        "evidence_checks": [{"key": "experiment_passed", "rule": "equals", "value": True}],
        "challenge": "Inspect the conflicting greeting change. Compare the first integrated Hello version with the second worker's Hi version, then explain why the host preserves both original commits and does not claim automatic integration.",
        "hints": ["Find `conflict.unmerged`, `integration` and `worktreeCount` in the retained report.",
                  "The greeting and alternative workers both start from the same base greeting.mjs. After the first Hello pick, the second Hi pick conflicts. The host records the unmerged path, aborts that pick and keeps three checkouts for inspection."],
        "reference": "Independent workers produce exact greeting and tax source in separate branches, pass fixed Node assertions, and receive original commits whose parents are the base. The coordinator cherry-picks one original SHA at a time, records the new integrated SHAs and parent chain, reruns both assertions on main, then removes only clean worker worktrees. Conflict mode deliberately assigns greeting.mjs twice. The second pick creates an unmerged path; the host aborts only that pick and retains both original branches and worktrees. A worker's SDK success alone is insufficient without host file, test and Git evidence.",
        "recovery": ["If Git or Node is missing, install Git and activate Node 24 before rerunning. The owned fixture report remains under lesson storage.",
                     "If live execution stops, Recover reads the finalized owned report without resuming execution or awarding a new check. A fresh paid run requires fresh consent."],
        "quiz": [
            question("Why does each worker use a separate worktree?", "To edit its own checkout and branch from the common base.", "To create an OS sandbox.", "To create separate remote repositories.", "Git worktrees isolate working files while sharing repository metadata."),
            question("Who validates and commits worker changes?", "The coordinator host after exact file and Node checks.", "The model's final answer.", "The remote server.", "Worker tool success is only one input to host validation."),
            question("What blocks an extra untracked file?", "The exact union of tracked and untracked changed paths.", "The model saying it edited one file.", "The branch name alone.", "The host reads actual Git changes before running source tests."),
            question("Why can a successful SDK terminal still fail?", "The assigned source or host assertions may be wrong.", "A terminal success always proves integration.", "It skips Git commits automatically.", "The host independently validates source bytes, tests and commits."),
            question("What happens after one worker fails?", "Both workers settle; no cherry-pick begins.", "The successful worker is immediately integrated.", "The failed branch is force removed.", "A failure blocks integration while partial evidence is retained."),
            question("How is the deliberate conflict handled?", "Record unmerged greeting.mjs, abort the current pick and retain worktrees.", "Force merge Hi over Hello.", "Delete both worker branches.", "The first pick remains and the second original commit is inspectable."),
            question("What proves clean independent completion?", "Two worker commits, serial picks, host tests and nonforce cleanup.", "Two generated prose summaries.", "A clean main branch before workers start.", "The criterion joins actual worker and integrated Git evidence."),
        ],
        "concept_code": source,
        "code_focus": "`run_workshop` starts two owned workers, validates their exact files and tests, then integrates one commit at a time. `grade` checks the actual parent chain and clean removal; `exact_file` limits native file tools independently.",
        "concept_points": [{"title": "Separate checkout", "text": "Each worker gets an assigned file, worktree and branch from one base commit."},
                           {"title": "Host validation", "text": "Exact source bytes and Node assertions precede coordinator commits."},
                           {"title": "Serial integration", "text": "The host cherry-picks original worker commits one at a time and keeps conflicts inspectable."}],
        "misconception": {"claim": "Separate worktrees automatically make workers safe and their changes mergeable.",
                        "correction": "Worktrees share Git metadata and are not OS sandboxes. File-tool policy, host tests and serial merge checks are separate requirements."},
    })
    LESSONS.write_text(json.dumps(lessons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tours = json.loads(TOURS.read_text(encoding="utf-8"))
    tours["57"] = {"source_sha256": hashlib.sha256(source.encode()).hexdigest(), "sections": [
        {"title": "Fresh owned independent run", "start": 5, "end": 7,
         "text": "The host creates one fresh owned Git repository and grades actual integration."},
        {"title": "Conflict observation", "start": 8, "end": 10,
         "text": "The second greeting pick records an actual unmerged path."},
        {"title": "No conflict pass", "start": 11, "end": 11,
         "text": "A retained conflict is teaching evidence, not independent integration."}]}
    TOURS.write_text(json.dumps(tours, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
