"""Pin reviewed Lesson 51 source narration to exact code excerpts."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_offline import offline_code

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The suite reserves its own temporary store and executes the fixed manifest sequentially. Each case calls the real host contract and returns an assertion row. The complete report requires every case, every passing observation, zero model calls and owned cleanup. A filtered group is useful for diagnosis, but cannot earn the complete check.",
    "The fake query yields normalized synthetic envelopes. The host consumer admits only the known lookup order and executes a real scoped store snapshot. It correlates the exact tool call and result identifiers, checks the terminal state and closes the fake query. This proves host handling of injected input, not a live model decision.",
    "The evaluator requires sixteen ordered passing cases, no mutation, zero model calls, zero actual billing and cleanup. The mutation challenge changes only the observed denial code, so its one failing assertion remains visible. Synthetic replay cost is labeled separately from actual provider billing.",
)
IDS = ("suite", "consumer", "evaluator")


def main() -> None:
    source_path = "agent_lab/offline_lab.py"
    source = (ROOT / source_path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    digest = hashlib.sha256(source.encode()).hexdigest()
    sections = [{"id": identifier, "title": title, "path": source_path,
                 "start_line": row["start_line"], "end_line": row["end_line"],
                 "reviewed_source_sha256": digest, "spoken_text": spoken}
                for identifier, title, row, spoken in zip(
                    IDS, ("Run the suite", "Consume the fake query", "Evaluate complete evidence"),
                    offline_code(), TEXT, strict=True)]
    payload = {"lesson": 51, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recorded-needs-listening",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_51_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_49_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_51_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-51-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 51, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
