"""Check packaged Lesson 58 media decodes, aligns, and contains audible signal."""

import json
import re
import subprocess

from agent_lab.config import ROOT
from scripts.lesson58_audio import verify_published


def main() -> None:
    script = json.loads((ROOT / "agent_lab/content/lesson_58_narration.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "public/audio/code/lesson-58-manifest.json").read_text(encoding="utf-8"))
    assert len(script["sections"]) == len(manifest["entries"]) == 3
    for section in script["sections"]:
        entry = next(row for row in manifest["entries"] if row["section"] == section["id"])
        verify_published(entry, section)
        audio = ROOT / entry["audio_path"]
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio),
                                "-af", "volumedetect", "-f", "null", "NUL"],
                               capture_output=True, text=True, check=True)
        maximum = re.search(r"max_volume:\s*(-?[\d.]+) dB", probe.stderr)
        if maximum is None or float(maximum.group(1)) < -50:
            raise ValueError(f"Silent or unreadable narration: {section['id']}")
        timing = json.loads((ROOT / entry["timing_path"]).read_text(encoding="utf-8"))
        print(json.dumps({"section": section["id"], "maxDb": float(maximum.group(1)),
                          "cues": len(timing["cues"]), "audioSha256": entry["audio_sha256"]}))


if __name__ == "__main__":
    main()
