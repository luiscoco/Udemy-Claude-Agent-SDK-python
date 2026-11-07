"""Pin the reviewed Lesson 50 source narration before recording."""

import hashlib
import json
from pathlib import Path

from agent_lab.api_desk import desk_code

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "The snapshot method loads the owned desk data, then keeps only conversations, tickets, refunds and audit rows belonging to the host-selected customer. Orders come from the fixed synthetic fixture for that same customer. The model never supplies the customer scope through a tool argument. This view makes cross-customer records invisible in the lesson report.",
    "The approval waiter accepts only the pending exact call. It waits for one answer with a timeout. Whether approval succeeds, is denied, times out or is cancelled, the pending entry is removed. A later call cannot reuse that decision. The refund handler also checks the run, conversation, call and token before it writes an effect.",
    "A local CRM close first requires the selected open conversation and copies its messages. It builds strict structured CRM data, persists the close and reloads the saved state. Success requires a closed status, the same CRM record and an unchanged transcript. The native close uses a restricted fork with no support tools, then checks the same host facts.",
)
IDS = ("scope", "approval", "crm-close")


def main() -> None:
    sections = []
    for identifier, title, row, spoken in zip(IDS, ("Scope saved records", "Settle exact approval", "Close into CRM"), desk_code(), TEXT, strict=True):
        source = (ROOT / row["file"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        sections.append({"id": identifier, "title": title, "path": row["file"],
                         "start_line": row["start_line"], "end_line": row["end_line"],
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 50, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recorded-needs-listening",
               "sections": sections}
    target = ROOT / "agent_lab/content/lesson_50_narration.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settings = ROOT / "agent_lab/content/lesson_49_inworld_settings.json"
    (ROOT / "agent_lab/content/lesson_50_inworld_settings.json").write_bytes(settings.read_bytes())
    manifest = ROOT / "public/audio/code/lesson-50-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 50, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
