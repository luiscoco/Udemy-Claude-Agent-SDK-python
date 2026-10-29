# M15 · Ask, select and read

**Goal:** Use a four-step workspace (Ask, Select, Build, Download) with free prepared answers.

## Implement

Nothing yet. Read `publisher.py`, this README and `prompt_library.json` (173 prompts in 17 sections).

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run `uv run agent-lab serve` and open http://127.0.0.1:8080/publish.
2. Pick a section and a suggested prompt: it only fills the box. Send it in **Prepared** mode.
3. Send a second, different prompt. Switch between both in **Saved answers**: every source label changes.
4. Read the code panel: it has a language label, colors and its own horizontal scroll.
5. Check the header controls: Text size and Appearance are remembered after a reload.
6. Run `uv run agent-lab publish check`: 1 test passes and the rest are skipped.

## Expected result

Two distinct prepared answers are labelled PREPARED SAMPLE, cost nothing and never look like live results.

## Check

```shell
uv run agent-lab publish check
```

## Hints

1. A prepared answer is a fixed teaching sample with zero model calls, not a tailored answer.
2. The API key stays in the server's `.env`; nothing in the page can read it.

## Quiz

- **Why keep only the latest 40 answers?**
  Bounded state: memory and disk stay predictable.
- **What must change when you select another answer?**
  Every source label, and any old artifact preview is cleared.

Related lesson: [lesson 1](http://127.0.0.1:8080/?lesson=1).
