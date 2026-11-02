"""One command starts the app or runs any lesson independently of its UI."""

import argparse
import asyncio
import json
from pathlib import Path

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


def check_project(command: str, reference: bool) -> int:
    """Run a milestone project's stage checks against the student's file or the reference."""
    import os
    import subprocess
    import sys
    from typing import Literal

    from agent_lab import evaluation_studio, publishing_studio, study_coach

    implementation: Literal["learner", "reference"] = "reference" if reference else "learner"
    project, path, variable = {
        "coach": (
            study_coach.PROJECT,
            study_coach.coach_path(implementation),
            "COACH_IMPLEMENTATION",
        ),
        "studio": (
            evaluation_studio.PROJECT,
            evaluation_studio.studio_path(implementation),
            "STUDIO_IMPLEMENTATION",
        ),
        "publish": (
            publishing_studio.PROJECT,
            publishing_studio.publisher_path(implementation),
            "PUBLISHER_IMPLEMENTATION",
        ),
    }[command]
    print(f"Checking {path} ...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", str(project)],
        env=os.environ | {variable: implementation},
    )
    return result.returncode


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
    lesson.add_argument("--prompt", default=None)
    lesson.add_argument("--follow-up", default=None)
    lesson.add_argument("--lesson-options-file", default=None, help="JSON file with this lesson's experiment options")
    lesson.add_argument(
        "--scenario", default="success", help="An offline scenario offered by the selected lesson"
    )
    subcommands.add_parser("list", help="List the curriculum")
    subcommands.add_parser("doctor", help="Check SDK and CLI installation without a model call")
    projects = {
        "coach": ("Study Coach milestone project", "coach.py"),
        "studio": ("Agent Evaluation Studio milestone project", "studio.py"),
        "publish": ("Agent Publishing Studio milestone project", "publisher.py"),
    }
    for command, (help_text, filename) in projects.items():
        project = subcommands.add_parser(command, help=help_text)
        project.add_argument("action", choices=["check"])
        project.add_argument(
            "--reference", action="store_true", help=f"check the reference, not your {filename}"
        )
    arguments = parser.parse_args()
    if arguments.command in projects:
        raise SystemExit(check_project(arguments.command, arguments.reference))
    if arguments.command == "doctor":
        from agent_lab.doctor import diagnose

        print(json.dumps(diagnose(), indent=2))
    elif arguments.command == "list":
        for item in LESSONS.values():
            print(f"{item.id:2}. {item.title}")
    elif arguments.command == "lesson":
        options = {}
        if arguments.lesson_options_file:
            try:
                options_path = Path(arguments.lesson_options_file)
                if options_path.stat().st_size > 20000:
                    raise ValueError("Lesson options file is too large.")
                options = json.loads(options_path.read_text(encoding="utf-8-sig"))
                if not isinstance(options, dict):
                    raise ValueError("Use a JSON object for lesson options.")
            except (OSError, ValueError) as exc:
                parser.error(f"Cannot load lesson options: {exc}")
        raise SystemExit(
            asyncio.run(
                run_lesson(
                    arguments.id,
                    RunRequest(
                        mode="live" if arguments.live else "offline",
                        prompt=arguments.prompt
                        if arguments.prompt is not None
                        else LESSONS[arguments.id].prompt
                        if arguments.id <= 14
                        else "",
                        scenario=arguments.scenario,
                        lesson_options=options,
                        follow_up=arguments.follow_up if arguments.follow_up is not None else RunRequest().follow_up,
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
