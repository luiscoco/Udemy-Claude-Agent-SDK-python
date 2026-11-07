"""Run the owned native probe in an existing WSL distro without storing credentials."""

import argparse
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main(live: bool) -> int:
    if not live:
        print("No WSL or provider process started. Use --live for the fixed native sandbox probe.")
        return 0
    load_dotenv(ROOT / ".env", override=False)
    linux_root = subprocess.check_output(
        ["wsl", "-d", "Ubuntu", "--", "wslpath", "-a", ROOT.as_posix()], text=True
    ).strip()
    env = dict(os.environ)
    shared = [name + "/u" for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL") if env.get(name)]
    env["WSLENV"] = ":".join(filter(None, [env.get("WSLENV", ""), *shared]))
    return subprocess.run(
        [
            "wsl",
            "-d",
            "Ubuntu",
            "--",
            "env",
            f"PYTHONPATH={linux_root}/.lab-data/sandbox-linux-site:{linux_root}",
            "python3",
            f"{linux_root}/scripts/native_sandbox_live.py",
            "--live",
            "--model",
            env.get("LAB_MODEL", "claude-haiku-4-5"),
        ],
        env=env,
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(args.live))
