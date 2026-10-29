# M13 · Record reviews and export evidence

**Goal:** Let a reviewer record a decision and export reproducible evidence.

## Implement

`review_record(run, marks, note)`: one boolean per criterion, a note under 1000 characters, `kind` from the run mode, and `passed` only with every mark and a success result. `export_evidence(records)`: a Markdown table that says prepared fixtures are not live validations. Set `STAGE = 6`.

Keep earlier stages passing and do not change public signatures.

## Try it on the page

1. Run a case, tick the criteria you can confirm, write a note and **Save review**.
2. Review a limited run: even with every box ticked it does not pass.
3. **Export evidence** and read the file: fixtures and live runs are labelled apart.

## Expected result

Reviews are saved with the run, and the exported evidence never calls a fixture a live validation.

## Check

```shell
uv run agent-lab studio check
```

## Hints

1. A review is a human decision; keep it separate from the run's own result.
2. Escape table characters such as | in notes so the export stays readable.

## Quiz

- **Every criterion is ticked but the subtype is error_max_turns. Passed?**
  No: an incomplete run cannot pass.
- **Why label the kind of run in the export?**
  So a reader never mistakes a prepared fixture for live evidence.

Related lesson: [lesson 52](http://127.0.0.1:8080/?lesson=52).
