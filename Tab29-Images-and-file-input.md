# Lesson 29: Images and file input

Construct typed content blocks and isolate uploaded or generated files from the host.

This lesson is part of **SDK fundamentals**. The Python implementation is shared by
the NiceGUI screen, FastAPI endpoints and command-line exercise.

## Run it

Install the environment once with `uv sync --locked`. Then run:

```shell
uv run agent-lab lesson 29
uv run python -m agent_lab.lessons.lesson_29
```

Both commands run **offline host code**. No model is called, no API cost is incurred,
and recorded examples are labelled as fixtures rather than live SDK messages.

For the browser lab, run `uv run agent-lab serve`, then open
[lesson 29](http://127.0.0.1:8080/?lesson=29).

## The concept in code

```python
import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


async def image_turn(path: Path) -> AsyncIterator[dict[str, Any]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("media_type says image/png, so the bytes must be a PNG")
    image = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(data).decode(),
        },
    }
    content = [image, {"type": "text", "text": "Describe this image in one sentence."}]
    yield {
        "type": "user",
        "message": {"role": "user", "content": content},
        "parent_tool_use_id": None,
    }


async def main() -> None:
    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(tools=[], max_turns=1)
    ) as client:
        await client.query(image_turn(Path("workspace/pixel.png")))
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                print(message.result)
```

The concept example shows a typed PNG image and text block. The runnable experiment validates a host-owned red or blue PNG and checks actual SDK responses against the file hash and selected color.

## How the offline lab checks it

Predict the evidence, then run the exercise. A model's description of an action is
not evidence that the action happened.

The lab is `images` in [agent_lab/exercises.py](agent_lab/exercises.py)
(line 1134); the Python source tab shows it below the concept code. Host contracts
are in [agent_lab/services.py](agent_lab/services.py); path and tool permissions are in
[agent_lab/policy.py](agent_lab/policy.py).

## Live Agent SDK exercise

Copy `.env.example` to `.env`, configure `ANTHROPIC_API_KEY`, and explicitly set
`LAB_ENABLE_LIVE=true`. Restart the app and choose **Live Agent SDK**.

```shell
uv run agent-lab lesson 29 --live
```

Suggested prompt:

> Explain image content blocks and why MIME types matter.

The live profile is `query`. Its tools and configuration are in
[agent_lab/image_input_lab.py](agent_lab/image_input_lab.py). The live run validates an owned PNG, sends a typed base64 image plus text through the SDK, and compares red/blue responses with the file hashes.

`ClaudeAgentOptions` uses Python names such as `max_turns`, `max_budget_usd`,
`setting_sources` and `include_partial_messages`. The SDK owns the agent loop;
the host owns validation, tool authority and task lifecycle. The budget option
is a threshold, not an exact billing cap.

## Python edition adaptation

The original exercise builds a one-pixel image block offline. The enhanced live lesson sends a separate validated red or blue PNG through the SDK input stream.

## API and lifecycle

| Endpoint | Purpose |
|---|---|
| `GET /api/lessons/29` | Lesson metadata |
| `POST /api/lessons/29/run` | Collected JSON events |
| `POST /api/lessons/29/stream` | Server-Sent Events |
| `/api/lessons/29/ws` | WebSocket events and cancellation |

Pydantic validates the request before the run starts:

```json
{"mode": "offline", "prompt": "", "max_turns": 4, "max_budget_usd": 0.10}
```

All transports use [RunService](agent_lab/runtime.py). It bounds concurrency,
owns the producer task and closes the SDK connection in the task that opened
it. A run emits one terminal `done` event. Cancellation awaits cleanup before
releasing the run slot.

## Practice

1. Identify trusted host inputs and untrusted model or source data.
2. Change one bounded input and predict whether validation accepts it.
3. Add a failure case and explain how the host should report it.
4. Compare offline evidence with a live run without mistaking fixtures for model output.

## Verification and references

`uv run pytest` executes every offline lesson and checks host policies, tenant
isolation, approvals, dependency failures, cancellation and API validation.
Paid calls are separate, opt-in checks.

- [Official Python Agent SDK reference](https://code.claude.com/docs/en/agent-sdk/python)
- [Python SDK source](https://github.com/anthropics/claude-agent-sdk-python)
- [Setup and migration coverage](README.md)
