"""Pin reviewed Lesson 54 narration to the visible Python source excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_tool_design import code_excerpts

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The catalog handler is shared by direct calls and native model tools. Pydantic validates arguments before the handler runs, so an invalid search never reaches the catalog. Every admitted call receives a unique call ID and a serialized envelope. The byte count comes from that exact UTF eight envelope, including the selected concise or detailed response format. A stale cursor, unknown ID, or empty result has a separate, actionable outcome.",
    "The prepared consumer makes the profile difference observable without model spend. The vague profile calls lookup once and receives the broad catalog. The focused profile searches with exact camping and price filters, follows each returned cursor instead of inventing one, and gets each matching product by stable ID. It saves the calls, returned envelopes, and summary so both response formats can be compared from the same fixture.",
    "The grader checks evidence, not an asserted success label. It requires the immutable fixture hash, admitted matching calls, real result envelopes and hashes, the focused search cursor chain, and the exact product IDs. It also checks that the run finished and cleaned up. Vague lookup remains an observation; only the focused sequence can satisfy the lesson check.",
)
IDS = ("handler", "consumer", "grader")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Validate and measure a tool result", "Follow the returned cursor", "Grade the evidence"),
        code_excerpts(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 54, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_54_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_53_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_54_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-54-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 54, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
