from prediction_core.llm.messages import filter_openai_messages_for_provider


def test_filters_orphan_tool_outputs_without_matching_tool_calls() -> None:
    messages = [
        {"role": "system", "content": "act as a trader"},
        {"role": "tool", "tool_call_id": "call_orphan", "content": "done"},
        {"role": "user", "content": "observe market"},
    ]

    filtered = filter_openai_messages_for_provider(messages)

    assert filtered == [
        {"role": "system", "content": "act as a trader"},
        {"role": "user", "content": "observe market"},
    ]


def test_keeps_tool_outputs_when_prior_assistant_declares_matching_tool_call() -> None:
    messages = [
        {"role": "system", "content": "act as a trader"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_ok", "type": "function", "function": {"name": "BUY_SHARES", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_ok", "content": "bought"},
        {"role": "user", "content": "next round"},
    ]

    filtered = filter_openai_messages_for_provider(messages)

    assert filtered == messages


def test_drops_empty_messages_except_assistant_tool_call_messages() -> None:
    messages = [
        {"role": "system", "content": ""},
        {"role": "assistant", "content": None},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_ok", "type": "function", "function": {"name": "SELL_SHARES", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_ok", "content": "sold"},
    ]

    filtered = filter_openai_messages_for_provider(messages)

    assert filtered == [messages[2], messages[3]]


def test_returns_empty_context_user_message_when_everything_is_filtered() -> None:
    assert filter_openai_messages_for_provider([
        {"role": "tool", "tool_call_id": "call_orphan", "content": "done"},
        {"role": "assistant", "content": ""},
    ]) == [{"role": "user", "content": "(empty context)"}]


def test_preserves_input_message_objects_without_mutating_them() -> None:
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_ok", "type": "function", "function": {"name": "HOLD", "arguments": "{}"}}],
    }
    tool = {"role": "tool", "tool_call_id": "call_ok", "content": "held"}
    messages = [assistant, tool]

    filtered = filter_openai_messages_for_provider(messages)

    assert filtered == [assistant, tool]
    assert filtered[0] is assistant
    assert messages == [assistant, tool]
