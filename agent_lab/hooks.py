"""Hook and permission callbacks shared by live SDK runs and the offline hook lessons.

Live runs register these with ClaudeAgentOptions; offline lessons call the same functions
with SDK-shaped inputs, so the policy students inspect is the policy the agent meets.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

from claude_agent_sdk import (
    HookCallback,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
)
from claude_agent_sdk.types import HookEvent

Permitted = Callable[[str, dict[str, Any]], tuple[bool, str]]
Audit = Callable[[str, dict[str, Any]], Awaitable[None]]
Ask = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def demo_elicitation_hook(ask: Ask, audit: Audit) -> HookCallback:
    """Bridge only the local rooms demo to the lesson's existing question UI."""

    async def answer(
        arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        data = cast(dict[str, Any], arguments)
        schema = data.get("requested_schema", {})
        expected = (
            data.get("mcp_server_name") == "rooms"
            and data.get("mode", "form") == "form"
            and isinstance(schema, dict)
            and isinstance(schema.get("properties"), dict)
            and set(schema.get("properties", {})) == {"name", "attendees", "confirmed"}
        )
        action = "decline"
        if expected:
            question = (
                "Allow the local demo booking for Student with 2 attendees? "
                "No external calendar is contacted."
            )
            response = await ask(
                {
                    "questions": [
                        {
                            "question": question,
                            "header": "Demo booking",
                            "multiSelect": False,
                            "options": [
                                {
                                    "label": "Accept",
                                    "description": "Confirm the local demonstration booking.",
                                },
                                {"label": "Decline", "description": "Refuse the booking."},
                                {"label": "Cancel", "description": "Cancel this request."},
                            ],
                        }
                    ]
                }
            )
            # A missing answer or free text never authorizes the operation.
            action = {"Accept": "accept", "Decline": "decline", "Cancel": "cancel"}.get(
                response.get(question, ""), "cancel"
            )
        output: dict[str, Any] = {"hookEventName": "Elicitation", "action": action}
        if action == "accept":
            output["content"] = {"name": "Student", "attendees": 2, "confirmed": True}
        await audit("elicitation", {"action": action, "known_demo": expected})
        return cast(HookJSONOutput, {"hookSpecificOutput": output})

    return answer


def pre_tool_hook(permitted: Permitted, audit: Audit) -> HookCallback:
    async def pre_tool(
        arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        name = str(arguments.get("tool_name", ""))
        allowed, reason = permitted(name, cast(dict[str, Any], arguments.get("tool_input", {})))
        await audit("hook", {"tool": name, "allowed": allowed, "reason": reason})
        # Allow decisions skip later permission checks; AskUserQuestion needs the callback.
        if name == "AskUserQuestion" and allowed:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allowed else "deny",
                "permissionDecisionReason": reason,
            }
        }

    return pre_tool


def post_tool_hook(audit: Audit) -> HookCallback:
    async def post_tool(
        arguments: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        # Record the outcome size, never the content: tool results can hold private data.
        response = arguments.get("tool_response")
        await audit(
            "audit",
            {
                "tool": str(arguments.get("tool_name", "")),
                "tool_use_id": tool_use_id,
                "result_characters": len(str(response)) if response is not None else 0,
            },
        )
        return {}

    return post_tool


def lesson_hooks(permitted: Permitted, audit: Audit) -> dict[HookEvent, list[HookMatcher]]:
    return {
        "PreToolUse": [HookMatcher(hooks=[pre_tool_hook(permitted, audit)])],
        "PostToolUse": [HookMatcher(hooks=[post_tool_hook(audit)])],
    }


def matches(matcher: str | None, tool_name: str) -> bool:
    """The CLI's matcher rule: no matcher or "*" matches every tool, otherwise a regex."""
    return matcher in {None, "", "*"} or re.fullmatch(str(matcher), tool_name) is not None


async def call_hook(
    callback: HookCallback, payload: dict[str, Any], tool_use_id: str | None
) -> dict[str, Any]:
    """Invoke a registered hook with a CLI-shaped input, as offline lessons do."""
    output = await callback(cast(HookInput, payload), tool_use_id, {"signal": None})
    return cast(dict[str, Any], output)


def permission_callback(permitted: Permitted, ask: Ask | None = None) -> Callable[..., Any]:
    async def permission(name: str, arguments: dict[str, Any], context: Any) -> Any:
        allowed, reason = permitted(name, arguments)
        if not allowed:
            return PermissionResultDeny(message=reason)
        if name == "AskUserQuestion" and ask is not None:
            from agent_lab.sdk import Questions

            parsed = Questions.model_validate(arguments)
            response = await ask(parsed.model_dump())
            return PermissionResultAllow(updated_input={**arguments, "answers": response})
        return PermissionResultAllow(updated_input=arguments)

    return permission
