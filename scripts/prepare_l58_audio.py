"""Pin Lesson 58 narration to the current three source excerpts."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = ("search", "refund", "native")
TITLES = ("Rank the local catalog", "Record one exact refund", "Verify native discovery")
TEXT = (
    "This local scorer explains why clear refund metadata is easy to find in a catalog of sixty-four tools. It tokenizes the query, gives three points for a name match, two for a search hint and one for a description. The vague billing operation has no refund hint, so a broad refund query cannot find it. An exact select query still resolves it. These scores are teaching estimates, not native ToolSearch ranking or billed token counts.",
    "The refund handler accepts only the synthetic invoice INV-2042, exactly forty-nine hundred euro cents, currency EUR and reason duplicate-charge. It reloads an owned ledger under a run UUID. With a lock, the first valid call writes receipt RF-2042-1 and its tool call ID; a duplicate returns already-recorded. The host independently reloads and hashes the ledger before awarding a check.",
    "The native run registers sixty-four in-process MCP tools and enables ToolSearch. The pre-use hook and permission callback admit only search and the exact refund input. The host requires a structured tool reference result before the refund handler, a matching tool result and ledger receipt, one successful SDK terminal and bounded cost. A model statement alone does not prove discovery or mutation.",
)
ANCHORS = (("agent_lab/tool_search_lab.py", "def search(", 32),
           ("agent_lab/tool_search_lab.py", "def refund(", 25),
           ("agent_lab/tool_search_native.py", "async def live(", 42))


def main() -> None:
    sections = []
    for identifier, title, (path, marker, length), spoken in zip(IDS, TITLES, ANCHORS, TEXT, strict=True):
        source = (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        lines = source.splitlines()
        start = next(i for i, line in enumerate(lines, 1) if line.startswith(marker))
        sections.append({"id": identifier, "title": title, "path": path,
                         "start_line": start, "end_line": min(start + length - 1, len(lines)),
                         "reviewed_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                         "spoken_text": spoken})
    payload = {"lesson": 58, "status": "reviewed-script", "language": "en",
               "voice_requested": "Yash (Inworld)", "audio_status": "recording-pending",
               "sections": sections}
    (ROOT / "agent_lab/content/lesson_58_narration.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "agent_lab/content/lesson_58_inworld_settings.json").write_bytes(
        (ROOT / "agent_lab/content/lesson_57_inworld_settings.json").read_bytes())
    manifest = ROOT / "public/audio/code/lesson-58-manifest.json"
    if not manifest.exists():
        manifest.write_text(json.dumps({"lesson": 58, "entries": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
