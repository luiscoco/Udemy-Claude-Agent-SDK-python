# Lesson 18: Sandbox

Use **Inside**, **Outside** and **Protected** to compare one authorized Read with two denied Reads. All paths are fixed, synthetic fixtures in the run's disposable workspace or its owned run directory. The agent has Read only, no shell or external MCP tools. The check requires a unique call/result pair, a matching actual host decision, successful parent completion, unchanged neighbor bytes and connection closure. A refusal written in an answer is insufficient.

The actual host Python child can read the synthetic neighbor even though tool policy denies it. This is a deliberate unsandboxed counterexample, not evidence that the SDK sandbox failed. The temporary neighbor is removed after success, error or cancellation. Missing decisions/results and wrong session identities intentionally need review.

## Native process verification

The separate fixed command runs through the real SDK Bash tool with sandboxing required. It must write inside the workspace, fail to overwrite an explicitly denied sibling file and fail a direct connection to a local loopback server. The host first verifies that server is reachable. The host also independently checks the inside file and unchanged sibling bytes; tool text and a sandbox option alone cannot pass. Call/result IDs, a matching host guard, parent success and complete closure are required.

The sandbox enables no excluded command, no unsandboxed retry, no allowed network domain and no arbitrary command. The CLI extension `sandbox.failIfUnavailable=true` prevents silent fallback when required isolation cannot start. The typed SDK configuration is combined with an inline settings extension for this field and the explicit filesystem denial.

Built-in Read, MCP servers and hooks run outside the CLI shell sandbox. Default native read permissions remain broad unless denied explicitly. This workshop tests writes and direct loopback isolation; it does not claim all machine data is hidden, all network/proxy paths are tested, or arbitrary untrusted code is safe.

Native Windows cannot enforce this CLI sandbox. Selecting the required native probe fails validation before a task, workspace or paid request is created. The same helper runs on supported Linux/WSL2 and macOS; capability detection is only preflight. Missing dependencies or runtime failure cannot silently become an unsandboxed run.

## Run and evidence

```shell
uv run agent-lab lesson 18
uv run agent-lab lesson 18 --scenario missing-decision
uv run python scripts/lesson_live_smoke.py 18 --live
```

Options file examples: `{"target":"outside"}` and `{"target":"protected"}`. The normal `/api/lessons/18/run`, CLI and UI share strict validation. Native process mode uses `{"native_required":true}` with Live mode and the Inside selection. Native controls never accept arbitrary paths, commands or network destinations.

For a supported Linux/macOS checkout, the standalone probe has a prompt-free preflight and explicit paid opt-in:

```shell
uv run python scripts/native_sandbox_live.py
uv run python scripts/native_sandbox_live.py --live
```

This checkout also verified the native helper in the existing Ubuntu WSL distribution. Ubuntu had bubblewrap and socat, but no ensurepip, so the pinned Linux SDK was installed into a disposable target without changing system packages:

```powershell
uv pip install --target .lab-data/sandbox-linux-site --python-platform x86_64-unknown-linux-gnu --python-version 3.12 --only-binary :all: claude-agent-sdk==0.2.174
uv run python scripts/wsl_sandbox_live.py --live
```

The WSL launcher passes the existing provider environment to that one child process; it does not write credentials to a Linux file. It uses the minimal Linux SDK installation for this helper, not the full Linux application stack. The probe permits only its generated local script and a private loopback fixture. Each live scenario uses four turns, a $0.10 SDK threshold and a 120-second deadline; thresholds are not hard billing caps.

On 3 November 2026 all three real application policy cases and the actual Linux/WSL native process probe passed. Reported total cost was $0.03668325. See [live acceptance](live-acceptance.md) for report locations. macOS runtime acceptance, wider network scenarios and full reference certification remain separate. The implementation follows the [official shell sandbox documentation](https://code.claude.com/docs/en/sandboxing) and pinned SDK 0.2.174; the pinned reference lesson contract was unavailable during this work.

Seven explained questions preserve the original two answer positions. Three exact implementation excerpts, a reviewed four-step concept code tour and the content-derived seven-section Learning Guide distinguish policy, capability and enforcement. Continue with [lesson 19, Session management](lesson-19-sessions.md).
