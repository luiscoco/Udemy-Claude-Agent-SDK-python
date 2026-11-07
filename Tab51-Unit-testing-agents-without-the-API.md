# Lesson 51: Unit testing agents without the API

Run deterministic host assertions without a model call or API key.

```shell
uv run agent-lab lesson 51
uv run python scripts/offline_host.py
uv run agent-lab serve
```

Open `http://127.0.0.1:8080/?lesson=51` and choose **Run the exercise**. The normal All group runs sixteen ordered cases: six contracts, two store checks and eight replay checks. Its 16/16 report with zero model calls, zero actual billing and cleanup earns the automatic check. Filtered groups help locate failures but cannot earn complete-suite credit.

Enable the mutation challenge to see one deliberate `denial-policy` failure (15/16). Restore the normal suite. Replay the six public fixed streams separately: success, budget, API error, invalid session, truncated stream and malformed tool call. The replayer calls a real scoped store handler for an admitted lookup, checks exact call/result identity and closes the fake query. Synthetic fixture costs are never billed costs.

`uv run python scripts/offline_host.py --mutation` exits 1 for that deliberate failure. `--live` is rejected with exit 2. The standalone command installs a controlled network guard before loading the suite. This lesson does not offer a live provider path.

See [implementation and verification](docs/lesson-51-offline.md) and [narration evidence](docs/lesson-51-narration.md).
