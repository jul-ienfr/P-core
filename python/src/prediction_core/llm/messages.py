from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

OpenAIMessage = Mapping[str, Any]


def filter_openai_messages_for_provider(openai_messages: Iterable[OpenAIMessage]) -> list[OpenAIMessage]:
    """Return a provider-safe OpenAI chat history.

    Strict OpenAI-compatible gateways reject ``tool`` result messages when no
    earlier assistant message declares the matching ``tool_calls[].id``. Agent
    frameworks can leave those orphan results in memory after tool execution
    errors, so this keeps only provider-valid tool outputs and drops empty
    messages that add no usable context.
    """
    valid_tool_call_ids: set[str] = set()
    filtered: list[OpenAIMessage] = []

    for message in openai_messages:
        role = message.get("role")
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []

        if role == "assistant" and tool_calls:
            for tool_call in tool_calls:
                if not isinstance(tool_call, Mapping):
                    continue
                call_id = tool_call.get("id")
                if call_id:
                    valid_tool_call_ids.add(str(call_id))
            filtered.append(message)
            continue

        if role == "tool":
            call_id = _tool_call_id(message)
            if call_id in valid_tool_call_ids:
                filtered.append(message)
            continue

        if content is not None and str(content).strip():
            filtered.append(message)

    if not filtered:
        return [{"role": "user", "content": "(empty context)"}]
    return filtered


def _tool_call_id(message: OpenAIMessage) -> str | None:
    direct = message.get("tool_call_id")
    if direct:
        return str(direct)

    nested = message.get("tool_call")
    if isinstance(nested, Mapping):
        nested_id = nested.get("id")
        if nested_id:
            return str(nested_id)
    return None
