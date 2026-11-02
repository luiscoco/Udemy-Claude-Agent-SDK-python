# Lesson 1: query stream and outcome checks

The lesson now has seven explained practice questions: two concept questions, three debugging questions with Python examples, and two visual flow questions. The original two question indices are unchanged, so existing saved answers retain their meaning. Quiz answers, explanations, attempts and the four manual review checkboxes remain separate from automatic run checks.

## Student flow

1. Open lesson 1 and read the concept and reviewed four-section Python source tour.
2. Open **Run exercise**. Keep **Offline Python exercise**, the default prompt and **Success** selected. Run and inspect the ordered fixture messages, assistant text and final result.
3. Try **SDK error** and **Missing final result**. Both contain assistant text, but both should show **Needs review**. A completed host replay does not mean the simulated SDK outcome succeeded. Return to **Success** for a passing check.
4. Answer the knowledge questions in **Learn**. Write your explanation under **Your explanation and evidence**, then choose **Save attempt**. Reload or return through **My Learning** to resume saved work. Mark manual review checkboxes only when you have reviewed the work yourself.

Offline prompts are validated but the recorded assistant text is fixed; it is not an answer generated for your question. Offline mode starts no SDK process and makes no paid call. The CLI also accepts `uv run agent-lab lesson 1 --scenario error` or `--scenario missing-result`.

## Validation and terminal evidence

Lesson 1 trims the prompt and rejects explicit empty, oversized, incorrectly typed and unexpected input before creating a task or workspace. An omitted prompt uses the lesson example. Its defaults and bounds are one turn and a positive budget threshold of at most USD 0.05. Other lessons retain their existing limits. Recorded negative scenarios are rejected for live mode and for other lessons.

The bounded criterion is: **the stream ended with a final SDK result/success and `is_error` was false**. This evaluates the run outcome, not the quality of its prose or the student's challenge.

Optional live mode requires the existing server configuration and credentials. It uses the actual prompt, no tools, no inherited settings, strict MCP configuration, isolated SDK configuration and the existing host deadline. A missing or unsuccessful terminal result fails the run. Session identity is compared with the SDK init message when supplied, and a result followed by extra messages is not accepted as final. Cancellation closes the same run's SDK stream. A budget threshold is not a billing guarantee; inspect actual reported cost and usage. No paid call is needed to read, answer or save work.

The implementation is adapted from the [pinned L01 teaching contract](https://github.com/luiscoco/Udemy-Claude-Agent-SDK-Student-Rebuild/blob/777d8479b62fddf5cd62df86fb048d589ed43a7c/docs/prompts/l01-lesson-1-query.md). Remaining reference differences include shared tab/navigation order, the TypeScript route names, separately produced media and recorded narration. This upgrade does not certify complete reference parity.

The runtime tests inject SDK-shaped producers for success, error, absent result, wrong session, unexpected subtype and messages after a purported terminal result. Browser tests cover desktop and phone scenarios, seven questions, saved answers and attempts, reload and unchanged manual review. Live network behavior still requires a separately authorized manual exercise.
