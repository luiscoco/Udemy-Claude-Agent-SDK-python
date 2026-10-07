import json

import httpx
import pytest
from claude_agent_sdk import ResultMessage, create_sdk_mcp_server, tool
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from agent_lab.document_builder import DocumentSpec, build_document
from agent_lab.integrations.channels import notify_email, notify_slack, notify_teams
from agent_lab.integrations.review_ci import changed_lines, run_review
from agent_lab.integrations.rooms_mcp import mcp as rooms
from agent_lab.services import Calculation


async def test_official_sdk_custom_tool_schema_and_error_mapping():
    @tool("add", "Add finite numbers", Calculation.model_json_schema())
    async def add(arguments):
        value = Calculation.model_validate(arguments)
        return {"content": [{"type": "text", "text": str(value.a + value.b)}]}

    server = create_sdk_mcp_server("calculator", tools=[add])
    async with create_connected_server_and_client_session(server["instance"]) as session:
        good = await session.call_tool("add", {"a": 20, "b": 22})
        assert not good.isError
        assert good.content[0].text == "42.0"
        bad = await session.call_tool("add", {"a": True, "b": 22})
        assert bad.isError


async def test_real_mcp_elicitation_accept_and_decline():
    async def accepted(context, request):
        assert request.requestedSchema["properties"]["attendees"]["maximum"] == 8
        return types.ElicitResult(
            action="accept", content={"name": "Student", "attendees": 2, "confirmed": True}
        )

    async with create_connected_server_and_client_session(
        rooms, elicitation_callback=accepted
    ) as session:
        result = await session.call_tool("book_room", {"room": "Blue"})
        assert json.loads(result.content[0].text)["booked"]

    async def declined(context, request):
        return types.ElicitResult(action="decline")

    async with create_connected_server_and_client_session(
        rooms, elicitation_callback=declined
    ) as session:
        result = await session.call_tool("book_room", {"room": "Blue"})
        assert not json.loads(result.content[0].text)["booked"]


async def test_channels_only_use_explicit_mock_client_and_never_leak_credentials():
    requests = []

    def dispatch(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(dispatch)) as client:
        await notify_slack("test-token", "demo", "Approval requested", client)
        await notify_teams("https://example.invalid/workflow", "Approval requested", client)
        await notify_email(
            "test-token",
            "sender@example.invalid",
            "student@example.invalid",
            "Approval requested",
            client,
        )
    assert len(requests) == 3
    assert requests[0].headers["authorization"] == "Bearer test-token"
    assert "test-token" not in requests[0].content.decode()


def test_document_spec_and_actual_word_file(tmp_path):
    from docx import Document

    specification = DocumentSpec(
        kind="general",
        title="Python report",
        author="Instructor",
        date="2026-10-07",
        classification="Internal",
        blocks=[
            {"type": "paragraph", "text": "A **validated** Python document."},
            {
                "type": "table",
                "columns": ["Owner", "Action"],
                "rows": [["Student", "Run the example"]],
            },
        ],
    )
    path = build_document(specification, tmp_path / "report.docx")
    document = Document(path)
    assert "Python report" in document.paragraphs[0].text
    assert document.tables[0].cell(1, 0).text == "Student"
    with pytest.raises(ValidationError):
        DocumentSpec.model_validate({**specification.model_dump(), "kind": "incident-report"})


async def test_review_gate_discards_out_of_scope_findings(tmp_path, monkeypatch):
    import agent_lab.integrations.review_ci as review
    from agent_lab.config import Settings

    diff = "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1,1 +1,2 @@\n keep\n+broken = 1\n"
    assert changed_lines(diff) == {"src/a.py": {2}}

    async def query(**kwargs):
        assert kwargs["options"].tools == []
        yield ResultMessage(
            subtype="success",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=1,
            session_id="fixture",
            total_cost_usd=0,
            structured_output={
                "findings": [
                    {
                        "file": "src/a.py",
                        "line": 2,
                        "severity": "high",
                        "message": "Fixture finding",
                    },
                    {
                        "file": "outside.py",
                        "line": 1,
                        "severity": "critical",
                        "message": "Out of scope",
                    },
                ]
            },
        )

    monkeypatch.setattr(review, "query", query)
    result = await run_review(diff, Settings(enable_live=True))
    assert result["blocking"]
    assert result["rejected_out_of_scope"] == 1
    assert len(result["findings"]) == 1
