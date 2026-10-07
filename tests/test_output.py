from agent_lab.models import Event
from agent_lab.output import OutputState


def message(**data):
    return Event(kind="message", data=data)


def test_live_answer_omits_init_thinking_and_tools_and_deduplicates_final_result():
    output = OutputState(mode="live")
    assert not output.apply(
        message(message_class="SystemMessage", subtype="init", data={"session_id": "private"})
    )
    output.apply(
        message(
            message_class="AssistantMessage",
            content=[
                {"thinking": "internal reasoning"},
                {"name": "calculator", "input": {"a": 19}},
                {"text": "## Answer\n\n**42** is the result."},
            ],
        )
    )
    output.apply(
        Event(
            kind="result",
            data={
                "result": "## Answer\n\n**42** is the result.",
                "num_turns": 1,
                "total_cost_usd": 0.01,
            },
        )
    )
    assert output.response_texts == ["## Answer\n\n**42** is the result."]
    assert output.turns == 1
    assert output.cost == 0.01


def test_streaming_preview_is_replaced_by_complete_assistant_message():
    output = OutputState(mode="live")
    for text in ("Hello", " world"):
        output.apply(
            message(
                message_class="StreamEvent", event={"delta": {"type": "text_delta", "text": text}}
            )
        )
    assert output.response_texts == ["Hello world"]
    output.apply(message(message_class="AssistantMessage", content=[{"text": "Hello world"}]))
    output.apply(Event(kind="result", data={"result": "Hello world"}))
    assert output.response_texts == ["Hello world"]


def test_follow_up_and_result_only_responses_are_preserved():
    output = OutputState(mode="live")
    output.apply(Event(kind="result", data={"result": "First answer"}))
    output.apply(message(message_class="AssistantMessage", content=[{"text": "Follow-up answer"}]))
    output.apply(Event(kind="result", data={"result": "Follow-up answer"}))
    assert output.response_texts == ["First answer", "Follow-up answer"]


def test_structured_response_validation_is_not_duplicated():
    output = OutputState(mode="live")
    value = {"summary": "Complete", "next_steps": ["Review"]}
    output.apply(Event(kind="result", data={"structured_output": value}))
    output.apply(Event(kind="validated", data=value))
    assert output.results == [("Structured response", value)]


def test_fixture_is_separate_from_live_response_and_error_is_visible():
    output = OutputState(mode="live")
    output.apply(Event(kind="evidence", data={"result": {"text": ["Recorded test text"]}}))
    output.apply(Event(kind="error", data={"message": "Authentication failed"}))
    output.apply(Event(kind="done", data={"status": "failed"}))
    assert not output.response_texts
    assert output.error == "Authentication failed"
    assert output.status == "failed"
    assert output.evidence == {"text": ["Recorded test text"]}


def test_partial_response_survives_cancellation_and_nested_agent_text_is_not_main_answer():
    output = OutputState(mode="live")
    assert not output.apply(
        message(
            message_class="AssistantMessage",
            parent_tool_use_id="child",
            content=[{"text": "Child response"}],
        )
    )
    output.apply(message(message_class="AssistantMessage", content=[{"text": "Partial answer"}]))
    output.apply(Event(kind="done", data={"status": "cancelled"}))
    assert output.response_texts == ["Partial answer"]
    assert output.status == "cancelled"
