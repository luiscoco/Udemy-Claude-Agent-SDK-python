"""Recorded Lesson 53 narration stays bound to the reviewed source and timing."""

import json
from pathlib import Path

from agent_lab.foundations import source_sections
from agent_lab.lesson53_audio import clip_for_section
from scripts.lesson53_audio import plan, reviewed_sections, verify_published


def test_lesson53_audio_matches_source_and_timing() -> None:
    script, settings = reviewed_sections()
    manifest = json.loads(Path("public/audio/code/lesson-53-manifest.json").read_text(encoding="utf-8"))
    sections = source_sections(53)
    assert len(sections) == len(manifest["entries"]) == 3
    assert plan(script, settings)["total_characters"] == 1222
    for index, section in enumerate(script["sections"]):
        entry = next(item for item in manifest["entries"] if item["section"] == section["id"])
        verify_published(entry, section)
        visible = sections[index]
        assert clip_for_section(index, visible["path"], visible["start"], visible["end"])
