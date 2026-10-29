# Agent Publishing Studio milestone project

This checkout includes the completed learner implementation at stage 8, alongside the
reference. The prompts below remain the incremental learning sequence; separate pristine
starter templates are pending. Keep a separate copy when practising from an empty stage.

Turn one saved SDK answer into Word, PDF, SVG and PNG files. Ask, select, build, download:
you implement the contracts in [publisher.py](publisher.py), and the course app runs
**your** file at <http://127.0.0.1:8080/publish>, so every stage unlocks a feature.

| Stage | Prompt | STAGE value |
|---|---|---|
| M15 | [Ask, select and read](prompts/m15-ask-and-select.md) | 1 |
| M16 | [Add a consented live answer](prompts/m16-live-answer.md) | 2 |
| M17 | [Attach sources and see the extracted text](prompts/m17-attach-sources.md) | 3 |
| M18 | [Plan a document or infographic](prompts/m18-plan-an-artifact.md) | 4 |
| M19 | [Build Word and PDF files](prompts/m19-word-and-pdf.md) | 5 |
| M20 | [Build SVG and PNG infographics](prompts/m20-svg-and-png.md) | 6 |
| M21 | [Optional docs MCP and the full workflow](prompts/m21-docs-mcp-and-workflow.md) | 7 |
| M22 | [Style infographics from a PNG reference](prompts/m22-png-style-reference.md) | 8 |

## Run and check

```shell
uv run agent-lab serve                        # open http://127.0.0.1:8080/publish
uv run agent-lab publish check                # checks YOUR publisher.py, stage by stage
uv run agent-lab publish check --reference    # checks the reference; never marks your work done
```

Raise `STAGE` after each stage passes; later tests are skipped until you do. On the page,
switch between **Your publisher.py** and **Reference**; **Reload my code** picks up edits.
PDF and PNG files are rendered by Playwright: run `uv run playwright install chromium` once
(the app also tries an installed Edge or Chrome).

## How it fits together

- `publisher.py` (yours) and `reference/publisher.py` hold the same functions: plain Python
  over dicts and bytes, testable without the SDK. `prompt_library.json` holds 173 prompts in
  17 sections; a prompt only fills the question box.
- `agent_lab/publishing_studio.py` is the server. It owns the API key, the latest 40 answers
  and 40 artifact files in `.lab-data/publishing-studio/`, extracts PDF text in a separate
  process, builds DOCX files and renders PDF and PNG with the network blocked. Downloads are
  served by opaque ids with explicit MIME types; the browser never names a path.
- Prepared answers and prepared plans make zero model calls. Live answers and live planning
  are separate paid calls, each with its own spending cap and fresh consent, plus a third
  consent for the documentation MCP. They need `ANTHROPIC_API_KEY` and
  `LAB_ENABLE_LIVE=true` in `.env`.
- Live answers and plans enable strict MCP configuration, excluding servers inherited
  from project files, user settings or plugins. Answers can use the explicitly approved
  documentation MCP; planning calls load no MCP servers.
- **Download project ZIP** on the page packages this folder (without the reference).

Review every preview for layout and facts before you share a file.

Document exports preserve the selected answer's fenced code. If a code block exceeds
12,000 characters or the document needs more than 60 blocks, split the answer before
exporting; the builder reports an error instead of silently removing code. Infographics
use a bounded, labeled code excerpt, while the document retains the full snippets.
