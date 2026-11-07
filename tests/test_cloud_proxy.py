"""Actual loopback HTTP checks for the owned Lesson 45 local proxy."""

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from agent_lab.cloud_proxy import AUDIENCE, GRANT_TYPE, SUBJECT_TYPE, CloudProxy
from agent_lab.cloud_wire import HAIKU, PROFILE, SONNET, fixture_sigv4
from agent_lab.exercises import EmbeddedServer


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["firstParty", "bedrock", "vertex", "foundry", "gateway"])
async def test_owned_local_provider_http(provider: str) -> None:
    run_id = str(uuid.uuid4())
    proxy = CloudProxy(run_id, "main", provider)
    async with EmbeddedServer(proxy).running() as base:
        proxy.base = base
        prefix = f"{base}{proxy.prefix}"
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            denied = await client.get(prefix + "/catalog")
            assert denied.status_code == 401
            headers: dict[str, str] = {}
            if provider == "vertex":
                sts = await client.post(prefix + "/sts", json={
                    "audience": AUDIENCE, "grant_type": GRANT_TYPE,
                    "subject_token_type": SUBJECT_TYPE, "subject_token": proxy.subject})
                assert sts.status_code == 200
                headers["Authorization"] = "Bearer " + sts.json()["access_token"]
            elif provider == "gateway":
                headers["Authorization"] = "Bearer " + proxy.bearer
            elif provider in {"firstParty", "foundry"}:
                headers["x-api-key"] = proxy.bearer
            else:
                headers["Authorization"] = "Bearer " + proxy.bearer
            catalog = await client.get(prefix + "/catalog", headers=headers)
            assert catalog.status_code == 200
            assert HAIKU in catalog.json()["models"]
            suffix = ("/model/" + PROFILE + "/invoke" if provider == "bedrock"
                      else "/v1/projects/lesson45-project/locations/us-east5/publishers/anthropic/models/" + HAIKU + ":rawPredict"
                      if provider == "vertex" else "/anthropic/v1/messages"
                      if provider == "foundry" else "/v1/messages")
            body = json.dumps({"model": HAIKU, "messages": [{"role": "user", "content": "READY L45-FIXTURE"}]}).encode()
            response = await client.post(prefix + suffix, content=body, headers=headers)
            assert response.status_code == 200
            assert response.json()["id"].startswith("msg_")
            receipt = proxy.receipts[-1]
            assert receipt["auth_verdict"] and receipt["canonical_model"] == HAIKU
            assert receipt["message_id"] == response.json()["id"]
            assert all("secret" not in json.dumps(row) and "access_token" not in json.dumps(row)
                       for row in proxy.receipts)


@pytest.mark.asyncio
async def test_bedrock_literal_host_sigv4_and_denial() -> None:
    run_id = str(uuid.uuid4())
    proxy = CloudProxy(run_id, "main", "bedrock")
    async with EmbeddedServer(proxy).running() as base:
        proxy.base = base
        suffix = "/model/" + HAIKU + "/invoke"
        path = (proxy.prefix + suffix).encode()
        body = b'{"messages":[{"role":"user","content":"READY L45-FIXTURE"}]}'
        headers = {"Host": "127.0.0.1", "x-amz-date": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")}
        headers["Authorization"] = fixture_sigv4(
            "POST", path, b"", headers, body, proxy.access_id, proxy.secret, "us-east-1")
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            good = await client.post(base + proxy.prefix + suffix, content=body, headers=headers)
            assert good.status_code == 200
            bad_body = await client.post(base + proxy.prefix + suffix, content=body + b" ", headers=headers)
            assert bad_body.status_code == 401
            bad_host = await client.post(base + proxy.prefix + suffix, content=body,
                                         headers={**headers, "Host": "127.0.0.1:9999"})
            assert bad_host.status_code == 400
            denied = await client.post(base + proxy.prefix + "/model/" + SONNET + "/invoke",
                                       content=body, headers={"Authorization": "Bearer " + proxy.bearer})
            assert denied.status_code == 403
            assert proxy.receipts[-1]["canonical_model"] == SONNET


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["firstParty", "bedrock"])
async def test_injected_upstream_sender_and_message_identity(provider: str) -> None:
    sent: list[dict[str, str]] = []
    body = (b'event: message_start\ndata: {"type":"message_start",'
            b'"message":{"id":"msg_owned_45"}}\n\n'
            b'event: message_stop\ndata: {"type":"message_stop"}\n\n')

    def upstream(request: httpx.Request) -> httpx.Response:
        sent.append({"url": str(request.url), "key": request.headers.get("x-api-key", ""),
                     "model": json.loads(request.content)["model"]})
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    run_id = str(uuid.uuid4())
    proxy = CloudProxy(run_id, "main", provider, upstream_key="private-host-key",
                       upstream_transport=httpx.MockTransport(upstream))
    async with EmbeddedServer(proxy).running() as base:
        proxy.base = base
        suffix = ("/model/" + HAIKU + "/invoke-with-response-stream" if provider == "bedrock"
                  else "/v1/messages")
        headers = ({"Authorization": "Bearer " + proxy.bearer} if provider == "bedrock"
                   else {"x-api-key": proxy.bearer})
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.post(base + proxy.prefix + suffix,
                                         json={"model": HAIKU, "messages": [
                                             {"role": "user", "content": "READY L45-OWNED"}],
                                             "max_tokens": 500, "stream": True}, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == (
            "application/vnd.amazon.eventstream" if provider == "bedrock" else "text/event-stream")
        assert sent == [{"url": "https://api.anthropic.com/v1/messages", "key": "private-host-key",
                         "model": HAIKU}]
        receipt = proxy.receipts[-1]
        assert receipt["upstream_status"] == 200
        assert receipt["message_id"] == "msg_owned_45"
        assert receipt["marker_seen"] == "L45-OWNED"
        assert proxy.bearer not in json.dumps(sent)
        assert "private-host-key" not in json.dumps(proxy.receipts)
