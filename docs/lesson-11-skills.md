# Lesson 11: Skills

Open lesson 11 and select **Run the exercise**. The default **Explicit invocation** experiment loads the prepared project skill. Compare it with **Discovery only**, **Host preload**, **Local plugin**, a hidden skill and the optional supporting checklist. The existing standard Markdown example remains in a separate collapsed reference section.

Offline mode really parses and reads owned files; its SDK call/result identities and parent outcome are explicitly recorded fixtures. It makes no model call. Live mode configures the real SDK and collects actual stream/callback evidence. A successful invocation requires one visible prepared Skill call, one successful result with the same ID and successful parent completion. Duplicate, mismatched, child-only and failed records cannot satisfy this check. Generated files and answer quality require separate review.

**Discovery only** inspects metadata without recording an invocation. **Host preload** places prepared instructions in the system appendix and hides the Skill listing; it demonstrates a separate host loading strategy. Both intentionally show **Needs review** for the invocation criterion. Selecting the hidden-skill comparison records a denied offline call, while its non-secret files remain readable under the host policy. `skills=[]` is a context filter, not a filesystem sandbox.

The prepared `SKILL.md` and `resources/checklist.md` exist in both an owned project directory and a local plugin. Plugin invocation uses `lesson-skills:lesson-summary`. Settings sources are always explicit: project only for project discovery, empty for plugin discovery. This avoids the SDK convenience option defaulting to user/project sources when sources are omitted. No arbitrary skill directory or plugin path is accepted from the browser. The small parser supports only the prepared single-line name/description frontmatter, not general YAML.

The timeline separates host inspection, instruction loading and optional support loading. It does not claim to measure the live model's complete context. **Python source** has three excerpts from current source with exact paths, line ranges and questions. **Learn** includes seven explained questions, two graduated hints, a challenge and a worked explanation. Saved answers retain the original two question indices. Automatic evidence never checks off the learner's manual review.

The same strict inputs work through `/api/lessons/11/run`, streaming/WebSocket entry points and the CLI:

```shell
uv run agent-lab lesson 11
uv run agent-lab lesson 11 --scenario wrong-identity
uv run agent-lab lesson 11 --lesson-options-file skill-options.json
```

For the last command, use `{"loading":"preload","discovery":"plugin","load_support":true}`. Negative recorded scenarios are offline only. Invalid options are rejected before creating a task or workspace.

This is an adaptation of the pinned [Skills teaching contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l11-lesson-11-skills.md), not complete reference certification. Native subagent preloading, dedicated reload/subagent route contracts, authored image assets and recorded narration remain pending. The concept-map and walkthrough briefs are distinct; no new recording is claimed. Paid model invocation is not established by injected-stream tests. Streaming input and MCP lifecycle controls (lessons 12–13) are the next implementation steps.
