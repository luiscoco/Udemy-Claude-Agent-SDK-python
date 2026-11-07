"""Pin reviewed Lesson 52 source narration to exact Python excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_evals import eval_code

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The comparison first rejects incomplete or incompatible reports. It keeps synthetic and live provenance separate. For each case, hard scope and money failures matter immediately. Other drops need both a meaningful rate decline and Fisher evidence; a drop with weak evidence is suspect. Wilson intervals and separate agent and judge costs show what these tiny trials can and cannot establish.",
    "The calibration runs eight human labelled replies through five heuristic criteria. It counts forty decisions, positive marginals and chance agreement before computing Cohen kappa. Two invented claims remain lenient errors because the keyword heuristic misses their meaning. The advisory trust value belongs only to this small teaching set; it does not certify the optional model judge.",
    "Promotion reloads the retained run and checks the eligibility gate before writing. A reviewed digest detects changed measurements, and a missing or ineligible run is rejected. The write targets only the matching provenance and judge baseline and records an audit note. Opening the baseline or clicking the button alone cannot promote an agent.",
)
IDS = ("comparison", "calibration", "promotion")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(
        IDS, ("Compare trial evidence", "Calibrate the heuristic", "Promote reviewed reports"),
        eval_code(), TEXT, strict=True,
    ):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 52, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_52_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_49_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_52_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-52-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 52, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
