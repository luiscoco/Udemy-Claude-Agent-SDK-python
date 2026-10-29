# My Learning

Open **My Learning** from the course home page, a lesson's header or its navigation
drawer. The workspace is served at `/my-learning`; the quick-start page is `/setup`.

## What students can do

- Continue the last visited lesson or explicitly resume its saved Learning Guide
  section. If no last lesson is available, saved work or the next unreviewed lesson
  supplies a starting point. A fully reviewed course has no fabricated next lesson.
- See manual checklist progress, lessons with saved work and recorded exercise
  checks. Learning-path cards show their own reviewed count and next unreviewed
  lesson in route order. Finished paths do not wrap to lesson one.
- Find lessons and saved text using path, status and search filters. The path stays
  in the URL and is retained when navigating to a lesson in that path or to setup.
- Read private notes and unsubmitted explanation drafts, review saved practice-quiz
  choices and explanations, and browse every saved challenge attempt. Attempt and
  lesson lists have **Show more** controls.
- Review section-quiz practice separately, open the three companion projects, and
  use the existing progress export/import controls for backups or transfers.
- On a first visit, start lesson 1 or review the real setup page. Setup shows the
  existing offline commands and describes optional live configuration; it does not
  install dependencies, start a second server or make a model call.

## Meaning of the counts

**Reviewed** means that the learner selected all four manual checklist items.
**In progress** means that work or a guide position is saved and manual review is
not complete. **No saved work** describes the stored record, not proof that the
student has never visited a lesson. Exercise checks and quiz answers never mark a
lesson reviewed. Quiz results reflect the currently saved practice answers, not a
certificate or a history of assessment attempts.

Saved work includes notes, drafts, attempts, valid quiz choices, checklist choices,
hints, saved tutor answers, exercise checks, run summaries and valid guide positions.
Section quizzes remain separate from lesson counts and challenge attempts.
Choosing to open a section quiz uses the existing quiz dialog. Its saved result
refreshes when the dialog closes, without marking any lesson reviewed. The global
Continue action follows the last visited lesson; path cards recommend the next
unreviewed lesson within their own route.

## Storage and implementation

The dashboard reads the existing NiceGUI per-browser records on this installation.
It adds no persistence keys and does not change the progress file format. Visiting,
searching, filtering or exporting does not update lesson records. The existing
import confirmation still replaces progress only when the learner chooses it.
Account login and cloud synchronization are not part of this workspace.

`agent_lab/my_learning.py` creates immutable summaries and filters without writing
to the input store. It ignores invalid or stale answer choices when presenting quiz
results. `agent_lab/ui_my_learning.py` renders the workspace and setup pages using
the existing appearance controls. Student text is rendered as plain text, including
text that resembles HTML. Students edit their notes and submit explanations in the
lesson itself.

An explicit **Resume Learning Guide** link carries a one-time `resume_guide=true`
query. The lesson resolves the section from that browser's existing saved position,
opens the guide and consumes the query. Reloading after closing the guide does not
automatically reopen it. No exercise, paid call, manual check or submission is
triggered by resuming a guide.

The workflow follows the pinned TypeScript reference's
[My Learning workspace contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/a11-improve-my-learning-workspace.md),
adapted to the Python application's existing records and appearance system.

## Verification

`tests/test_my_learning.py` checks manual-review rules, independent activity counts,
path boundaries, valid saved choices, search, resume links and unchanged source data.
The browser tests in `tests/test_learning.py` cover first visits, setup navigation,
import/export equality, saved notes and drafts, quiz feedback, attempt pagination,
route retention and explicit guide resumption. They also exercise light and dark
appearance at 320px and 150% content scaling, including long saved text. Existing
progress tests continue to verify the unchanged backup format.
