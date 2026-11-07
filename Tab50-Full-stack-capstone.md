# Lesson 50: Full-stack support capstone

Build a scoped synthetic support desk with a persisted conversation, native SDK tools, one-shot refund approval and structured CRM closure.

## Run it

```shell
uv run agent-lab lesson 50
uv run agent-lab serve
```

Open `http://127.0.0.1:8080/?lesson=50` and choose **Run the exercise**. The desk panel uses the same owned store as the `/api/c50` routes. Ada and Bo are classroom fixtures; the customer selector is not production authentication, and a refund changes only the lesson ledger.

Start with **Orders** for Ada. Resume the saved open conversation for **Ticket**. Each operation reads orders again before a write. Try **Refund** twice, denying the first exact proposal and approving the second. Then use **Close to CRM** and **Local evaluations**. Inspect matched call IDs, audit rows, one 1000-cent refund row, closed CRM and unchanged transcript. The three negative Local scenarios deliberately withhold the success verdict.

The command-line runner also uses the persisted desk. Its default intent is Orders; `lesson_options` can select `customer`, `intent`, `conversation_id` and `approval`. The local authored lifecycle creates real owned records and is labelled as local evidence.

## Live Agent SDK

With a private `ANTHROPIC_API_KEY` and `LAB_ENABLE_LIVE=true`, restart the app and choose Live. Confirm each paid chat or CRM close separately. The native chat admits only selected support tools, resumes the SDK session and joins the real tool call/result IDs to the host ledger. A restricted fork creates schema-constrained CRM data without desk tools. One chat is capped at $0.10; use `scripts/desk_live_matrix.py --live --budget 0.50` for the complete bounded journey after local checks pass.

## Source and verification

- `agent_lab/desk_store.py`: scoped persisted conversations, orders, tickets, refunds and audit.
- `agent_lab/desk_approver.py`: exact one-shot pending approval and timeout cleanup.
- `agent_lab/desk_lab.py`: host admission, local operations, close and evaluator.
- `agent_lab/desk_native.py`: native SDK calls, resumed session, restricted CRM fork and terminal evidence.
- `agent_lab/api_desk.py`: strict HTTP contract; `agent_lab/ui_desk.py`: browser controls.

The Python source tab has three source-bound Yash recordings with verified hashes and word timing. The Visual guide and Lab walkthrough show the concept and ordered exercise. Seven questions test scope, fresh reads, one-shot approval, denial, native evidence, CRM and negative evidence.

This Python adaptation does not connect to real customer identity, payment processing or deployed CRM. Offline records are authored host effects. Live evidence is provider-backed only when the native SDK path actually completes.
