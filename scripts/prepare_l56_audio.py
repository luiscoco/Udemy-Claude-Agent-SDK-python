"""Pin reviewed Lesson 56 narration to exact Python team source excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_teams import code_excerpts

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The free reducer creates fresh member, task, inbox and receipt state for each request. Claims require an idle member, an unowned task and completed dependencies. A send queues one envelope; an identical repeat retains that envelope, while a conflicting ID is refused. Delivery and acknowledgment change inbox status, but neither completes a task. Rejected commands still add an ordered receipt and leave the underlying team state unchanged.",
    "The offline grader recomputes the selected command history and compares the entire state and history hash with the report. It then requires exact research and review owners and evidence, shutdown workers, acknowledged peer evidence and an accepted final cleanup receipt. The five intentional refusals remain visible in the passing walkthrough. A partial, edited or forged run cannot borrow a previous passing result.",
    "The native observer is a separate paid named-subagent demonstration. It creates one isolated run, accepts only the advertised Agent or Task spawning tool and SendMessage through a pre-use hook, and records actual tool IDs and results across two turns. It retains cumulative SDK cost and closes the owned stream. A SendMessage attempt, transport result or answer containing thirty seven does not independently verify delivery or worker completion, and this is not an interactive native team.",
)
IDS = ("reducer", "grader", "native")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Reduce commands into team state", "Grade the completed replay", "Observe named SDK tools"),
        code_excerpts(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 56, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_56_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_55_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_56_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-56-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 56, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
