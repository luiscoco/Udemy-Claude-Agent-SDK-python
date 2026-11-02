"""Host boundaries: model text never grants authority."""

import re
from pathlib import Path
from typing import Any

PROTECTED = {".git", ".env", ".venv", "config", ".claude"}


def inside(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("Use a nonempty relative workspace path.")
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or PROTECTED.intersection(target.relative_to(root).parts):
        raise ValueError("Path is outside the permitted workspace.")
    return target


def decide(root: Path, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    if tool_name in {"Read", "Glob", "Grep"}:
        raw = arguments.get("file_path", arguments.get("path", "."))
        try:
            value = Path(str(raw))
            if value.is_absolute():
                value = value.resolve().relative_to(root.resolve())
            inside(root, str(value))
        except (ValueError, OSError):
            return False, "Read only non-secret files inside this lesson workspace."
        return True, "Read-only workspace access."
    return False, "This tool is not available in the read-only lesson policy."


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.search(r"token|secret|password|api.?key|authorization", key, re.I)
            and item is not None
            # Usage counters such as input_tokens are numbers, never credentials.
            and not (isinstance(item, int | float) and not isinstance(item, bool))
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"sk-ant-[\w-]+|Bearer\s+[\w.\-/+=]+", "[REDACTED]", value, flags=re.I)
    return value
