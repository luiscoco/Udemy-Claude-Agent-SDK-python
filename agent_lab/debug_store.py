"""Owned, restart-safe Lesson 53 diagnostic bundle persistence."""

import json
import math
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from agent_lab.debug_lab import BYTE_LIMIT, FORCED_LIMIT, SCENARIOS, digest


class MissingBundle(LookupError):
    pass


class InvalidBundle(ValueError):
    pass


def valid_bundle(value: Any, identifier: uuid.UUID) -> bool:
    if not isinstance(value, dict):
        return False
    required = {"id", "mode", "scenario", "effectiveConfig", "compareId", "rows", "findings",
                "observations", "closed", "interrupted", "overflow", "modelCalls", "reportedSdkUsd",
                "log", "limitations"}
    if (set(value) - required - {"comparison"} or required - set(value) or
            value["id"] != str(identifier) or value["mode"] not in {"prepared", "live"} or
            value["scenario"] not in SCENARIOS or
            not isinstance(value["rows"], list) or len(value["rows"]) > FORCED_LIMIT or
            not isinstance(value["findings"], list) or not isinstance(value["observations"], dict) or
            not isinstance(value["effectiveConfig"], dict) or
            set(value["effectiveConfig"]) != {"policy", "fixture", "maxTurns", "captureLog", "producerFault"} or
            not all(type(value[key]) is bool for key in ("closed", "interrupted", "overflow")) or
            type(value["modelCalls"]) is not int or value["modelCalls"] < 0 or
            not isinstance(value["limitations"], list)):
        return False
    cost = value["reportedSdkUsd"]
    if cost is not None and (not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0):
        return False
    if value["compareId"] is not None:
        try:
            uuid.UUID(value["compareId"])
        except (TypeError, ValueError):
            return False
    if not isinstance(value["log"], dict) or set(value["log"]) != {"found", "truncated", "text"}:
        return False
    if (type(value["log"]["found"]) is not bool or type(value["log"]["truncated"]) is not bool or
            not isinstance(value["log"]["text"], str)):
        return False
    for index, row in enumerate(value["rows"], 1):
        if (not isinstance(row, dict) or row.get("runId") != str(identifier) or
                row.get("seq") != index or type(row.get("milliseconds")) is not int or
                row["milliseconds"] < 0 or row.get("kind") not in {"host", "sdk", "hook", "permission", "stderr"} or
                not isinstance(row.get("name"), str) or not 1 <= len(row["name"]) <= 80 or
                not isinstance(row.get("data"), dict)):
            return False
    for finding in value["findings"]:
        if (not isinstance(finding, dict) or set(finding) != {"code", "row", "nextCheck"} or
                not isinstance(finding["code"], str) or type(finding["row"]) is not int or
                not 1 <= finding["row"] <= len(value["rows"]) or
                not isinstance(finding["nextCheck"], str)):
            return False
    return True


class DebugStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, identifier: uuid.UUID) -> Path:
        return self.root / str(identifier) / "bundle.json"

    def save(self, bundle: dict[str, Any]) -> dict[str, Any]:
        identifier = uuid.UUID(bundle["id"])
        if not valid_bundle(bundle, identifier):
            raise InvalidBundle("Diagnostic bundle has invalid shape")
        path = self.path(identifier)
        if path.exists():
            raise InvalidBundle("Diagnostic bundle already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode()
        if len(data) > BYTE_LIMIT:
            raise InvalidBundle("Diagnostic bundle exceeds the byte ceiling")
        temporary = path.with_name("bundle." + uuid.uuid4().hex + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.load(identifier)

    def load(self, identifier: uuid.UUID) -> dict[str, Any]:
        path = self.path(identifier)
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise MissingBundle("Saved diagnostic bundle was not found") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > BYTE_LIMIT:
            raise InvalidBundle("Saved diagnostic bundle is not a bounded regular file")
        data = path.read_bytes()
        try:
            bundle = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidBundle("Saved diagnostic bundle is not valid JSON") from exc
        if not valid_bundle(bundle, identifier):
            raise InvalidBundle("Saved diagnostic bundle has invalid identity or shape")
        return {"source": "persisted-file-reload", "id": str(identifier),
                "sha256": digest(data), "bundle": bundle}
