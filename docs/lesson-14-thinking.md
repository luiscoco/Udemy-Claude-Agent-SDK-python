# Lesson 14: Thinking, effort and models

Run one lane, or compare two fresh SDK connections with exactly the same prompt and one changed setting: effort, model or thinking mode. Requested settings and observed results appear separately. The host maps disabled, adaptive and enabled-with-budget thinking to the installed SDK's typed options. Valid option shapes do not establish account access or model compatibility.

The automatic check requires initialized parent identity, a correlated root Stop callback with an observed effort level, successful terminal completion and closed resources for every planned lane. Missing effort stays **Unknown**, never zero or the requested value. A requested/observed difference does not prove fallback or hidden reasoning. Model names reported by the SDK are shown without interpreting aliases. Private thinking blocks and streaming thinking/signature deltas are excluded from lesson output.

Offline mode executes the option mapping, callback and evaluator using labelled recorded SDK payloads. It makes no model call. Model latency, token counts and cost remain unknown; local host elapsed time is a separate measurement. Compare passing, missing-evidence, mismatched-identity, missing-effort, unsupported-setting, model-error and interrupted scenarios. Live mode uses actual SDK messages and registered callbacks. A failed lane closes its connection and prevents later lanes from starting; the host does not retry or choose a fallback.

Live runs require enabled/configured access and explicit consent. Two-lane runs require additional authorization for both paid lanes. The selected budget threshold applies to each lane separately and is not a guaranteed billing cap. Every lane uses a fresh client, empty tools and isolated settings. Comparison is a controlled observation, not an assessment of answer quality.

## Metadata and configuration drafts

**Model metadata (no prompt)** is separate from running the exercise. Its optional live probe connects, reads public initialization metadata and closes without calling `query` or sending a user message. Results are cached for sixty seconds. Missing model metadata stays unavailable; the configured model is labelled unverified. Disabled live access never starts a CLI. Metadata does not complete a lesson check or establish applied behavior.

The installed Python SDK has no public live `set_effort` or `set_thinking` method. Session routes therefore manage **configuration drafts for subsequent fresh queries**; they do not pretend to mutate a live agent connection. The prompt remains fixed within a draft. Each send requires fresh consent and, for two lanes, fresh comparison authorization. Drafts use control tokens, bounded concurrency, ten-minute idle expiry and at most four sends. Ending a draft cancels its owned active run.

## API and CLI

`POST /api/c14/run` accepts strict mode, prompt, limits, scenario, consent and typed `lesson_options`. `GET /api/c14/models` performs the separate metadata probe. The draft routes are `POST /api/c14/session`, `/send`, `/effort`, `/thinking`, `/model` and `/end`. Creation returns a draft ID and control token, both required for later actions. Edits validate the complete next configuration before changing it. These are host draft controls, not persistent CLI sessions.

The common lesson API, event streams and CLI share the same runner and validation:

```shell
uv run agent-lab lesson 14
uv run agent-lab lesson 14 --scenario missing-effort
uv run agent-lab lesson 14 --lesson-options-file thinking-options.json
```

For a free recorded effort comparison, the options file can contain `{"comparison":"effort","effort":"medium","comparison_effort":"high"}`. Negative scenarios are offline only. Invalid settings and identical comparison lanes are rejected before task/workspace creation.

Seven explained questions, hints, a challenge, written briefs and three exact source excerpts cover requested options, Stop observations and evidence evaluation. The seven-section Learning Guide remains user-started and never runs an exercise or changes manual review.

This adapts the pinned [lesson 14 reference contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l14-lesson-14-thinking-effort-models.md). Injected SDK streams verify host wiring and cleanup; paid account acceptance, live effort/thinking mutation, authored media and recorded narration remain pending. Lesson 15, cost and usage, is next.
