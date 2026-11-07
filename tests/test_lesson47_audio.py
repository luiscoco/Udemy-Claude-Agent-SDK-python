"""Recorded Lesson 47 narration must match its current source."""

import json
from pathlib import Path

from agent_lab.foundations import source_sections
from agent_lab.lesson47_audio import clip_for_section
from scripts.lesson47_audio import plan, reviewed_sections, verify_published


def test_lesson47_audio_matches_source_and_timing() -> None:
    script, settings = reviewed_sections()
    manifest = json.loads(Path("public/audio/code/lesson-47-manifest.json").read_text(encoding="utf-8"))
    sections = source_sections(47)
    assert len(sections) == len(manifest["entries"]) == 3
    assert plan(script, settings)["total_characters"] == 1362
    for index, section in enumerate(script["sections"]):
        entry = next(item for item in manifest["entries"] if item["section"] == section["id"])
        verify_published(entry, section)
        visible = sections[index]
        assert clip_for_section(index, visible["path"], visible["start"], visible["end"])
