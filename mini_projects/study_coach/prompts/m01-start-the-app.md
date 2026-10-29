# M01 · Start the app

**Goal:** Run the course app, open the Study Coach and tell a prepared response from a live one.

## Implement

Nothing yet. Read `coach.py` and the stage table in the README.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run `uv run agent-lab serve` and open http://127.0.0.1:8080/coach.
2. Browse the concept guide: change the route and section, use Previous and Next concept.
3. Ask a question with **Your coach.py** selected: the page tells you to implement stage 2.
4. Switch to **Reference**, choose a shortcut and ask: the answer is a prepared example.
5. Run `uv run agent-lab coach check`: 1 test passes and the rest are skipped.

## Expected result

You can explain that prepared answers come from the lesson content with zero model calls.

## Check

```shell
uv run agent-lab coach check
```

## Hints

1. Prepared answers are authored, so they cannot prove anything about a live model.
2. Look at `prepared_answer` in `agent_lab/study_coach.py`: it only reads lesson content.

## Quiz

- **Where does a prepared answer come from?**
  From this course's lesson content, built by the server; no model is called.
- **Why are later stage tests skipped?**
  `STAGE = 1`: the gate skips tests until you raise STAGE after implementing a stage.

Related lesson: [lesson 1](http://127.0.0.1:8080/?lesson=1).
