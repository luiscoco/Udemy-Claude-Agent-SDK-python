# Lesson 58 tool search and large catalogs

The owned synthetic MCP server advertises 64 tools across eight domains. The local scorer and load plan are teaching estimates. They do not claim to reproduce native ToolSearch ranking, SDK context tokenization, or billing.

The refund is fixed to `INV-2042`, 4,900 EUR cents and reason `duplicate-charge`. A valid call writes one `RF-2042-1` entry under a fresh run UUID. Duplicate or wrong calls leave the ledger unchanged. A native pass requires a structured ToolSearch reference before the exact refund call, both permission gates, a matching tool result, host-reloaded ledger and one successful terminal under the $0.15 stop threshold.

Free command: `python scripts/tool_search_check.py`. Paid command: `python scripts/live_tool_search_check.py --live --budget 1 --summary`. Separate zero-model-input context controls: `python scripts/measure_tool_search_context.py --live --summary`. Silent controls can still produce SDK control traffic.

On 2026-11-09, the native discovery scenario passed at **$0.009226** in its SDK terminal cost field. The separate deferred and eager silent measurements each reported 64 MCP tools and zero model input turns. Deferred reported **917** total context tokens; eager reported **6,311**. Both returned zero per-tool `isLoaded` flags despite the eager total increase, so this SDK flag discrepancy is retained as an observation rather than being presented as resolved. Three Yash clips were recorded and source-bound; human listening remains pending.

The API native discovery scenario also passed after rejecting a request without consent; its SDK terminal cost field was **$0.009252**. A separate live Stop probe returned 202 and an interrupted, closed `needs-review` report before any terminal cost was available. Stop timing does not establish cancellation during model inference.

The final uninterrupted offline regression passed **2,050 tests with 22 expected skips**. Ruff, focused mypy and offline wheel build passed. The lesson remains marked `not-certified` in the parity inventory until the context flag discrepancy, human audio listening and independent student acceptance are resolved.
