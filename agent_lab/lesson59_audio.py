"""Expose only verified Lesson 59 source-bound narration to the Python tab."""

import hashlib
import json
from pathlib import Path

from agent_lab.config import ROOT

MANIFEST = ROOT / "public/audio/code/lesson-59-manifest.json"
SCRIPT = ROOT / "agent_lab/content/lesson_59_narration.json"
SETTINGS = ROOT / "agent_lab/content/lesson_59_inworld_settings.json"
SECTION_IDS = ("keys", "metrics", "native")


def clip_for_section(index: int, path: str, start: int, end: int) -> str | None:
    if not 0 <= index < len(SECTION_IDS):
        return None
    try:
        script = json.loads(SCRIPT.read_text(encoding="utf-8"))
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        section = next(row for row in script["sections"] if row["id"] == SECTION_IDS[index])
        entry = next(row for row in manifest["entries"] if row["section"] == SECTION_IDS[index])
        if (section["path"], section["start_line"], section["end_line"]) != (path, start, end):
            return None
        source = (ROOT / path).resolve()
        if not source.is_relative_to(ROOT / "agent_lab"):
            return None
        normalized = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        source_hash = hashlib.sha256(normalized.encode()).hexdigest()
        if source_hash != section["reviewed_source_sha256"] or entry["source_sha256"] != source_hash:
            return None
        if (entry["text_sha256"] != hashlib.sha256(section["spoken_text"].encode()).hexdigest()
                or entry["settings"] != settings):
            return None
        allowed = (ROOT / "public/audio/code").resolve()
        audio = (ROOT / entry["audio_path"]).resolve()
        timing = (ROOT / entry["timing_path"]).resolve()
        if not audio.is_relative_to(allowed) or not timing.is_relative_to(allowed):
            return None
        if hashlib.sha256(audio.read_bytes()).hexdigest() != entry["audio_sha256"]:
            return None
        if hashlib.sha256(timing.read_bytes()).hexdigest() != entry["timing_sha256"]:
            return None
        if not isinstance(json.loads(timing.read_text(encoding="utf-8")).get("cues"), list):
            return None
        return "/assets/audio/code/" + Path(entry["audio_path"]).name
    except (OSError, ValueError, KeyError, StopIteration):
        return None
