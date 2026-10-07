from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAB_", env_file=ROOT / ".env", extra="ignore")
    model: str = "claude-haiku-4-5"
    cli_path: str | None = None
    host: str = "127.0.0.1"
    port: int = 8080
    enable_live: bool = False
    timeout_seconds: int = 90
    max_concurrent_runs: int = 4
    data_dir: Path = ROOT / ".lab-data"
