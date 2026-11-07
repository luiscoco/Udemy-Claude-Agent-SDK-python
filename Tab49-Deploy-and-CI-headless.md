# Lesson 49: Deployment and headless CI

Run the local lesson with `uv run agent-lab lesson 49`, or open the browser lab at `/?lesson=49` after starting `uv run agent-lab serve`.

Run fixed CLI and Python Agent SDK jobs as owned child processes. A successful process exit is necessary but does not prove the machine report is complete or the fixture verdict is correct. The host checks exact run identity, terminal success, denials and fixed report shape before assigning a CI exit code.

The **Headless** action compares native Claude CLI and Python SDK runs. **CI** checks a clean source (PASS, exit 0) and buggy source (FAIL, exit 20). **Limits** exercises real child close, missing result, denial, deadline and absent executable mappings. **Deploy** starts a one-slot loopback worker and checks health, readiness, 429 backpressure, 503 drain readiness, job completion, process exit and closed TCP. Limits and Deploy use owned local processes; Headless and CI also have bounded provider-backed modes.

The fixed Python files and source hashes are available from `/api/c49/files`, with the current bundle at `/api/c49/source`. The browser includes seven questions, source narration, separate concept and walkthrough diagrams, action controls and evidence tables. `/api/c49/state` saves only passing summaries.

The reference lesson uses Node.js child IPC. This Python edition uses exact `asyncio.create_subprocess_exec` arguments, bounded separate pipes and a local HTTP worker with JSONL process receipts. The deployment example files are teaching artifacts. See [the implementation guide](docs/lesson-49-headless.md) and [live acceptance log](docs/live-acceptance.md).
