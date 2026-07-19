import json
from types import SimpleNamespace

from coding_kid.parser import parse_output


def test_parse_text_and_multiple_tool_calls() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="output_text", text="I will inspect both files."
                    )
                ],
            ),
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="read",
                arguments=json.dumps({"path": "one.py"}),
            ),
            SimpleNamespace(
                type="function_call",
                call_id="call-2",
                name="read",
                arguments=json.dumps({"path": "two.py"}),
            ),
        ]
    )

    parsed = parse_output(response)

    assert parsed.text == "I will inspect both files."
    assert [
        (call.call_id, call.name, call.arguments) for call in parsed.tool_calls
    ] == [
        ("call-1", "read", {"path": "one.py"}),
        ("call-2", "read", {"path": "two.py"}),
    ]


def test_parse_output_rejects_invalid_tool_arguments() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="read",
                arguments="not json",
            )
        ]
    )

    try:
        parse_output(response)
    except ValueError as error:
        assert "read" in str(error)
    else:
        raise AssertionError("invalid tool arguments should fail")


def test_parse_output_uses_aggregate_text_as_a_fallback() -> None:
    response = SimpleNamespace(
        output=[SimpleNamespace(type="reasoning")],
        output_text="Recovered final answer.",
    )

    parsed = parse_output(response)

    assert parsed.text == "Recovered final answer."


def test_parse_output_rejects_non_string_tool_arguments() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="read",
                arguments=None,
            )
        ]
    )

    try:
        parse_output(response)
    except ValueError as error:
        assert "read" in str(error)
    else:
        raise AssertionError("non-string tool arguments should fail")
