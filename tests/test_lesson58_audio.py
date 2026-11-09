"""Lesson 58 clips must stay bound to reviewed source and media bytes."""

import hashlib
import json

from agent_lab.config import ROOT
from agent_lab.foundations import source_sections
from agent_lab.lesson58_audio import clip_for_section


def test_three_source_bound_clips() -> None:
    sections = source_sections(58)
    manifest = json.loads((ROOT / "public/audio/code/lesson-58-manifest.json").read_text(encoding="utf-8"))
    assert len(sections) == len(manifest["entries"]) == 3
    for index, section in enumerate(sections):
        clip = clip_for_section(index, section["path"], section["start"], section["end"])
        assert clip and clip.endswith(".mp3")
        assert clip_for_section(index, section["path"], section["start"] + 1, section["end"]) is None
        entry = next(row for row in manifest["entries"] if row["section"] == ("search", "refund", "native")[index])
        assert hashlib.sha256((ROOT / entry["audio_path"]).read_bytes()).hexdigest() == entry["audio_sha256"]
