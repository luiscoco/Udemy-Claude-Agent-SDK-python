"""One bounded, opt-in Lesson 45 native provider probe through the owned proxy."""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from dotenv import dotenv_values

from agent_lab.cloud_lab import evaluate_native
from agent_lab.cloud_proxy import AUDIENCE, PROVIDERS, SUBJECT_TYPE, CloudProxy
from agent_lab.cloud_wire import HAIKU, PROFILE, SONNET
from agent_lab.config import ROOT
from agent_lab.exercises import EmbeddedServer

ESSENTIAL = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP",
             "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS",
             "PROCESSOR_ARCHITECTURE"}


async def run(provider: str, budget: float, *, inspect_only: bool = False,
              auth_case: str = "bearer", model_case: str = "default",
              fallback: bool = True, timeout_seconds: int = 160,
              auth_probes: bool = False) -> dict[str, object]:
    if provider not in PROVIDERS or budget != 0.10:
        raise ValueError("Select one fixed provider and the $0.10 ceiling")
    if auth_case not in {"bearer", "sigv4"} or model_case not in {"default", "profile", "region", "denied"}:
        raise ValueError("Unknown fixed cloud case")
    if provider != "bedrock" and (auth_case != "bearer" or model_case != "default"):
        raise ValueError("These fixed cases use Bedrock")
    if not 10 <= timeout_seconds <= 160:
        raise ValueError("The probe timeout must be between 10 and 160 seconds")
    key = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not isinstance(key, str) or not key.startswith("sk-ant-"):
        raise ValueError("A private Anthropic host key is required")
    run_id = str(uuid.uuid4())
    folder = ROOT / ".lab-data" / "cloud-live-probe" / run_id
    work, home = folder / "work", folder / "home"
    work.mkdir(parents=True)
    home.mkdir()
    aws_config, aws_credentials = home / "aws-config", home / "aws-credentials"
    aws_config.write_text("", encoding="utf-8")
    aws_credentials.write_text("", encoding="utf-8")
    proxy = CloudProxy(run_id, provider, provider, inspect_only=inspect_only, upstream_key=key)
    frames: list[dict[str, object]] = []
    auth_probe_statuses: list[int] = []
    async with EmbeddedServer(proxy).running() as base:
        proxy.base = base
        if auth_probes:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as http:
                url = base + proxy.prefix + "/catalog"
                auth_probe_statuses.append((await http.get(url)).status_code)
                bad = ({"x-api-key": "wrong"} if provider in {"firstParty", "foundry"}
                       else {"Authorization": "Bearer wrong"})
                auth_probe_statuses.append((await http.get(url, headers=bad)).status_code)
        environment = {name: value for name, value in os.environ.items() if name.upper() in ESSENTIAL}
        environment.update({"HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(home / "appdata")})
        provider_env = {"CLAUDE_CONFIG_DIR": str(home),
                        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                        "AWS_CONFIG_FILE": str(aws_config),
                        "AWS_SHARED_CREDENTIALS_FILE": str(aws_credentials),
                        "AWS_EC2_METADATA_DISABLED": "true",
                        "CLOUDSDK_CONFIG": str(home / "gcloud"),
                        "ANTHROPIC_DEFAULT_HAIKU_MODEL": HAIKU}
        if provider == "firstParty":
            provider_env.update({"ANTHROPIC_BASE_URL": base + proxy.prefix,
                                 "ANTHROPIC_API_KEY": proxy.bearer})
        elif provider == "gateway":
            provider_env.update({"ANTHROPIC_BASE_URL": base + proxy.prefix,
                                 "ANTHROPIC_AUTH_TOKEN": proxy.bearer})
        elif provider == "bedrock":
            provider_env.update({"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1",
                                 "ANTHROPIC_BEDROCK_BASE_URL": base + proxy.prefix})
            if auth_case == "sigv4":
                provider_env.update({"AWS_ACCESS_KEY_ID": proxy.access_id,
                                     "AWS_SECRET_ACCESS_KEY": proxy.secret})
            else:
                provider_env["AWS_BEARER_TOKEN_BEDROCK"] = proxy.bearer
        elif provider == "foundry":
            provider_env.update({"CLAUDE_CODE_USE_FOUNDRY": "1",
                                 "ANTHROPIC_FOUNDRY_BASE_URL": base + proxy.prefix + "/anthropic",
                                 "ANTHROPIC_FOUNDRY_API_KEY": proxy.bearer})
        elif provider == "vertex":
            subject_file, account_file = home / "subject.jwt", home / "external-account.json"
            subject_file.write_text(proxy.subject, encoding="utf-8")
            account_file.write_text(json.dumps({"type": "external_account", "audience": AUDIENCE,
                "subject_token_type": SUBJECT_TYPE, "token_url": base + proxy.prefix + "/sts",
                "credential_source": {"file": str(subject_file)}}), encoding="utf-8")
            provider_env.update({"CLAUDE_CODE_USE_VERTEX": "1",
                                 "ANTHROPIC_VERTEX_PROJECT_ID": "lesson45-project",
                                 "CLOUD_ML_REGION": "us-east5",
                                 "ANTHROPIC_VERTEX_BASE_URL": base + proxy.prefix + "/v1",
                                 "GOOGLE_APPLICATION_CREDENTIALS": str(account_file)})
        selected_model = (PROFILE if model_case == "profile" else
                          "eu.anthropic." + HAIKU + "-v1:0" if model_case == "region" else
                          SONNET if model_case == "denied" else HAIKU)
        if model_case == "denied":
            provider_env["CLAUDE_CODE_MAX_RETRIES"] = "1"
            provider_env["CLAUDE_CODE_DISABLE_REFUSAL_RETRY"] = "1"
        job = {"work": str(work), "model": selected_model,
               "fallback_model": HAIKU if model_case == "denied" and fallback else None,
               "marker": "L45-" + uuid.uuid4().hex[:16],
               "timeout_seconds": timeout_seconds,
               "inspect_only": inspect_only,
               "environment": provider_env}
        helper = ROOT / "scripts" / "cloud_native_helper.py"
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(helper), cwd=str(ROOT), env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(json.dumps(job).encode()),
                                               timeout=timeout_seconds + 10)
            result = json.loads(output)
            frames = result.get("frames", []) if isinstance(result, dict) else []
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    proxy.closed = True
    report: dict[str, object] = {"lesson": 45, "run_id": run_id, "provider": provider,
                                 "mode": "live", "inspect_only": inspect_only,
                                 "auth_case": auth_case, "model_case": model_case,
                                 "fallback_configured": model_case == "denied" and fallback,
                                 "auth_probes_required": auth_probes,
                                 "auth_probe_statuses": auth_probe_statuses,
                                 "marker": job["marker"],
                                 "frames": frames, "receipts": proxy.receipts,
                                 "forward_diagnostics": proxy.forward_diagnostics,
                                 "forwarded": proxy.forwarded, "closed": proxy.closed,
                                 "created_at": datetime.now(UTC).isoformat()}
    report["passed"] = evaluate_native(report)
    folder.joinpath("report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--provider", choices=list(PROVIDERS), required=True)
    parser.add_argument("--budget", type=float, required=True)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--auth-case", choices=["bearer", "sigv4"], default="bearer")
    parser.add_argument("--model-case", choices=["default", "profile", "region", "denied"], default="default")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=160)
    args = parser.parse_args()
    report = asyncio.run(run(args.provider, args.budget, inspect_only=args.inspect_only,
                             auth_case=args.auth_case, model_case=args.model_case,
                             fallback=not args.no_fallback,
                             timeout_seconds=args.timeout_seconds))
    frames = cast(list[dict[str, Any]], report["frames"])
    receipts = cast(list[dict[str, Any]], report["receipts"])
    results = [frame for frame in frames if frame["kind"] == "result"]
    catalogs = [frame for frame in frames if frame["kind"] == "catalog"]
    print(json.dumps({"run_id": report["run_id"], "provider": report["provider"],
                      "inspect_only": report["inspect_only"], "auth_case": report["auth_case"],
                      "model_case": report["model_case"], "passed": report["passed"],
                      "forwarded": report["forwarded"],
                      "wire": [(row["kind"], row["status"], row["upstream_status"])
                               for row in receipts],
                      "catalog": [{"account_provider": row["account_provider"],
                                   "model_count": len(row["models"])} for row in catalogs],
                      "terminal": [{"subtype": row["subtype"], "is_error": row["is_error"],
                                    "cost_usd": row["cost_usd"]} for row in results]}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
