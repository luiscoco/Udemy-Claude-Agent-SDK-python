# Lesson 21: Slash commands

This lesson writes one host-owned `.claude/commands/lesson-summary.md` template in each disposable run workspace. The Summary and Quiz selections change the template and its fixed response marker. `source=project` sets `ClaudeAgentOptions.setting_sources=["project"]`; `source=none` leaves filesystem settings disabled while keeping the file in place.

The SDK connection first reports available commands through `get_server_info()`. The lab sends `/lesson-summary` on that same connection, then checks one `Read` of the owned `notes.txt`, a matching successful tool result, the selected marker in assistant or terminal text, a matching initialized/final session, unchanged file hashes and client closure. Model tools are limited to `Read`; an exact host policy denies reads of command settings, other files and outside paths. The command cannot grant new file access.

Use the Run tab's **Filesystem settings source** and **Command template** controls, or pass `{"source":"project","template":"quiz"}` in a lesson options JSON file. The valid values are `project`/`none` and `summary`/`quiz`; extra fields and arbitrary paths are rejected. The normal lesson endpoint, CLI and browser share validation.

Offline runs perform actual host file writes and reads but label SDK session, inventory and tool identities as fixtures. They cannot certify command discovery by Claude. The `missing-evidence`, `wrong-identity`, `missing-command`, `missing-invocation` and `unmatched-read` scenarios intentionally need review. Live runs use actual SDK inventory and stream data. The `none` control can confirm absence of discovery but intentionally fails the full invocation check.

The earlier `project_markdown` exercise still lists local Markdown files. Its `files` and `setting_sources` fields describe host setup; the automatic criterion uses the enhanced `experiment` report. The seven review questions and three exact source excerpts cover command ownership, project source opt-in, inventory, Read correlation and control limitations.

Three bounded provider-backed cases passed on 3 November 2026; see [live acceptance](live-acceptance.md). This verifies the pinned Python SDK and CLI behavior for an owned project command. Arbitrary commands, user settings, plugin namespaces, argument expansion, authored media and full reference parity remain separate. Lesson 22, CLAUDE.md and memory, is next.

References: [Claude Agent SDK cookbook](https://platform.claude.com/cookbook/claude-agent-sdk-01-the-chief-of-staff-agent), [Python SDK client control method](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py).
