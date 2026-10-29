# M10 · Compare baseline and guided instructions

**Goal:** Compare instruction variants on the same case.

## Implement

`build_system_prompt(variant, depth, mcp_mode)`: join the variant (1-2000 characters), the depth instruction, a source rule for none, docs or custom, and a rule against claiming tool calls that are not visible. Raise ValueError for anything invalid. Set `STAGE = 3`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Choose **Compare baseline and guided**: both composed prompts and answers appear side by side.
2. Change only one thing (the variant, or the depth) and compare again.

## Expected result

You can name the instruction that changed and the difference it made in the answer.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. Keep stable rules in the system prompt and the changing question in the user prompt.
2. Change one variable at a time, or you cannot attribute the difference.

## Quiz

- **Why compare variants on the same case?**
  Holding the case fixed attributes the difference to the instructions.
- **Where does the anti-hallucination rule live?**
  In the system prompt for every variant, so no comparison drops it.

Related lesson: [lesson 9](http://127.0.0.1:8080/?lesson=9).
