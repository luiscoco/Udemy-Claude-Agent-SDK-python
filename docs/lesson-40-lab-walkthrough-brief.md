# Lesson 40 lab walkthrough brief

1. Capture serialized SDK flags with `/api/c40/dry`.
2. Build and inspect the prepared source. Follow active `parentUuid` ancestry and locate the queued attachment within turn 3.
3. Compare exact, unsafe and recovery cases. Inspect the new fork session IDs, retained prompts, queued attachment and unchanged source hash.
4. Run one selected `/api/c40/undo` boundary and note that a single attempt cannot pass the full comparison.
5. Inspect the live report. The source, exact drop and recovery succeeded; the unsafe guard raised during connection, and the SDK preserved its real CLI result frame in structured `ResultError.data`. Verify the parsed frame and its origin, then the passed live check.
