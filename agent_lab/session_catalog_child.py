"""Isolated, owned local-session catalog operations; this process never calls a model."""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from claude_agent_sdk import (
    delete_session,
    fork_session,
    get_session_info,
    get_session_messages,
    list_sessions,
    rename_session,
    tag_session,
)


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def visible_text(message) -> str:
    value = message.message.get("content", "")
    return (
        value
        if isinstance(value, str)
        else "".join(b.get("text", "") for b in value if isinstance(b, dict))
    )


def inspect_session(project: str, session_id: str, size: int, offset: int) -> dict:
    info = get_session_info(session_id, directory=project)
    all_sessions = list_sessions(directory=project, include_worktrees=False, limit=10)
    page = list_sessions(directory=project, include_worktrees=False, limit=size, offset=offset)
    messages = get_session_messages(session_id, directory=project, limit=64)
    message_page = get_session_messages(session_id, directory=project, limit=size, offset=offset)
    uuids = [m.uuid for m in messages]
    first_user = next((visible_text(m) for m in messages if m.type == "user"), "")
    return {
        "session_id": session_id,
        "info_found": info is not None,
        "info_session_id": info.session_id if info else None,
        "cwd": info.cwd if info else None,
        "title": info.custom_title if info else None,
        "tag": info.tag if info else None,
        "catalog_session_ids": [s.session_id for s in all_sessions],
        "session_page_ids": [s.session_id for s in page],
        "session_page_matches": [s.session_id for s in page]
        == [s.session_id for s in all_sessions][offset : offset + size],
        "message_count": len(messages),
        "message_uuids": uuids,
        "message_types": [m.type for m in messages],
        "message_session_ids": list(dict.fromkeys(m.session_id for m in messages)),
        "message_page": [
            {"uuid": m.uuid, "type": m.type, "preview": visible_text(m)[:240]} for m in message_page
        ],
        "message_page_matches": [m.uuid for m in message_page] == uuids[offset : offset + size],
        "first_user_digest": hashlib.sha256(first_user.encode()).hexdigest(),
        "visible_content_digest": digest(
            [{"type": m.type, "message": m.message} for m in messages]
        ),
    }


def owned_file(config: Path, session_id: str) -> Path:
    files = [
        p
        for p in (config / "projects").glob(f"*/{session_id}.jsonl")
        if not p.is_symlink() and p.resolve().is_relative_to(config)
    ]
    if len(files) != 1:
        raise ValueError("Expected exactly one owned transcript")
    return files[0]


def operate(payload: dict) -> dict:
    config, project_path = Path(payload["config"]).resolve(), Path(payload["project"]).resolve()
    if config.parent != project_path.parent or config == project_path:
        raise ValueError("Configuration and project must be sibling run directories")
    session_id = str(UUID(payload["session_id"]))
    action, size, offset = payload["action"], payload["page_size"], payload["offset"]
    if (
        action not in {"inspect", "rename-tag", "fork", "delete"}
        or type(size) is not int
        or not 1 <= size <= 10
        or type(offset) is not int
        or not 0 <= offset <= 20
    ):
        raise ValueError("Unsupported catalog operation")
    os.environ["CLAUDE_CONFIG_DIR"] = str(config)
    project = str(project_path)
    before = inspect_session(project, session_id, size, offset)
    if (
        not before["info_found"]
        or before["info_session_id"] != session_id
        or session_id not in before["catalog_session_ids"]
        or Path(before["cwd"] or "").resolve() != project_path
        or before["first_user_digest"] != payload["prompt_digest"]
    ):
        raise ValueError("The recorded session does not establish ownership")
    source = owned_file(config, session_id)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    mutation = {"action": action, "target_session_id": session_id}
    if action == "rename-tag":
        rename_session(session_id, payload["title"], directory=project)
        tag_session(session_id, payload["tag"], directory=project)
    elif action == "fork":
        forked = fork_session(session_id, directory=project, title=payload["title"])
        mutation["fork_session_id"] = forked.session_id
        mutation["fork"] = inspect_session(project, forked.session_id, size, offset)
    elif action == "delete":
        delete_session(session_id, directory=project)
    after = inspect_session(project, session_id, size, offset)
    mutation["original_file_unchanged"] = (
        source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    )
    mutation["original_file_exists"] = source.exists()
    os.environ["CLAUDE_CONFIG_DIR"] = str(config.parent / "empty-catalog-config")
    empty = list_sessions(directory=project, include_worktrees=False, limit=10)
    os.environ["CLAUDE_CONFIG_DIR"] = str(config)
    other_project = list_sessions(
        directory=str(project_path / "other-project"), include_worktrees=False, limit=10
    )
    return {
        "source": "actual public SDK catalog functions in an isolated child",
        "before": before,
        "after": after,
        "mutation": mutation,
        "isolation": {
            "empty_config_session_count": len(empty),
            "other_project_session_count": len(other_project),
        },
    }


if __name__ == "__main__":
    try:
        result = operate(json.loads(sys.stdin.read(10000)))
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}))
        raise SystemExit(1) from None
