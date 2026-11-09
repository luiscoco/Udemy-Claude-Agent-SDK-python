"""Plan or explicitly record reviewed lesson 58 source narration."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_lab.config import ROOT  # noqa: E402

SCRIPT = ROOT / "agent_lab/content/lesson_58_narration.json"
SETTINGS = ROOT / "agent_lab/content/lesson_58_inworld_settings.json"
MANIFEST = ROOT / "public/audio/code/lesson-58-manifest.json"
PRIVATE = ROOT / ".lab-data/lesson-58-audio"
ENDPOINT = "https://api.inworld.ai/tts/v1/voice"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def reviewed_sections() -> tuple[dict[str, Any], dict[str, Any]]:
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if script.get("lesson") != 58 or script.get("status") != "reviewed-script":
        raise ValueError("Lesson 58 source script has not been reviewed.")
    if settings.get("voiceId") != "Yash" or settings.get("modelId") != "inworld-tts-2":
        raise ValueError("The reviewed voice or model setting changed.")
    seen: set[str] = set()
    for section in script["sections"]:
        identifier = section["id"]
        if identifier in seen:
            raise ValueError("Duplicate narration section ID.")
        seen.add(identifier)
        path = (ROOT / section["path"]).resolve()
        if not path.is_relative_to(ROOT / "agent_lab") or path.suffix != ".py":
            raise ValueError("Narration source path escapes the owned Python package.")
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if digest(source.encode()) != section["reviewed_source_sha256"]:
            raise ValueError(f"Reviewed source changed: {identifier}.")
        if not 1 <= section["start_line"] <= section["end_line"] <= len(source.splitlines()):
            raise ValueError(f"Invalid source range: {identifier}.")
        if not 0 < utf16_units(section["spoken_text"]) <= 2000:
            raise ValueError(f"Spoken text exceeds the unary TTS limit: {identifier}.")
    return script, settings


def normalize_word(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def checked_timing(text: str, alignment: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    words = alignment.get("words")
    starts = alignment.get("wordStartTimeSeconds")
    ends = alignment.get("wordEndTimeSeconds")
    if not isinstance(words, list) or not isinstance(starts, list) or not isinstance(ends, list):
        raise ValueError("Provider word alignment is absent.")
    if not (len(words) == len(starts) == len(ends)):
        raise ValueError("Provider word alignment arrays differ in length.")
    authored = re.findall(r"[\w']+(?:-[\w']+)*", text, flags=re.UNICODE)
    cues: list[dict[str, Any]] = []
    index = 0
    partial = ""
    first = 0.0
    last_end = 0.0
    for raw, start, end in zip(words, starts, ends, strict=True):
        if not isinstance(raw, str) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError("Malformed provider word alignment.")
        if not (0 <= start <= end <= duration + 0.05) or start < last_end - 0.02:
            raise ValueError("Overlapping or out-of-bounds provider word times.")
        last_end = end
        token = normalize_word(raw)
        if not token:
            continue
        if index >= len(authored):
            raise ValueError("Provider returned extra spoken words.")
        if not partial:
            first = start
        partial += token
        expected = normalize_word(authored[index])
        if not expected.startswith(partial):
            raise ValueError("Provider words differ from the reviewed transcript.")
        if partial == expected:
            cues.append({"word": authored[index], "start": first, "end": end})
            index += 1
            partial = ""
    if partial or index != len(authored):
        raise ValueError("Provider alignment omitted reviewed words.")
    return cues


def media_duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not 0 < duration < 600:
        raise ValueError("Invalid MP3 duration.")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                   capture_output=True, check=True)
    return duration


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_published(entry: dict[str, Any], section: dict[str, Any]) -> None:
    audio = (ROOT / entry["audio_path"]).resolve()
    timing = (ROOT / entry["timing_path"]).resolve()
    allowed = (ROOT / "public/audio/code").resolve()
    if not audio.is_relative_to(allowed) or not timing.is_relative_to(allowed):
        raise ValueError("Published narration path escapes the audio directory.")
    if not audio.is_file() or not timing.is_file():
        raise ValueError("Published narration asset is missing; reconcile before recording again.")
    if digest(audio.read_bytes()) != entry["audio_sha256"] or digest(timing.read_bytes()) != entry["timing_sha256"]:
        raise ValueError("Published narration hash changed; reconcile before recording again.")
    duration = media_duration(audio)
    timeline = json.loads(timing.read_text(encoding="utf-8"))
    cues = timeline.get("cues")
    authored = re.findall(r"[\w']+(?:-[\w']+)*", section["spoken_text"], flags=re.UNICODE)
    if not isinstance(cues, list) or len(cues) != len(authored):
        raise ValueError("Published narration timing does not cover the reviewed text.")
    previous = 0.0
    for word, cue in zip(authored, cues, strict=True):
        if normalize_word(cue.get("word", "")) != normalize_word(word):
            raise ValueError("Published narration word differs from the reviewed text.")
        start, end = cue.get("start"), cue.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not 0 <= start <= end <= duration + 0.05 or start < previous - 0.02:
            raise ValueError("Published narration timing is invalid.")
        previous = end


def plan(script: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    sections = [{"id": section["id"], "utf16_characters": utf16_units(section["spoken_text"])}
                for section in script["sections"]]
    return {"lesson": 58, "voice": settings["voiceId"], "model": settings["modelId"],
            "settings_sha256": digest(json.dumps(settings, sort_keys=True).encode()),
            "sections": sections, "total_characters": sum(item["utf16_characters"] for item in sections),
            "billing_usd": None, "network_requests": 0}


def section_identity(section: dict[str, Any], settings: dict[str, Any]) -> str:
    return digest(json.dumps({
        "lesson": 58, "id": section["id"], "source": section["reviewed_source_sha256"],
        "text": digest(section["spoken_text"].encode()), "settings": settings,
    }, sort_keys=True).encode())


def publish_saved(section: dict[str, Any], settings: dict[str, Any],
                  identity: str, manifest: dict[str, Any]) -> None:
    response_path = PRIVATE / f"{identity}.response.json"
    receipt = PRIVATE / f"{identity}.receipt.json"
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    usage = payload.get("usage", {})
    if usage.get("modelId") != settings["modelId"] or usage.get("processedCharactersCount") != utf16_units(section["spoken_text"]):
        raise ValueError("Provider usage does not match the reviewed request.")
    audio_bytes = base64.b64decode(payload["audioContent"], validate=True)
    candidate = PRIVATE / f"{identity}.mp3"
    if not candidate.is_file():
        candidate.write_bytes(audio_bytes)
    if digest(candidate.read_bytes()) != digest(audio_bytes):
        raise ValueError("Saved audio differs from the preserved provider response.")
    duration = media_duration(candidate)
    cues = checked_timing(section["spoken_text"], payload.get("timestampInfo", {}).get("wordAlignment", {}), duration)
    audio_hash = digest(audio_bytes)
    audio_path = Path("public/audio/code") / f"{audio_hash}.mp3"
    timing_path = Path("public/audio/code") / f"{audio_hash}.json"
    (ROOT / audio_path).parent.mkdir(parents=True, exist_ok=True)
    candidate.replace(ROOT / audio_path)
    atomic_json(ROOT / timing_path, {"lesson": 58, "section": section["id"],
                                     "duration": duration, "cues": cues})
    entry = {"identity": identity, "section": section["id"],
             "source_sha256": section["reviewed_source_sha256"],
             "text_sha256": digest(section["spoken_text"].encode()),
             "settings": settings, "audio_path": audio_path.as_posix(),
             "audio_sha256": audio_hash, "timing_path": timing_path.as_posix(),
             "timing_sha256": digest((ROOT / timing_path).read_bytes()),
             "duration": duration, "processed_characters": usage["processedCharactersCount"]}
    manifest["entries"] = [item for item in manifest["entries"] if item["section"] != section["id"]] + [entry]
    atomic_json(MANIFEST, manifest)
    atomic_json(receipt, {"status": "published", "identity": identity,
                          "section": section["id"], "settings": settings})


def record(script: dict[str, Any], settings: dict[str, Any], maximum: int) -> None:
    schedule = plan(script, settings)
    if schedule["total_characters"] > maximum:
        raise ValueError("The planned characters exceed --max-characters.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg and FFprobe are required before recording.")
    load_dotenv(ROOT / ".env", override=False)
    credential = os.getenv("INWORLD_API_KEY")
    if not credential:
        raise ValueError("INWORLD_API_KEY is missing. Configure it privately in .env or the process environment.")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock = PRIVATE / "record.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for section in script["sections"]:
            identity = section_identity(section, settings)
            existing = next((item for item in manifest["entries"] if item["identity"] == identity), None)
            if existing:
                verify_published(existing, section)
                continue
            receipt = PRIVATE / f"{identity}.receipt.json"
            if receipt.exists():
                raise ValueError(f"An earlier recording attempt for {section['id']} needs manual reconciliation.")
            atomic_json(receipt, {"status": "sent-or-ambiguous", "identity": identity,
                                  "section": section["id"], "settings": settings})
            body = {**settings, "text": section["spoken_text"]}
            with httpx.Client(timeout=60) as client:
                response = client.post(ENDPOINT, headers={"Authorization": f"Basic {credential}"}, json=body)
            (PRIVATE / f"{identity}.response.json").write_bytes(response.content)
            response.raise_for_status()
            publish_saved(section, settings, identity, manifest)
    finally:
        lock.unlink(missing_ok=True)


def reconcile(script: dict[str, Any], settings: dict[str, Any]) -> int:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock = PRIVATE / "record.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    published = 0
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for section in script["sections"]:
            identity = section_identity(section, settings)
            receipt = PRIVATE / f"{identity}.receipt.json"
            response_path = PRIVATE / f"{identity}.response.json"
            if not receipt.is_file() or not response_path.is_file():
                continue
            if json.loads(receipt.read_text(encoding="utf-8")).get("status") != "sent-or-ambiguous":
                continue
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            if (payload.get("code") == 7 and payload.get("message") == "key is expired" and
                    "audioContent" not in payload and "usage" not in payload):
                archived_response = PRIVATE / f"{identity}.expired-auth.response.json"
                archived_receipt = PRIVATE / f"{identity}.expired-auth.receipt.json"
                if archived_response.exists() or archived_receipt.exists():
                    raise ValueError("Expired-auth archive already exists; inspect before retrying.")
                response_path.replace(archived_response)
                receipt.replace(archived_receipt)
                continue
            publish_saved(section, settings, identity, manifest)
            published += 1
    finally:
        lock.unlink(missing_ok=True)
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "record", "reconcile"])
    parser.add_argument("--lessons", required=True)
    parser.add_argument("--max-characters", type=int)
    args = parser.parse_args()
    if args.lessons != "58":
        parser.error("This private command accepts only --lessons=58.")
    script, settings = reviewed_sections()
    if args.action == "plan":
        print(json.dumps(plan(script, settings), indent=2))
        return 0
    if args.action == "reconcile":
        print(json.dumps({"lesson": 58, "reconciled_sections": reconcile(script, settings), "network_requests": 0}))
        return 0
    if args.max_characters is None or args.max_characters <= 0:
        parser.error("Recording requires a positive --max-characters ceiling.")
    record(script, settings, args.max_characters)
    print(json.dumps({"lesson": 58, "published_sections": len(json.loads(MANIFEST.read_text())["entries"])}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
