# Lesson 59 model routing checkpoint

The Python portal now has thirteen fixed tasks, eight prepared strategies, independent answer keys, synthetic cost and duration labels, a bounded `/api/c59` API and a dedicated NiceGUI panel. The prepared fixture comparison deliberately leaves `light` and `cascade` in `needs-review`; six other strategies pass. The confident `001` draft for power-mod is rejected by its computed key even though the escalation heuristic does not flag it.

The native implementation uses a fresh owned SDK query for each task, a fixed structured schema, a USD 0.10 per-query stop threshold and a 90-second deadline. Review switches from light to deep within one stable session. The separate model-list, alias-resolution and expert-delegation controls never award the routing-suite check. The expert gate accepts the installed CLI's observed `Task` advertisement with an emitted `Agent` call only when the bounded custom expert and matched result are present.

## Observations made on 14 November 2026

- Invoice review passed: one SDK query, stable session across both turns, actual `set_model` to the configured deep ID, independent invoice grade accepted, **USD 0.012003** SDK query-pipeline estimate.
- Silent installed-CLI model metadata returned five entries with zero model input turns.
- Three invoice alias probes passed with observed Sonnet usage in each, **USD 0.0075033** SDK query-pipeline estimate in total.
- The first expert probe was `needs-review`: the CLI advertised `Task` but emitted `Agent`; the gate denied it. After correcting that compatibility rule, a fresh expert probe passed with an admitted `Agent` call, matching successful result, accepted lineup grade and both light/deep model usage entries, **USD 0.01753665** SDK query-pipeline estimate.

These reports are local under ignored `.lab-data/lesson-59` and are observations of the installed SDK, not a provider invoice or an independent expert execution audit. The new raw-terminal billing recomputation and special assessor were added after those paid observations and still need their own fresh live validation.

## Current validation and remaining work

On 25 November 2026, the focused routing and exercise tests passed **51 tests**; the Lesson 59 offline course acceptance check passed separately. Ruff and focused mypy passed for the new routing modules. A wider learning test run hit an unrelated Lesson 39 timing failure; Lesson 39 passed alone. The complete post-change offline regression is pending.

Lesson 59 remains **not certified**. The remaining contract work includes final live reruns after the raw-terminal assessor change, full API and browser acceptance coverage, distinct concept and walkthrough visuals, source-bound Yash narration clips, a visual review at 390px, the full offline regression, and independent student acceptance. Lesson 60 is gated on closing these items.
