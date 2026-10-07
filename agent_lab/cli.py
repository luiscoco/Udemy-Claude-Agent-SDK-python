"""One command starts the app or runs any lesson independently of its UI."""

import argparse
import asyncio
import json

from agent_lab.config import Settings
from agent_lab.curriculum import LESSONS
from agent_lab.models import RunRequest
from agent_lab.runtime import RunService


async def run_lesson(lesson_id: int, request: RunRequest | None = None) -> int:
    service = RunService()
    try:
        handle = service.start(lesson_id, request or RunRequest())
        exit_code = 0
        async for event in service.events(handle):
            payload = event.model_dump()
            payload["data"].pop("control_token", None)
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            if event.kind == "question":
                # No interactive approval is fabricated by a headless worker.
                print("Use the browser UI to answer this live question.", flush=True)
                await service.cancel(handle)
            if event.kind == "done" and event.data["status"] != "completed":
                exit_code = 1
        return exit_code
    finally:
        await service.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Python Claude Agent SDK Lab")
    subcommands = parser.add_subparsers(dest="command", required=True)
    server = subcommands.add_parser("serve", help="Start FastAPI and NiceGUI")
    server.add_argument("--host", default=None)
    server.add_argument("--port", type=int, default=None)
    server.add_argument("--native", action="store_true")
    lesson = subcommands.add_parser("lesson", help="Run a standalone lesson")
    lesson.add_argument("id", type=int, choices=range(1, 76))
    lesson.add_argument("--live", action="store_true")
    lesson.add_argument("--prompt", default="")
    subcommands.add_parser("list", help="List the curriculum")
    subcommands.add_parser("doctor", help="Check SDK and CLI installation without a model call")
    arguments = parser.parse_args()
    if arguments.command == "doctor":
        from agent_lab.doctor import diagnose

        print(json.dumps(diagnose(), indent=2))
    elif arguments.command == "list":
        for item in LESSONS.values():
            print(f"{item.id:2}. {item.title}")
    elif arguments.command == "lesson":
        raise SystemExit(
            asyncio.run(
                run_lesson(
                    arguments.id,
                    RunRequest(
                        mode="live" if arguments.live else "offline",
                        prompt=arguments.prompt,
                        max_turns=LESSONS[arguments.id].max_turns,
                        max_budget_usd=LESSONS[arguments.id].max_budget_usd,
                    ),
                )
            )
        )
    else:
        import uvicorn

        from agent_lab.api import create_app

        settings = Settings()
        app = create_app(RunService(settings))
        if arguments.native:
            from nicegui import app as nice_app

            nice_app.native.start_args["debug"] = False
            from nicegui.native import native_mode

            native_mode.activate(
                "http",
                arguments.host or settings.host,
                arguments.port or settings.port,
                "Python Agent Lab",
                1200,
                800,
                False,
                False,
            )
        uvicorn.run(app, host=arguments.host or settings.host, port=arguments.port or settings.port)


if __name__ == "__main__":
    main()
