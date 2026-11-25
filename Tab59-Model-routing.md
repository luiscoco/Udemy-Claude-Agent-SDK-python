# Lesson 59: Model routing

Model routing assigns a bounded model choice to each task and checks whether the result is correct. The browser lab compares prepared strategies against independently computed answer keys. A separate live control uses the installed Claude Agent SDK to observe model selection, review switching, alias resolution and expert delegation.

## Run the lesson

Install dependencies with `uv sync --locked`. Start the portal with `uv run agent-lab serve` and open lesson 59. The lesson includes a concept map, lab walkthrough, Python source excerpts and three Yash narration clips.

For a free command-line check, run:

```shell
uv run agent-lab lesson 59
uv run python scripts/routing_check.py
```

This checks all 104 prepared task and strategy cases, the answer keys and network isolation. Prepared cost and duration labels are synthetic. A passing prepared row is evidence about the fixture and host rules, not a provider call.

## How to use the lab

Choose one or all thirteen fixed tasks, then compare the eight prepared strategies. The independent check computes the expected answer for each task; it does not trust a strategy's self-reported confidence. Six strategies pass the current fixtures. `light` and `cascade` need review because their outputs include wrong answers. The `power-mod` task is a useful trap: a confident `001` is still wrong.

The live controls are separate from the prepared suite. Invoice review checks a stable SDK session and a real switch from a light model to a deep model. Model listing checks installed CLI metadata without a model input turn. Alias resolution checks observed usage for each requested alias. Expert delegation checks the advertised and emitted tool, the bounded expert configuration, the matching tool result and the final answer. A terminal error, missing structured output or invalid billing evidence produces `needs-review`.

The live invoice control uses a USD 0.10 per-query stop threshold and a 90-second deadline. This is a host budget threshold, not an exact provider billing cap.

## Run provider-backed checks

Configure `ANTHROPIC_API_KEY` in the ignored `.env`. Explicitly enable live mode in the portal when prompted. The command-line runner is:

```shell
uv run python scripts/live_routing_check.py --live --budget 1
```

On 25 November 2026, the fresh invoice run returned HTTP 401 from the provider. The report correctly stayed `needs-review` and marked cost unknown; a zero in that failed SDK envelope is not a free successful run. Provider-backed reruns await a working key. Do not treat the earlier 14 November observations as proof that the current code passes live.

## Review the evidence

The [implementation checkpoint](docs/lesson-59-model-routing.md) records observed reports and remaining gates. The [reference parity inventory](docs/reference-parity.md) tracks course coverage. Live reports are stored under ignored `.lab-data/lesson-59`; inspect terminal reason, model usage, SDK-reported cost and structured result together.

Before moving to Lesson 60, run the complete offline regression and fresh provider-backed live scenarios. The narration clips have passed automated source and audio checks and still need a human listening review.
