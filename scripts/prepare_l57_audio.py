"""Pin reviewed Lesson 57 narration to exact Python worktree source excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_worktrees import code_excerpts

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The host creates a fresh owned repository and commits a known base before adding two separate worker branches. Both workers start before either commit is accepted. Each worker may change exactly one assigned source file. The host verifies the branch, base commit, changed path, exact source bytes and fixed Node behavior before it creates the worker commit. The workers share Git history, so Git operations are serialized while their file work can overlap.",
    "The grader requires the independent scenario to carry two real worker commits, each parented to the base. It checks two serial integrated commits and their parent chain, successful worker and combined Node assertions, clean main, original worker refs and nonforce removal of both worker worktrees. The deliberate conflict is retained for inspection and needs review. A model statement or a partial report cannot satisfy these actual Git and test gates.",
    "The native file gate admits only Read, Write or Edit targeting the existing assigned regular file. Both the pre-use hook and permission callback apply the same exact path decision; Bash, Git commands, delegation and other files are denied. A successful SDK terminal still needs a correlated admitted write or edit and nonerror tool result. The coordinator then independently validates the file, runs Node tests and commits it. The two SDK cost thresholds are stop rules, not prepaid billing caps.",
)
IDS = ("reducer", "grader", "native")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Launch owned workers", "Grade real integration", "Gate native file tools"),
        code_excerpts(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 57, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_57_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_55_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_57_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-57-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 57, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
