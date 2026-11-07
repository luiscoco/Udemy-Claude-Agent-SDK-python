# Lesson 51 offline host suite

The fixed manifest has sixteen cases in contract (6), store (2) and replay (8) groups. `agent_lab/offline_lab.py` executes actual strict input, exit mapping, approval and scoped store contracts; `FakeQuery` feeds normalized synthetic envelopes to the real host consumer. The replay consumer admits only the known lookup, matches exact tool call/result IDs, requires a terminal, and closes the query.

The normal complete suite returns 16/16 and is the only graded result. A mutation changes the observed denial code from 12 to 0 without weakening the assertion, yielding 15/16. Filtered groups and six public replays are diagnostic. Costs in fixtures are simulated; `modelCalls` and `actualBilledUsd` are zero.

The `/api/c51/facts`, `/code`, `/run`, `/replay`, `/stop` routes are local and strict. Run and replay stream started, case or fixture, summary and complete frames. Invalid input is HTTP 400 and overlapping operations are HTTP 409. The CLI network guard rejects provider calls and `--live` exits 2. There is no live selector for this lesson.

Run `uv run python scripts/offline_host.py`, the focused `tests/test_offline_lab.py`, `tests/test_api_offline.py`, `tests/test_offline_cli.py`, and the Lesson 51 browser test in `tests/test_learning.py`. The browser page includes seven explained questions, two diagrams, three source excerpts and the scoped evidence table.
