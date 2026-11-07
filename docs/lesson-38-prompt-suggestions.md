# Lesson 38: Prompt suggestions

The CLI can emit a `prompt_suggestion` after a completed turn. The installed Python SDK skips this raw message type, so the lesson uses a transport tap to record it before parsing. Suggestions remain proposed text in a separate ledger. A user or host must explicitly submit one through the validated input queue.

## Try it

Start the app with `uv run agent-lab serve` and open lesson 38. The offline exercise uses authored SDK fixtures to show two successful turns, session identity, an observed suggestion, and normal closure. Select **Live** only after configuring `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true`. The live chat has no tools or MCP servers, uses an isolated configuration directory, accepts at most three inputs, ends after 60 seconds, and caps the SDK budget at $0.10.

The interactive API has `POST /api/c38/dry` for an options preview, `/chat` to create one token-owned conversation, `/send` to queue a validated input, `/status` to inspect the ledgers, and `/end` to close and evaluate it. `/when`, `/switches`, and `/cache` return comparison metadata for `{}` and run only one selected two-turn probe when a mode and variant are supplied. Setting-off and cache variants are comparison-only in this Python CLI build. `GET /api/c38/code` returns three source excerpts.

An enabled run passes only when the two ordered SDK turns succeed in one session, an attributable nonempty suggestion is observed, and input and connection close normally. The edited variant sends a third input only when it can copy and change an actually observed suggestion. An absent suggestion is a **Needs review** outcome. It does not identify which setting caused the absence.

## Evidence boundary

The `submitted` ledger records exact host input IDs and text. The `results` ledger records SDK turn outcomes and session IDs. The `suggestions` ledger records raw proposed text and the turn to which it was attributed. A suggestion never enters the submitted ledger automatically. Queued text while the SDK is busy remains host input; it cannot be counted as an observed suggestion.

The `prompt-suggestions` CLI flag is passed through `ClaudeAgentOptions.extra_args`; it is not a typed Python SDK option. The tap is specific to the installed SDK/CLI version and should be revisited after an SDK upgrade.
