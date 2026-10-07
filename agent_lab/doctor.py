"""Read-only installation diagnostics, with no model call or credential output."""

import importlib.metadata
import shutil
import sys
from pathlib import Path

from agent_lab.config import Settings


def resolve_cli_path(settings: Settings) -> str | None:
    """Find the same native executable for diagnostics and SDK execution."""
    import claude_agent_sdk

    binary = "claude.exe" if sys.platform == "win32" else "claude"
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / binary
    configured = Path(settings.cli_path).expanduser() if settings.cli_path else None
    native_install = Path.home() / ".local" / "bin" / binary
    return (
        str(configured)
        if configured
        else str(bundled)
        if bundled.is_file()
        else shutil.which(binary)
        or shutil.which("claude")
        or (str(native_install) if native_install.is_file() else None)
    )


def diagnose(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    path = resolve_cli_path(settings)
    native = (
        path is not None
        and Path(path).is_file()
        and (sys.platform != "win32" or str(path).lower().endswith(".exe"))
    )
    return {
        "python": sys.version.split()[0],
        "sdk": importlib.metadata.version("claude-agent-sdk"),
        "nicegui": importlib.metadata.version("nicegui"),
        "cli_available": native,
        "cli_path": path,
        "live_enabled": settings.enable_live,
        "next_step": "Claude Code is available. Live calls require valid provider credentials and LAB_ENABLE_LIVE=true."
        if native
        else "Offline lessons work. Install native Claude Code and set LAB_CLI_PATH if it is not on PATH. See https://code.claude.com/docs/en/setup.",
    }
