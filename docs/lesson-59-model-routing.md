# Lesson 59 model routing checkpoint

The Python portal now has thirteen fixed tasks, eight prepared strategies, independent answer keys, synthetic cost and duration labels, a bounded `/api/c59` API and a dedicated NiceGUI panel. The prepared fixture comparison deliberately leaves `light` and `cascade` in `needs-review`; six other strategies pass. The confident `001` draft for power-mod is rejected by its computed key even though the escalation heuristic does not flag it.

The native implementation uses a fresh owned SDK query for each task, a fixed structured schema, a USD 0.10 per-query stop threshold and a 90-second deadline. Review switches from light to deep within one stable session. The separate model-list, alias-resolution and expert-delegation controls never award the routing-suite check. The expert gate accepts the installed CLI's observed `Task` advertisement with an emitted `Agent` call only when the bounded custom expert and matched result are present.

## Observations made on 14 November 2026

- Invoice review passed: one SDK query, stable session across both turns, actual `set_model` to the configured deep ID, independent invoice grade accepted, **USD 0.012003** SDK query-pipeline estimate.
- Silent installed-CLI model metadata returned five entries with zero model input turns.
- Three invoice alias probes passed with observed Sonnet usage in each, **USD 0.0075033** SDK query-pipeline estimate in total.
- The first expert probe was `needs-review`: the CLI advertised `Task` but emitted `Agent`; the gate denied it. After correcting that compatibility rule, a fresh expert probe passed with an admitted `Agent` call, matching successful result, accepted lineup grade and both light/deep model usage entries, **USD 0.01753665** SDK query-pipeline estimate.

These reports are local under ignored `.lab-data/lesson-59` and are observations of the installed SDK, not a provider invoice or an independent expert execution audit. The new raw-terminal billing recomputation and special assessor were added after those paid observations and still need their own fresh live validation.

On 25 November 2026 the post-change invoice review returned a successful CLI envelope with no structured output, empty model usage and zero billed SDK cost. A diagnostic repeat identified **HTTP 401, invalid external API key**. Both runs correctly remained `needs-review`; invalid zero usage is now reported as unknown cost rather than a free successful result. The silent native model-list control still returned five entries and zero input turns. Provider-backed task, alias and delegation reruns are waiting for a replacement key in the ignored workspace `.env`.

## Current validation and remaining work

On 25 November 2026, the free routing harness passed all **104 authored task/strategy cases** with zero SDK queries and zero network attempts. Focused routing, audio and browser checks passed. The 390px panel comparison stays within the viewport. Distinct concept and walkthrough SVGs were rendered and visually reviewed. Three source-bound Yash clips were recorded; decode, word timing, hashes, volume and browser player checks passed. They remain `recorded-needs-listening` until human review. Ruff and focused mypy passed. The tutorial contract passed after restoring its required heading and CLI command. A full regression attempt showed one early failure in the global concept-snippet mypy check, which passed in isolation; that full attempt was interrupted during the slow browser section. A complete clean offline gate is still required.

Lesson 59 remains **not certified**. The remaining contract work includes provider-backed reruns after the key replacement, complete regression results, any uncovered API or browser gaps, human audio listening and independent student acceptance. Lesson 60 is gated on the provider-backed and offline checks.
