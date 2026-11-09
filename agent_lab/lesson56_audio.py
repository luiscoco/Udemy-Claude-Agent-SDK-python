"""Expose only verified packaged lesson 56 narration to the source panel."""

import hashlib
import json
from pathlib import Path

from agent_lab.config import ROOT

MANIFEST = ROOT / "public/audio/code/lesson-56-manifest.json"
SCRIPTS = ROOT / "agent_lab/content/lesson_56_narration.json"
SETTINGS = ROOT / "agent_lab/content/lesson_56_inworld_settings.json"
SECTION_IDS = ("reducer", "grader", "native")


def clip_for_section(index: int, path: str, start: int, end: int) -> str | None:
    if not 0 <= index < len(SECTION_IDS):
        return None
    try:
        script = json.loads(SCRIPTS.read_text(encoding="utf-8"))
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        section = next(item for item in script["sections"] if item["id"] == SECTION_IDS[index])
        entry = next(item for item in manifest["entries"] if item["section"] == SECTION_IDS[index])
        if (section["path"], section["start_line"], section["end_line"]) != (path, start, end):
            return None
        source = (ROOT / path).resolve()
        if not source.is_relative_to(ROOT / "agent_lab"):
            return None
        source_bytes = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").encode()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        if source_hash != section["reviewed_source_sha256"] or entry["source_sha256"] != source_hash:
            return None
        if entry["text_sha256"] != hashlib.sha256(section["spoken_text"].encode()).hexdigest() or entry["settings"] != settings:
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
