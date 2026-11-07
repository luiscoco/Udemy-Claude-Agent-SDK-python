# Lesson 22: CLAUDE.md and memory

Each run writes one host-owned `CLAUDE.md` with an Alpha or Beta marker rule. A fixed question asks for the loaded project marker, or `UNKNOWN` if none is available. The model has no tools, so it cannot read the file through a tool call. The lab compares `setting_sources=["project"]` with an empty source list and compares the Claude Code preset with a custom system prompt on fresh SDK connections.

In the pinned SDK 0.2.174 and bundled CLI used here, project settings determined the answer: both system prompt modes returned the selected marker when project settings were enabled; both returned `UNKNOWN` when they were disabled. This is an observed behavioral comparison. The Python SDK does not expose the fully resolved system prompt, so the lab does not claim to inspect its assembled contents. The earlier lesson text assumed a custom prompt would suppress CLAUDE.md; the live comparison corrected that assumption.

`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` is set in the private CLI environment. The report also scans this run's private config for `MEMORY.md` and checks that the owned `CLAUDE.md` hash did not change. An empty scan is evidence about that config directory during the bounded run, not about every filesystem location or future memory behavior.

Use the Run tab's **Project settings**, **System prompt** and **Owned project rule** controls. The prompt is fixed and read-only in the UI; CLI/API callers receive an error if they substitute another prompt. Options accept only `project`/`none`, `preset`/`custom` and `alpha`/`beta`. Offline mode writes the actual owned file and labels SDK answers and identities as fixtures. Recorded negative scenarios intentionally need review. The earlier `project_markdown` output lists the host-created file; the automatic criterion uses the enhanced `experiment` report.

Six real provider-backed variants passed on 3 November 2026; see [live acceptance](live-acceptance.md). The seven review questions and three exact source excerpts cover project source selection, owned file state, behavioral evidence and auto-memory limits. Automatic memory writes outside the private config, other CLAUDE.md locations, nested instruction files, session compaction, authored media and full reference parity remain separate. Lesson 23, Plugins, is next.

References: [SDK client context API](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py), [SDK settings isolation changelog](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md).
