"""Pin reviewed Lesson 53 source narration to exact Python excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_debugging import debug_code

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "This helper reads only this run's raw debug log. It first distinguishes a missing file from an empty one, then opens a descriptor and checks that the same regular single-link file was opened. It reads one byte beyond the one hundred twenty eight thousand byte export ceiling so truncation is visible. Finally always closes the descriptor and redacts the text before it leaves the host.",
    "The native finalizer closes the stream and raw log descriptor before assembling its bundle. It records stream end and cleanup as distinct host rows, then checks the fixture's before and after hashes independently of the assistant reply. The bundle retains all collected rows and findings, interruption and overflow flags, and a known terminal cost even if a later iterator exception occurred. Only then does the host save the redacted result.",
    "The diagnosis scans captured rows for a first supported cause. A denied pre-use decision points to policy, while a missing-file finding needs an admitted matching Read error and independently absent fixture. An API error checks the terminal isError flag even if its subtype says success. Later exceptions and missing terminals stay visible as separate findings, ordered by their supporting rows.",
)
IDS = ("log", "lifecycle", "diagnosis")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Read a bounded log", "Own the native lifecycle", "Find the first cause"),
        debug_code(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 53, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_53_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_49_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_53_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-53-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 53, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
