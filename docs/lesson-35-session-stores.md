# Lesson 35: Session stores

The host owns `transcript.json` as application data. The SDK separately mirrors its conversation into a `SessionStore`. These serve different purposes even when the host transcript records the SDK session ID.

The lesson offers four transcript and resume actions:

1. **Commit:** write a complete `transcript.tmp`, replace `transcript.json`, and verify the new bytes and hash.
2. **Interrupted:** stop before replacement. Verify the baseline JSON hash remains and the temporary file exists.
3. **Resume:** make a first SDK turn, inspect mirrored user and assistant entries, then open a fresh client with the observed session ID and the same `InMemorySessionStore`. The second turn must recall `ORBIT_35`.
4. **Durable resume:** mirror into an owned SQLite database, reopen the adapter, and resume with a fresh SDK configuration directory. A separate process test verifies that stored entries remain readable after the original process exits.

Choose eager or batched flushing and optionally delay a store load. A disabled mirror or rejected append leaves the model turn successful but makes the storage check need review. The store wrapper records append/load timing and failures. The SQLite adapter deduplicates UUID-bearing entries, folds session summaries, and scopes sessions and subkeys by project and session.

Offline mode uses real host file operations and labelled SDK fixtures. Live mode uses a real provider-backed SDK stream with no model tools. Passing evidence requires successful terminal results, matching session IDs, nonempty local and stored transcripts, zero missing UUIDs from the first owned local CLI transcript, zero mirror errors, matching summary identity and modification time, the correct host file state, and complete client closure. This is UUID coverage; it does not compare every byte or establish coverage for entries without UUIDs.

The scoped API exposes `POST /api/c35/run`, `GET /db`, `GET /entries`, `POST /failures`, `POST /manage`, `POST /reset`, and `GET /code` under `/api/c35`. Run requests use strict options and require explicit consent for live calls. Inspection and mutation are separate; a run ID and control token gate private results and deletion. The lesson browser also exposes the four storage actions, flush policy, mirror enable switch and fault controls.

The [concept map brief](lesson-35-concept-map-brief.md) and [lab walkthrough brief](lesson-35-lab-walkthrough-brief.md) are distinct planning sources for the two visual tabs. [Reviewed Python narration](lesson-35-narration.md) now has three recorded source clips; human listening review remains before audio acceptance.

Run the local lesson with `uv run agent-lab lesson 35`. The explicit paid acceptance command is `uv run python scripts/lesson_live_smoke.py 35 --live`; its eight cases run sequentially and stop on the first failure.
