"""Recorded lesson 43 narration must match its reviewed source and timing."""

import json
from pathlib import Path

from agent_lab.foundations import source_sections
from agent_lab.lesson43_audio import clip_for_section
from scripts.lesson43_audio import media_duration, plan, reviewed_sections, verify_published


def test_lesson43_clips_match_current_source() -> None:
    script, settings = reviewed_sections()
    manifest = json.loads(Path("public/audio/code/lesson-43-manifest.json").read_text(encoding="utf-8"))
    sections = source_sections(43)
    assert len(sections) == len(manifest["entries"]) == 3
    assert plan(script, settings)["total_characters"] == 1438
    for index, section in enumerate(script["sections"]):
        entry = next(item for item in manifest["entries"] if item["section"] == section["id"])
        verify_published(entry, section)
        visible = sections[index]
        assert clip_for_section(index, visible["path"], visible["start"], visible["end"])
        assert media_duration(Path(entry["audio_path"])) > 0
