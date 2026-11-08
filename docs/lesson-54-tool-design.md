# Lesson 54 tool design lab

The lab uses one immutable five-product EUR catalog. The vague profile exposes a broad `lookup(q)` tool. The focused profile exposes exact `catalog_search` filters, snapshot-bound pagination, and `catalog_get` by stable SKU. Both profiles return concise or detailed serialized result envelopes; the page measures their actual UTF-8 bytes and handler time without presenting those values as tokens or model cost.

`/api/c54/facts`, `/code`, `/call`, `/run`, `/active`, and `/stop` expose strict schemas, direct calls, streamed free and paid runs, and cancellation. Invalid input fails before handler execution. Cursor, missing SKU, and empty-result outcomes are distinct. The prepared consumer runs all four profile and format combinations without network or model calls. The focused grade checks admitted calls, matched result identities and hashes, the returned cursor chain, exact SKUs, and cleanup.

The optional paid path exposes only the selected read-only tools to native Haiku, with a pre-use guard, bounded calls, time, and SDK cost. `scripts/tool_design_check.py` runs the free matrix; `--live --budget 0.5` runs both native profiles. The browser supports direct tool calls, profile comparison, evidence inspection, paid consent, Stop, seven explained questions, three source excerpts with Yash clips, and two diagrams. The 390px browser flow and targeted tests pass. See [live acceptance](live-acceptance.md) and [narration](lesson-54-narration.md).

The final uninterrupted full offline regression passed with 2,016 tests and 18 expected skips. The synthetic catalog illustrates the design tradeoff; its measured bytes do not predict token usage or vendor bills. Human listening and independent student acceptance remain open.
