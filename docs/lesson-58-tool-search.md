# Lesson 58 tool search and large catalogs

The owned synthetic MCP server advertises 64 tools across eight domains. The local scorer and load plan are teaching estimates. They do not claim to reproduce native ToolSearch ranking, SDK context tokenization, or billing.

The refund is fixed to `INV-2042`, 4,900 EUR cents and reason `duplicate-charge`. A valid call writes one `RF-2042-1` entry under a fresh run UUID. Duplicate or wrong calls leave the ledger unchanged. A native pass requires a structured ToolSearch reference before the exact refund call, both permission gates, a matching tool result, host-reloaded ledger and one successful terminal under the $0.15 stop threshold.

Free command: `python scripts/tool_search_check.py`. Paid command: `python scripts/live_tool_search_check.py --live --budget 1 --summary`. Separate zero-model-input context controls: `python scripts/measure_tool_search_context.py --live --summary`. Silent controls can still produce SDK control traffic.

On 2026-11-09, the native discovery scenario passed at **$0.009226** in its SDK terminal cost field. The separate deferred and eager silent measurements each reported 64 MCP tools and zero model input turns. Deferred reported **917** used context tokens and **6,312** deferred MCP definition tokens; eager reported **6,311** used context tokens, including **6,303** in the `mcp_tools` category. Both returned zero per-tool `isLoaded` flags, so the lab now grades eager/deferred loading from the SDK category `kind` and reports the flags separately. Three Yash clips were recorded and source-bound; human listening remains pending.

The API native discovery scenario also passed after rejecting a request without consent; its SDK terminal cost field was **$0.009252**. A separate live Stop probe returned 202 and an interrupted, closed `needs-review` report before any terminal cost was available. Stop timing does not establish cancellation during model inference.

On 2026-11-10, a third silent native measurement pinned only the refund tool with `alwaysLoad`: **144** MCP definition tokens were `used`, **6,168** were `deferred`, and exactly one per-tool `isLoaded` flag was true. This confirms the intended one-tool pinning behavior in the installed SDK. The three measurements are context snapshots, not billed token totals.

All three packaged MP3s passed FFmpeg decode, reviewed-word cue alignment, source and media hash checks, and non-silent volume checks. The clips contain 75, 59 and 61 timed words respectively, with maximum levels of −0.3, −0.3 and −0.4 dB. These machine checks do not replace human listening.

The last uninterrupted offline regression before the category clarification passed **2,050 tests with 22 expected skips**. Ruff, focused mypy and offline wheel build passed after the clarification. A later full rerun had one Lesson 48 browser timing failure among **2,051 passes and 22 skips**; that test passed alone. A subsequent fail-fast rerun encountered a Lesson 17 subprocess timeout, which also passed alone. The post-change full suite is therefore unconfirmed. The lesson remains marked `not-certified` pending that regression, human audio listening and independent student acceptance.
