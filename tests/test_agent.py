"""Tests for the structured test-case agent.

None of these need an API key. That is deliberate: the claim this project
makes is that the *schema* guarantees valid output, and the schema is a static
artifact. If the schema stops satisfying the strict-tool-use requirements, the
guarantee quietly degrades to "usually valid" with no error anywhere — so the
invariants that make it strict are asserted here rather than assumed.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent  # noqa: E402


# Retired model IDs return 404. A retired pin looks correct in code and fails
# on every request, so it is worth failing the build over.
RETIRED_MODELS = {
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-5-haiku-20241022",
    "claude-3-7-sonnet-20250219",
}


def test_model_is_not_retired():
    assert agent.MODEL not in RETIRED_MODELS, f"{agent.MODEL} is retired and will 404"


def test_tool_is_marked_strict():
    """`strict` is what turns a suggested schema into an enforced one."""
    assert agent.EMIT_TEST_CASES_TOOL.get("strict") is True


def test_tool_definition_is_well_formed():
    tool = agent.EMIT_TEST_CASES_TOOL
    for field in ("name", "description", "input_schema"):
        assert field in tool, f"tool definition missing {field!r}"
    assert tool["input_schema"] is agent.TEST_CASE_SCHEMA


def _objects(schema):
    """Yield every object-typed subschema, recursively."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for value in schema.values():
            yield from _objects(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _objects(item)


def test_every_object_forbids_extra_properties():
    """Strict tool use requires additionalProperties: false on every object.

    Miss one and that object silently accepts keys you never defined.
    """
    for obj in _objects(agent.TEST_CASE_SCHEMA):
        assert obj.get("additionalProperties") is False, (
            f"object with properties {sorted(obj.get('properties', {}))} "
            "does not set additionalProperties: false"
        )


def test_every_property_is_required():
    """Strict mode requires every declared property to appear in `required`."""
    for obj in _objects(agent.TEST_CASE_SCHEMA):
        declared = set(obj.get("properties", {}))
        required = set(obj.get("required", []))
        assert declared == required, (
            f"schema object declares {sorted(declared)} but requires "
            f"{sorted(required)}; strict mode needs them identical"
        )


def test_generate_returns_the_tool_input():
    """The answer is the tool_use block's input, not the assistant's prose."""
    payload = {"feature": "login", "assumptions": [], "test_cases": []}

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = payload

    text_block = MagicMock()
    text_block.type = "text"

    response = MagicMock()
    # Text first, so a naive content[0] read would return the wrong block.
    response.content = [text_block, tool_block]

    with patch.object(agent.anthropic, "Anthropic") as client_cls:
        client_cls.return_value.messages.create.return_value = response
        assert agent.generate_test_cases("users can log in") is payload


def test_request_forces_the_tool():
    """tool_choice must pin the tool, or Claude may answer in prose instead."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {}
    response = MagicMock()
    response.content = [tool_block]

    with patch.object(agent.anthropic, "Anthropic") as client_cls:
        create = client_cls.return_value.messages.create
        create.return_value = response
        agent.generate_test_cases("anything")

    kwargs = create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_test_cases"}
    assert kwargs["model"] == agent.MODEL
