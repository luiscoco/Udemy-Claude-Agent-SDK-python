import pytest

from agent_lab.hooks import call_hook, demo_elicitation_hook


@pytest.mark.parametrize(
    ("choice", "action"),
    [
        ("Accept", "accept"),
        ("Decline", "decline"),
        ("Cancel", "cancel"),
        ("yes please", "cancel"),
        ("", "cancel"),
    ],
)
async def test_demo_elicitation_requires_an_explicit_answer(choice, action):
    events = []

    async def ask(arguments):
        return {arguments["questions"][0]["question"]: choice}

    async def audit(kind, data):
        events.append((kind, data))

    output = await call_hook(
        demo_elicitation_hook(ask, audit),
        {
            "mcp_server_name": "rooms",
            "mode": "form",
            "requested_schema": {"properties": {"name": {}, "attendees": {}, "confirmed": {}}},
        },
        None,
    )
    specific = output["hookSpecificOutput"]
    assert specific["action"] == action
    if action == "accept":
        assert specific["content"] == {"name": "Student", "attendees": 2, "confirmed": True}
    else:
        assert "content" not in specific
    assert events == [("elicitation", {"action": action, "known_demo": True})]


@pytest.mark.parametrize(
    "payload",
    [
        {"mcp_server_name": "other", "requested_schema": {}},
        {"mcp_server_name": "rooms", "mode": "url", "url": "https://example.com"},
        {"mcp_server_name": "rooms", "requested_schema": {"properties": {"password": {}}}},
    ],
)
async def test_other_elicitations_are_declined_without_prompting(payload):
    async def ask(arguments):
        raise AssertionError("Only the local demo form may be shown")

    async def audit(kind, data):
        assert data == {"action": "decline", "known_demo": False}

    output = await call_hook(demo_elicitation_hook(ask, audit), payload, None)
    assert output["hookSpecificOutput"] == {"hookEventName": "Elicitation", "action": "decline"}
