# Lesson 34: Output styles

The host writes one selected Markdown style to `.claude/output-styles/` and selects it in `.claude/settings.json`. With `setting_sources=["project"]`, the real SDK reported the active style (`teaching` or `brief`) and returned its fixed marker. With project settings disabled, the files remained present but the SDK reported `default` and returned `STYLE_NONE_34`. Every variant set `tools=[]` and `allowed_tools=[]`, and no model tool call appeared.

The automatic check compares the selected source, SDK initialization and terminal session, exact file hashes before and after, the fixed marker response and absence of tool calls. Offline mode labels its SDK observations as fixtures while writing the actual owned files. Recorded wrong-answer, changed-file and wrong-source cases need review. The original `project_markdown` exercise still lists Markdown files and explains why `settings.json` is absent from that inventory.

This fixed comparison demonstrates observed style loading and response behavior. It does not reveal the complete resolved system prompt or test arbitrary style instructions.

## Live acceptance

All three final provider-backed scenarios passed on 3 November 2026:

| Case | SDK style and answer | Stream reported USD |
|---|---|---:|
| Teaching with project | `teaching`, `STYLE_TEACHING_34` | 0.0053490 |
| Brief with project | `brief`, `STYLE_BRIEF_34` | 0.0050560 |
| Project disabled | `default`, `STYLE_NONE_34` | 0.0072325 |

Final run cost: **$0.0176375**. Report: `.lab-data/lesson-live-smoke/lesson-34-20261103T151311351266Z/report.json`. The earlier passing comparison cost $0.0180965 at `.lab-data/lesson-live-smoke/lesson-34-20261103T151049556435Z/report.json`. Combined stream-reported cost: **$0.0357340**.

Reference: [Claude Code output styles](https://code.claude.com/docs/en/output-styles).
