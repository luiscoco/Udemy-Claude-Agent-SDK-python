"""Serialize NiceGUI file backups on Windows, where an atomic replace can be transiently denied."""

import asyncio
import os
import time
import uuid
from pathlib import Path

from nicegui import background_tasks, core
from nicegui.helpers import unlink_with_retry
from nicegui.persistence.file_persistent_dict import FilePersistentDict
from nicegui.persistence.serialization import dumps


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(8):
        try:
            source.replace(target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 7:
                raise
            time.sleep(0.02 * (attempt + 1))


def install_windows_storage_retry() -> None:
    """Use a private temporary file per backup and retry only transient Windows lock errors."""
    if os.name != "nt" or getattr(FilePersistentDict, "_agent_lab_retry", False):
        return

    locks: dict[Path, asyncio.Lock] = {}

    def backup(self: FilePersistentDict) -> None:
        path = self.filepath
        if not path.exists() and not self:
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def save() -> None:
            if not self:
                unlink_with_retry(path, missing_ok=True)
                return
            temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(dumps(self, str(path), indent=self.indent), encoding=self.encoding)
                _replace_with_retry(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

        @background_tasks.await_on_shutdown
        async def async_backup() -> None:
            lock = locks.setdefault(path, asyncio.Lock())
            async with lock:
                await asyncio.to_thread(save)

        if core.is_loop_running():
            background_tasks.create_lazy(async_backup(), name=path.stem)
        else:
            save()

    FilePersistentDict.backup = backup  # type: ignore[method-assign]
    FilePersistentDict._agent_lab_retry = True  # type: ignore[attr-defined]
