"""Lesson 45 local cloud-format comparisons over owned HTTP listeners."""

import asyncio
import json
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from agent_lab.cloud_proxy import AUDIENCE, GRANT_TYPE, PROVIDERS, SUBJECT_TYPE, CloudProxy
from agent_lab.cloud_wire import HAIKU, PROFILE, SONNET, fixture_sigv4
from agent_lab.config import Settings
from agent_lab.exercises import EmbeddedServer
from agent_lab.models import Event, RunRequest, lesson_request

ACTIONS = ("catalog", "same", "auth", "models", "failures")
AUTH_CASES = {"sigv4": "bedrock", "bearer": "bedrock", "wif": "vertex",
              "foundry": "foundry", "gateway": "gateway"}
MODEL_CASES = ("alias", "profile", "region")


def facts() -> dict[str, Any]:
    return {"lesson": 45, "actions": list(ACTIONS), "providers": list(PROVIDERS),
            "criterion": "Local cloud-format proxy observed authenticated traffic; does not prove cloud deployment.",
            "canonical_model": HAIKU, "profile": PROFILE,
            "mode_labels": {"local": "authored host client over owned loopback HTTP",
                            "live": "native SDK subprocess through owned proxy"}}


def _lanes(action: str, auth_case: str, model_case: str) -> list[tuple[str, str, str]]:
    if action in {"catalog", "same"}:
        return [(provider, provider, HAIKU) for provider in PROVIDERS]
    if action == "auth":
        provider = AUTH_CASES[auth_case]
        return [(auth_case, provider, HAIKU)]
    if action == "models":
        provider = "firstParty" if model_case == "alias" else "bedrock"
        wire = ("haiku" if model_case == "alias" else PROFILE if model_case == "profile"
                else "eu.anthropic." + HAIKU + "-v1:0")
        return [(model_case, provider, wire)]
    return [("denied", "bedrock", SONNET), ("recovered", "bedrock", HAIKU)]


async def _headers(client: httpx.AsyncClient, proxy: CloudProxy, prefix: str,
                   auth_case: str) -> dict[str, str]:
    if proxy.provider == "vertex":
        response = await client.post(prefix + "/sts", json={
            "audience": AUDIENCE, "subject_token_type": SUBJECT_TYPE,
            "grant_type": GRANT_TYPE, "subject_token": proxy.subject})
        if response.status_code != 200:
            raise ValueError("Owned STS rejected the local subject")
        return {"Authorization": "Bearer " + response.json()["access_token"]}
    if proxy.provider == "bedrock":
        if auth_case != "sigv4":
            return {"Authorization": "Bearer " + proxy.bearer}
        return {}
    if proxy.provider == "gateway":
        return {"Authorization": "Bearer " + proxy.bearer}
    return {"x-api-key": proxy.bearer}


def _url_and_body(proxy: CloudProxy, wire: str, marker: str) -> tuple[str, bytes]:
    if proxy.provider == "bedrock":
        suffix = "/model/" + wire + "/invoke"
    elif proxy.provider == "vertex":
        suffix = ("/v1/projects/lesson45-project/locations/us-east5/publishers/anthropic/models/"
                  + wire + ":rawPredict")
    elif proxy.provider == "foundry":
        suffix = "/anthropic/v1/messages"
    else:
        suffix = "/v1/messages"
    body = json.dumps({"model": HAIKU if wire == "haiku" else wire,
                       "messages": [{"role": "user", "content": "READY " + marker}],
                       "max_tokens": 24}, separators=(",", ":")).encode()
    return proxy.base + proxy.prefix + suffix, body


async def local_action(action: str, auth_case: str = "bearer", model_case: str = "profile",
                       scenario: str = "normal") -> dict[str, Any]:
    if action not in ACTIONS or auth_case not in AUTH_CASES or model_case not in MODEL_CASES or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown Lesson 45 action or fixed case")
    run_id = str(uuid.uuid4())
    reports: list[dict[str, Any]] = []
    closed = True
    for lane_name, provider, wire in _lanes(action, auth_case, model_case):
        proxy = CloudProxy(run_id, lane_name, provider, inspect_only=action == "catalog")
        marker = "L45-" + uuid.uuid4().hex[:16]
        async with EmbeddedServer(proxy).running() as base:
            proxy.base = base
            prefix = base + proxy.prefix
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                headers = await _headers(client, proxy, prefix, auth_case)
                rejected_statuses: list[int] = []
                if action == "auth":
                    rejected_statuses.append((await client.get(prefix + "/catalog")).status_code)
                    bad = ({"Authorization": "Bearer wrong"} if provider in {"bedrock", "vertex", "gateway"}
                           else {"x-api-key": "wrong"})
                    rejected_statuses.append((await client.get(prefix + "/catalog", headers=bad)).status_code)
                if provider == "bedrock" and auth_case == "sigv4":
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    catalog_path = (proxy.prefix + "/catalog").encode()
                    catalog_headers = {"Host": "127.0.0.1", "x-amz-date": stamp}
                    catalog_headers["Authorization"] = fixture_sigv4(
                        "GET", catalog_path, b"", catalog_headers, b"", proxy.access_id, proxy.secret, "us-east-1")
                    catalog = await client.get(prefix + "/catalog", headers=catalog_headers)
                else:
                    catalog = await client.get(prefix + "/catalog", headers=headers)
                if catalog.status_code != 200:
                    raise ValueError("Owned catalog request failed")
                response_status = None
                response_id = None
                if action != "catalog":
                    url, body = _url_and_body(proxy, wire, marker)
                    model_headers = dict(headers)
                    if provider == "bedrock" and auth_case == "sigv4":
                        path = httpx.URL(url).raw_path
                        model_headers = {"Host": "127.0.0.1", "x-amz-date": stamp}
                        model_headers["Authorization"] = fixture_sigv4(
                            "POST", path, b"", model_headers, body, proxy.access_id, proxy.secret, "us-east-1")
                    response = await client.post(url, content=body, headers=model_headers)
                    response_status = response.status_code
                    response_id = response.json().get("id")
                reports.append({"name": lane_name, "provider": provider, "wire_model": wire,
                                "catalog_status": catalog.status_code, "catalog_models": catalog.json()["models"],
                                "response_status": response_status, "response_id": response_id,
                                "marker": marker, "rejected_statuses": rejected_statuses,
                                "receipts": list(proxy.receipts), "forwarded": proxy.forwarded,
                                "listener_closed": True})
        proxy.closed = True
    report = {"action": action, "mode": "local", "scenario": scenario, "run_id": run_id,
              "auth_case": auth_case, "model_case": model_case, "lanes": reports, "closed": closed,
              "source_label": "authored host HTTP fixture"}
    if scenario == "missing":
        reports[0]["receipts"] = []
    elif scenario == "foreign":
        reports[0]["receipts"][0]["run_id"] = str(uuid.uuid4())
    elif scenario == "failed":
        reports[0]["listener_closed"] = False
    report["experiment_passed"] = evaluate_local(report)
    return report


def evaluate_local(report: dict[str, Any]) -> bool:
    if report.get("mode") != "local" or report.get("scenario") != "normal" or not report.get("closed"):
        return False
    lanes = report.get("lanes", [])
    expected = _lanes(report["action"], report["auth_case"], report["model_case"])
    if len(lanes) != len(expected):
        return False
    for lane, (name, provider, wire) in zip(lanes, expected, strict=True):
        if (lane["name"] != name or lane["provider"] != provider or lane["wire_model"] != wire or
                not lane["listener_closed"] or lane["forwarded"] != 0 or lane["catalog_status"] != 200 or
                HAIKU not in lane["catalog_models"]):
            return False
        receipts = lane["receipts"]
        if not receipts or any(row["run_id"] != report["run_id"] or row["lane"] != name or
                               row["provider"] != provider for row in receipts):
            return False
        if not any(row["kind"] == "catalog" and row["status"] == 200 and row["auth_verdict"]
                   for row in receipts):
            return False
        if report["action"] == "auth" and (lane["rejected_statuses"] != [401, 401] or
                                          sum(row["status"] == 401 for row in receipts) < 2):
            return False
        if report["action"] == "catalog":
            if lane["response_status"] is not None or any(row["kind"] == "model" for row in receipts):
                return False
        elif name == "denied":
            if lane["response_status"] != 403 or not any(row["canonical_model"] == SONNET and
                    row["status"] == 403 and row["auth_verdict"] for row in receipts):
                return False
        elif (lane["response_status"] != 200 or not lane["response_id"] or
              not any(row["kind"] == "model" and row["status"] == 200 and row["auth_verdict"]
                      and row["canonical_model"] == HAIKU and row["message_id"] == lane["response_id"]
                      and row["marker_seen"] == lane["marker"] for row in receipts)):
            return False
    return True


def evaluate_native(report: dict[str, Any]) -> bool:
    """Join actual SDK, proxy and upstream identities for one isolated lane."""
    if (report.get("mode") != "live" or not report.get("closed") or
            report.get("provider") not in PROVIDERS or len(report.get("receipts", [])) > 40 or
            report.get("forwarded", 0) > 8):
        return False
    provider = report["provider"]
    receipts = report["receipts"]
    if any(row["run_id"] != report["run_id"] or row["provider"] != provider or
           row["lane"] != provider for row in receipts):
        return False
    if report.get("auth_probes_required") and (report.get("auth_probe_statuses") != [401, 401] or
            sum(row["kind"] == "catalog" and row["status"] == 401 and not row["auth_verdict"]
                for row in receipts) < 2):
        return False
    catalogs = [row for row in report["frames"] if row["kind"] == "catalog"]
    actual_provider = "firstParty" if provider == "gateway" else provider
    if (len(catalogs) != 1 or catalogs[0]["account_provider"] != actual_provider or
            not catalogs[0]["models"]):
        return False
    if report.get("inspect_only"):
        return bool(report["forwarded"] == 0 and
                    not any(row["kind"] in {"assistant", "result", "init"} for row in report["frames"]) and
                    not any(row["kind"] == "model" and row["upstream_status"] is not None
                            for row in receipts))
    inits = [row for row in report["frames"] if row["kind"] == "init"]
    assistants = [row for row in report["frames"] if row["kind"] == "assistant"]
    terminals = [row for row in report["frames"] if row["kind"] == "result"]
    if len(inits) != 1 or len(terminals) != 1 or not assistants:
        return False
    init, terminal = inits[0], terminals[0]
    try:
        ids_ok = (str(uuid.UUID(init["session_id"])) == init["session_id"] and
                  str(uuid.UUID(terminal["uuid"])) == terminal["uuid"])
    except (ValueError, TypeError, KeyError):
        ids_ok = False
    cost = terminal.get("cost_usd")
    if report.get("model_case") == "denied":
        return bool(ids_ok and terminal["session_id"] == init["session_id"] and
                    init["model"] == SONNET and report.get("fallback_configured") and
                    terminal["is_error"] is True and terminal["cost_usd"] == 0 and
                    not terminal["model_usage"] and report["forwarded"] == 0 and
                    any(row["kind"] == "model" and row["status"] == 403 and
                        row["auth_verdict"] and row["canonical_model"] == SONNET
                        for row in receipts) and
                    not any(row["upstream_status"] is not None for row in receipts) and
                    not any(item["model"] == HAIKU for item in assistants))
    expected_usage = (PROFILE if report.get("model_case") == "profile" else
                      "eu.anthropic." + HAIKU + "-v1:0" if report.get("model_case") == "region" else HAIKU)
    if (not ids_ok or terminal["session_id"] != init["session_id"] or
            terminal["subtype"] != "success" or terminal["is_error"] or
            not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0 or cost > 0.10 or
            expected_usage not in terminal["model_usage"]):
        return False
    matched = [row for row in receipts if row["kind"] == "model" and row["status"] == 200 and
               row["upstream_status"] == 200 and row["auth_verdict"] and row["canonical_model"] == HAIKU and
               row["marker_seen"] == report["marker"] and
               any(item["id"] == row["message_id"] and item["session_id"] == init["session_id"] and
                   item["model"] == HAIKU for item in assistants)]
    if not matched:
        return False
    if report.get("model_case") == "profile" and not any(row["wire_model"] == PROFILE for row in matched):
        return False
    if report.get("auth_case") == "sigv4" and not any(row["auth_kind"] == "sigv4" for row in matched):
        return False
    return True


def state(storage: Path) -> dict[str, Any]:
    pointer = storage / "latest.json"
    if not pointer.is_file() or pointer.is_symlink() or pointer.stat().st_nlink != 1 or pointer.stat().st_size > 128:
        raise ValueError("No successful Lesson 45 run")
    try:
        identity = json.loads(pointer.read_text(encoding="utf-8")).get("run_id")
        if str(uuid.UUID(identity)) != identity:
            raise ValueError
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Lesson 45 run ID") from exc
    summary = storage / identity / "summary.json"
    if not summary.is_file() or summary.is_symlink() or summary.stat().st_nlink != 1 or summary.stat().st_size > 1024:
        raise ValueError("Invalid Lesson 45 summary")
    result = json.loads(summary.read_text(encoding="utf-8"))
    if (not isinstance(result, dict) or set(result) != {"run_id", "action", "mode", "check"} or
            result["run_id"] != identity or result["action"] not in ACTIONS or
            result["mode"] not in {"local", "live"} or result["check"] != "passed"):
        raise ValueError("Invalid Lesson 45 summary")
    return result


async def run(storage: Path, settings: Settings, action: str, mode: str,
              *, scenario: str = "normal", auth_case: str = "bearer",
              model_case: str = "profile") -> dict[str, Any]:
    if action not in ACTIONS or mode not in {"local", "live"}:
        raise ValueError("Unknown Lesson 45 action or mode")
    if auth_case not in AUTH_CASES or model_case not in MODEL_CASES or scenario not in {"normal", "missing", "foreign", "failed"}:
        raise ValueError("Unknown fixed Lesson 45 case")
    if mode == "live" and scenario != "normal":
        raise PermissionError("Fault scenarios are local only")
    if mode == "local":
        report = await local_action(action, auth_case, model_case, scenario)
    else:
        if not settings.enable_live:
            raise PermissionError("Enable bounded paid calls with LAB_ENABLE_LIVE=true")
        from scripts.cloud_live_probe import run as native_probe

        selections: list[tuple[str, bool, str, str]]
        if action == "catalog":
            selections = [(provider, True, "bearer", "default") for provider in PROVIDERS]
        elif action == "same":
            selections = [(provider, False, "bearer", "default") for provider in PROVIDERS]
        elif action == "auth":
            provider = AUTH_CASES[auth_case]
            selections = [(provider, False, auth_case if provider == "bedrock" else "bearer", "default")]
        elif action == "models":
            selections = [("firstParty", False, "bearer", "default")]
            if model_case != "alias":
                selections = [("bedrock", False, "bearer", model_case)]
        else:
            selections = [("bedrock", False, "bearer", "denied"),
                          ("bedrock", False, "bearer", "default")]
        lanes: list[dict[str, Any]] = []
        async with asyncio.timeout(180):
            for provider, inspect_only, selected_auth, selected_model in selections:
                lane = await native_probe(provider, 0.10, inspect_only=inspect_only,
                                          auth_case=selected_auth, model_case=selected_model,
                                          auth_probes=action == "auth")
                lanes.append(lane)
                if not lane["passed"]:
                    break
        report = {"action": action, "mode": "live", "scenario": "normal",
                  "auth_case": auth_case, "model_case": model_case,
                  "run_id": str(uuid.uuid4()), "source_label": "native SDK subprocess",
                  "lanes": lanes, "closed": True,
                  "experiment_passed": len(lanes) == len(selections) and
                  all(lane["passed"] for lane in lanes)}
    oversized = len(json.dumps(report).encode()) > 2_000_000
    frames = sum(len(lane.get("frames", [])) + len(lane.get("receipts", []))
                 for lane in report["lanes"])
    if oversized or frames > 1500:
        report["experiment_passed"] = False
        report["evidence_bound_hit"] = True
        report["lanes"] = [{"name": lane.get("name", lane.get("provider")), "truncated": True}
                           for lane in report["lanes"]]
    if report["experiment_passed"]:
        folder = storage / report["run_id"]
        folder.mkdir(parents=True, exist_ok=True)
        report_path = folder / "report-new.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report_path.replace(folder / "report.json")
        (folder / "summary.json").write_text(json.dumps({"run_id": report["run_id"],
            "action": action, "mode": mode, "check": "passed"}), encoding="utf-8")
        pointer = storage / ("latest-" + report["run_id"] + ".json")
        pointer.write_text(json.dumps({"run_id": report["run_id"]}), encoding="utf-8")
        pointer.replace(storage / "latest.json")
    return report


async def execute_lesson(root: Path, request: RunRequest, settings: Settings,
                         emit: Any) -> dict[str, Any]:
    request = lesson_request(45, request)
    options = request.lesson_options
    report = await run(root / "owned-cloud", settings, options["action"],
                       "live" if request.mode == "live" else "local",
                       scenario="normal" if request.scenario == "success" else request.scenario,
                       auth_case=options["auth_case"], model_case=options["model_case"])
    if request.mode == "live":
        cost = sum(frame["cost_usd"] for lane in report["lanes"] for frame in lane["frames"]
                   if frame["kind"] == "result" and isinstance(frame.get("cost_usd"), (int, float)))
        await emit(Event(kind="result", data={"lesson_id": 45, "total_cost_usd": cost}))
    proof = {"experiment": report, "experiment_passed": report["experiment_passed"]}
    await emit(Event(kind="evidence", data={"lesson_id": 45, "result": proof}))
    return proof


async def local(root: Path, request: RunRequest) -> dict[str, Any]:
    async def ignore(event: Event) -> None:
        pass

    return await execute_lesson(root, request.model_copy(update={"mode": "offline"}),
                                Settings(), ignore)
