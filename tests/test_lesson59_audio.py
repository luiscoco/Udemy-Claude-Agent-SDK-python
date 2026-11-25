"""Lesson 59 narration is bound to reviewed source and recorded media."""

import hashlib
import json

from agent_lab.config import ROOT
from agent_lab.foundations import source_sections
from agent_lab.lesson59_audio import clip_for_section
from scripts.lesson59_audio import verify_published


def test_three_source_bound_yash_clips_decode_and_match_timings() -> None:
    sections = source_sections(59)
    script = json.loads((ROOT / "agent_lab/content/lesson_59_narration.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "public/audio/code/lesson-59-manifest.json").read_text(encoding="utf-8"))
    assert script["status"] == "reviewed-script"
    assert script["audio_status"] == "recorded-needs-listening"
    assert len(sections) == len(script["sections"]) == len(manifest["entries"]) == 3
    for index, section in enumerate(sections):
        clip = clip_for_section(index, section["path"], section["start"], section["end"])
        assert clip and clip.endswith(".mp3")
        assert clip_for_section(index, section["path"], section["start"] + 1, section["end"]) is None
        authored = script["sections"][index]
        entry = next(row for row in manifest["entries"] if row["section"] == authored["id"])
        assert hashlib.sha256((ROOT / entry["audio_path"]).read_bytes()).hexdigest() == entry["audio_sha256"]
        verify_published(entry, authored)
