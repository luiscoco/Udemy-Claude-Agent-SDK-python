"""Pin reviewed Lesson 55 narration to the visible Python source excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_upgrading import code_excerpts

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The runtime inventory reads the declared Python package pin, the locked version, installed package metadata, and three callable public exports. It also hashes the project and lock bytes. This inspection never queries Claude or changes the environment. Agreement among the pin, lock and installed version is a prerequisite for the workshop's automatic check, but it does not establish that a future SDK candidate will work.",
    "The stream adapter checks the authored candidate records as application contracts. It requires one initialized session, an owned Read of fixture dot text, a return with the same call ID and fixture evidence, a completed task notification, and one successful non-error terminal with a nonempty result. An unknown additive event is counted and tolerated. Missing, duplicated, foreign, renamed or error evidence fails the gate.",
    "The transition handler recomputes the selected candidate's assessment and current installed inventory for each action. Only an eligible checked candidate may start a simulated canary, and only an eligible canary may be promoted. Rollback is allowed from canary or promoted state, including when the candidate now fails. The submitted state is a teaching input; no package installation or deployment occurs.",
)
IDS = ("inventory", "adapter", "transition")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Inspect the installed SDK", "Adapt fixture stream evidence", "Rehearse state changes"),
        code_excerpts(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 55, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_55_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_54_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_55_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-55-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 55, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
