"""Inspect CLI initialization metadata without ever submitting a user prompt."""

import asyncio
import importlib.metadata
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from agent_lab.config import Settings
from agent_lab.policy import redact


def check_owned(root: Path, parent: Path) -> None:
    if not root.resolve().is_relative_to(parent.resolve()):
        raise ValueError("The metadata workspace must remain inside its owned directory.")


class ModelMetadata:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = asyncio.Lock()
        self.cached: tuple[float, dict] | None = None

    async def inspect(self) -> dict:
        from claude_agent_sdk import ClaudeAgentOptions

        from agent_lab.sdk import (
            ClaudeSDKClient,
            isolated_env,
            require_live_access,
            resolve_cli_path,
        )

        base: dict[str, Any] = {
            "configured_model": self.settings.model,
            "configured_model_verified": False,
            "installed_sdk": importlib.metadata.version("claude-agent-sdk"),
            "sdk_effort_values": ["low", "medium", "high", "xhigh", "max"],
            "sdk_thinking_shapes": ["disabled", "adaptive", "enabled"],
            "prompt_sent": False,
            "models": None,
            "connection_closed": True,
            "scope": "SDK option types and runtime initialization metadata; not proof of model access, compatibility, prompt success or fallback.",
        }
        if not self.settings.enable_live:
            return base | {"status": "disabled", "source": "configuration only; no CLI was started"}
        if self.cached and time.monotonic() - self.cached[0] < 60:
            return self.cached[1] | {"cached": True}
        if self.lock.locked():
            return base | {"status": "busy", "source": "another metadata probe is running"}
        async with self.lock:
            temporary = None
            client = None
            try:
                require_live_access(self.settings)
                directory = self.settings.data_dir / "thinking-metadata"
                await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
                temporary = await asyncio.to_thread(
                    tempfile.TemporaryDirectory, prefix="probe-", dir=directory
                )
                root = Path(temporary.name)
                await asyncio.to_thread(check_owned, root, directory)
                options = ClaudeAgentOptions(
                    model=self.settings.model,
                    cli_path=resolve_cli_path(self.settings),
                    tools=[],
                    setting_sources=[],
                    strict_mcp_config=True,
                    cwd=str(root),
                    env=isolated_env(root / "config"),
                )
                client = ClaudeSDKClient(options=options)
                base["connection_closed"] = False
                async with asyncio.timeout(15):
                    await client.connect()  # No prompt and no query() call.
                    info = await client.get_server_info()
                    models = info.get("models") if isinstance(info, dict) else None
                    if isinstance(models, list):
                        keys = {
                            "value",
                            "id",
                            "displayName",
                            "description",
                            "supportsEffort",
                            "supportedEffortLevels",
                            "supportsAdaptiveThinking",
                        }
                        filtered = [
                            {k: v for k, v in row.items() if k in keys}
                            for row in models[:100]
                            if isinstance(row, dict)
                        ]
                        if len(json.dumps(filtered, default=str)) <= 20000:
                            base["models"] = redact(filtered)
                base.update(
                    status="observed" if base["models"] is not None else "unavailable",
                    source="CLI initialization metadata; no user input submitted",
                )
            except Exception as exc:
                base.update(
                    status="failed",
                    source="metadata not established",
                    error=f"{type(exc).__name__}: metadata probe failed. Check CLI setup and credentials; no fallback was attempted.",
                )
            finally:
                try:
                    if client is not None:
                        try:
                            await client.disconnect()
                            base["connection_closed"] = True
                        except Exception:
                            base.update(
                                status="failed",
                                error="Metadata connection cleanup could not be confirmed.",
                            )
                finally:
                    if temporary is not None:
                        await asyncio.to_thread(
                            check_owned,
                            Path(temporary.name),
                            self.settings.data_dir / "thinking-metadata",
                        )
                        try:
                            await asyncio.to_thread(temporary.cleanup)
                        except Exception:
                            base.update(
                                status="failed",
                                error="Owned metadata workspace cleanup could not be confirmed.",
                            )
            self.cached = (time.monotonic(), dict(base))
            return base | {"cached": False}
