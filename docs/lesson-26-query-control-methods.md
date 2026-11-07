# Lesson 26: Query control methods

The offline exercise uses the official `ClaudeSDKClient` with a scripted CLI process, so it exercises the protocol without a provider call. The live experiment uses an isolated SDK connection with no tools. The switch path sends a first fixed marker prompt, calls `set_model` and `set_permission_mode`, then sends a second fixed marker prompt on the same session. The host checks both control acknowledgements, the observed assistant models, both successful terminal results, fixed markers and session identity.

The interrupt path requests a long turn with partial messages enabled. It calls `interrupt()` only after a streamed text delta, drains the response and records the actual terminal subtype. Both paths disconnect and verify that a later query raises `CLIConnectionError`.

The `plan` and `default` mode acknowledgements show that the connected CLI accepted each request. These prompts use no tools, so the experiment does not test all permission-policy effects. The interrupted terminal can be reported as `error_during_execution`; that generic subtype is recorded as observed rather than treated as a dedicated interruption code. An interrupted run may report zero stream cost even after a text delta, so provider-side billing is not established from that value.

Run the offline exercise with `uv run agent-lab lesson 26`. Run the three bounded provider-backed cases with `uv run python scripts/lesson_live_smoke.py 26 --live` after the live environment is configured. Reports are saved under `.lab-data/lesson-live-smoke/`.
