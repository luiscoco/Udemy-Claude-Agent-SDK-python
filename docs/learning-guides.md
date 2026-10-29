# Written Learning Guides

All 75 lessons have **Open Learning Guide** above the tabs. Start the tour explicitly
or resume a saved section. The seven sections cover the goal, preparation, Python
example, exercise controls, evidence, source and practice.

The guide frames a real page element in red and keeps it clear of the fixed header
and guide panel. Long code, paragraphs and results scroll inside their frames. Its
navigation buttons stay visible while the guide text scrolls. Changing tabs manually
pauses the tour; **Show section** returns to its target. Minimize and close preserve
the saved section. **Finish tour** clears only this lesson's position and returns to
its heading. **Next lesson** follows the selected learning path; it is absent when
there is no next lesson in that route.

Guide controls do not run exercises, select live mode, authorize model calls, answer
questions, save student explanations or change the manual review checklist. Notes,
attempts and tour positions are separate. Positions are included in progress exports;
older exports without that field remain importable.

## Content and maintenance

`agent_lab/lesson_guide.py` builds and validates the guide catalog. The curated entries
in `agent_lab/content/learning_guides.json` take precedence, preserving the approved
Lesson 1 text. Remaining lessons are populated directly from their teaching content:

| Section | Lesson-specific source | Target |
|---|---|---|
| Goal | Curriculum objective, concept brief and first teaching step | Objective paragraph |
| Preparation | All preparation instructions, including prerequisites and optional live distinctions | First preparation paragraph |
| Example | Code focus and named source-tour sections | Actual concept-code frame in Learn |
| Controls | Offline host behavior and run instructions | Run exercise button |
| Evidence | Fields to inspect, expected result and evidence criterion | Response and results content |
| Source | Concept focus, actual registered host function and offline boundaries | Actual concept-code frame in Python source |
| Practice | Full lesson challenge | Your explanation and evidence field |

The source data lives in `agent_lab/content/lessons.json`,
`agent_lab/content/code_tours.json`, `agent_lab/curriculum.py` and the host exercise
registry. No extra generated copy needs rebuilding when these lesson texts change.
Restart the server after editing cached content. Add a validated curated entry when
a lesson needs different wording or semantic targets. Guides must contain the seven
section ids in order; duplicate lesson ids and invalid selectors are rejected.

Keep the SDK concept and the actual offline implementation distinct. For example,
lesson 17's host snapshot does not demonstrate live SDK checkpointing, lesson 29
does not upload an image in its text-only live exercise, and lesson 75's bounded
fixture does not publish a pull request. The guide uses each lesson's preparation,
host description and expected evidence to preserve these distinctions.

## Verification

- `tests/test_lesson_guide.py` checks all 525 sections and binds lessons 2-75 to their
  own preparation, concept focus, registered host function, evidence and challenge.
- `test_browser_remaining_learning_guides_frame_all_seven_targets` visits every
  remaining lesson, using a mix of desktop and phone viewports, and checks all seven
  red outlines, target bounds, source-code frames, cleanup and terminal navigation.
- Lesson 1's existing tests cover keyboard focus, dark mode and Extra large text,
  manual-tab pause, missing-target recovery, and unchanged exercise/completion state.
- The cross-lesson test verifies independent Resume positions and retained notes
  across lessons 2 and 75. Progress tests cover validated backup and restore.
- The red outline is checked as rendered CSS, including after a Run button update.
  CSS layer priority must continue to override the framework's `no-outline` rule.

These are written guides. Recorded Python narration, full TypeScript runtime parity
and student acceptance remain separate work in [the parity report](reference-parity.md).
