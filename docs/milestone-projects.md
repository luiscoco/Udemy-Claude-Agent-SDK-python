# Build the milestone projects

The course has three milestone projects that you build yourself. Each one is a Python file
of contracts (functions with a docstring and a `NotImplementedError` TODO) that the course
app runs, so every stage you finish unlocks a feature on its page.

| Order | Project | Your file | Page | Stages |
|---|---|---|---|---|
| 1 · Understand | [Study Coach](../mini_projects/study_coach/README.md) | `mini_projects/study_coach/coach.py` | `/coach` | M01–M07 |
| 2 · Evaluate | [Agent Evaluation Studio](../mini_projects/evaluation_studio/README.md) | `mini_projects/evaluation_studio/studio.py` | `/studio` | M08–M14 |
| 3 · Publish | [Agent Publishing Studio](../mini_projects/publishing_studio/README.md) | `mini_projects/publishing_studio/publisher.py` | `/publish` | M15–M22 |

The stages are your work, not finished submissions: a fresh clone starts every project at
`STAGE = 1`.

## Procedure for every stage

1. Run `uv run agent-lab serve` and open the project's page.
2. Read the stage prompt in the project's `prompts/` folder: goal, what to implement, what to
   try on the page, expected result, hints and a short quiz.
3. Implement the named functions in your file. Keep earlier stages passing and do not change
   public signatures.
4. Run the stage checks, then raise `STAGE` once they pass. Later tests stay skipped until
   you do.

   ```shell
   uv run agent-lab coach check      # or: studio check, publish check
   ```

5. Press **Reload my code** on the page and try the feature the stage unlocked.
6. Record what you observed in the project's `docs/evidence-template.md`. Keep prepared,
   mocked and live evidence in separate rows.

Stuck? `uv run agent-lab <project> check --reference` runs the same checks against the
reference solution, and each page can switch to **Reference** to show the finished
behavior. Neither marks your own work as done.

## Compare the three learning paths

The counts measure different activities, so do not add them up.

| Project | Catalog | What you do | Evidence of progress |
|---|---:|---|---|
| Study Coach | 80 concept cards: 5 start-here cards and one per lesson | Read a concept, its Python code and lab source, ask a focused question, answer a recognition check | A correct check; applying the concept still happens in the lesson's lab |
| Agent Evaluation Studio | 170 cases in 17 sections | Run a prepared case, inspect the answer, result and timeline, review its criteria, optionally compare an authorized live run | A recorded, reviewed run; a run alone is not mastery |
| Agent Publishing Studio | 173 prompt suggestions in 17 sections | Ask, inspect the exact answer, turn an approved answer into Word/PDF or an infographic | A reviewed answer and downloadable files tied to it by id and SHA-256 |

## Learning order

1. **Understand:** start in the Study Coach with the start-here cards (LLM, agent, harness,
   SDK, first `query()`), then follow a course route.
2. **Evaluate:** in the Evaluation Studio, judge runs by their result and timeline, not by how
   fluent the answer sounds.
3. **Publish:** in the Publishing Studio, turn only answers you reviewed into files, and review
   the files before you share them.

## Prepared and live

Every project works offline with prepared fixtures and zero model calls. Live calls are
optional: they need `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true` in `.env`, a restart, and
fresh consent for each paid call (plus separate consent for an MCP connection or a second
planning call). The API key stays on the server.

Your work runs locally. Account sync, managed backups and shared hosting are outside the
course scope.
