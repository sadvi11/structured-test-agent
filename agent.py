"""
Structured Test-Case Agent
==========================

Give it a plain-English software requirement, e.g.:

    python agent.py "test a login form"

...and it returns a list of test cases as valid JSON, every time.

The "every time" part is the interesting bit. Instead of asking Claude to
"please reply with JSON" and then hoping (and writing a pile of regex to
scrape the JSON back out of a chatty answer), we define a *tool* whose
input schema IS the shape we want, and then force Claude to call it.
Claude fills in the tool's arguments, the API validates them against the
schema, and we read the result straight out as a Python dict.

No parsing. No retries. No "Sure! Here's your JSON:" preamble to strip.
"""

import argparse
import json
import os
import sys

import anthropic

# Optional: load ANTHROPIC_API_KEY from a .env file if one exists.
# Wrapped in try/except so the script still runs if dotenv isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

# Claude Opus 5 — Anthropic's current flagship model. Model IDs are exact
# strings; don't add date suffixes to them.
MODEL = "claude-opus-5"

# Upper bound on how much the model may generate for one request. This budget
# covers Claude's internal reasoning *and* the visible answer, so leave room.
MAX_TOKENS = 16000

# How hard Claude should think before answering: low | medium | high | xhigh | max.
# "medium" is a good balance for a well-defined extraction task like this one.
# Bump it to "high" if you want more thorough / more creative test coverage.
EFFORT = "medium"


# ---------------------------------------------------------------------------
# 2. The schema — this is the heart of the program
# ---------------------------------------------------------------------------
#
# This is a JSON Schema describing exactly what a test-case list looks like.
# Two details make it *strict* (guaranteed-valid) rather than merely suggested:
#
#   - "additionalProperties": false  -> no surprise extra keys
#   - every property listed in "required" -> no missing keys
#
# Because every field is required, there are no optional fields. When a field
# doesn't apply to a given test case, Claude fills in an empty string or an
# empty list rather than omitting it. That's a deliberate trade: your code can
# always do `case["test_data"]` without a KeyError.

TEST_CASE_SCHEMA = {
    "type": "object",
    "properties": {
        "feature": {
            "type": "string",
            "description": "Short name of the feature being tested, e.g. 'Login form'.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Anything the requirement left unsaid that you had to assume "
                "(e.g. 'assumes email/password auth, not SSO'). Empty list if none."
            ),
        },
        "test_cases": {
            "type": "array",
            "description": "The generated test cases.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable identifier, e.g. 'TC-001'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "One-line summary of what this case verifies.",
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "functional",
                            "negative",
                            "boundary",
                            "security",
                            "usability",
                            "performance",
                        ],
                        "description": "Category of test.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "How important this case is to run.",
                    },
                    "preconditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "State that must exist before the steps run.",
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered actions the tester performs, in order.",
                    },
                    "test_data": {
                        "type": "string",
                        "description": "Concrete inputs to use. Empty string if not applicable.",
                    },
                    "expected_result": {
                        "type": "string",
                        "description": "The single observable outcome that means this test passed.",
                    },
                },
                "required": [
                    "id",
                    "title",
                    "type",
                    "priority",
                    "preconditions",
                    "steps",
                    "test_data",
                    "expected_result",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["feature", "assumptions", "test_cases"],
    "additionalProperties": False,
}


# The tool definition. Claude never "runs" this tool — we only use it as a
# typed form for Claude to fill out. `strict: True` tells the API to enforce
# the schema, so `block.input` is guaranteed to match it.
EMIT_TEST_CASES_TOOL = {
    "name": "emit_test_cases",
    "description": "Record the generated test cases for the given requirement.",
    "strict": True,
    "input_schema": TEST_CASE_SCHEMA,
}


# ---------------------------------------------------------------------------
# 3. The prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior QA engineer. You turn short, informal feature requirements \
into concrete, executable test cases.

Guidelines:
- Cover the happy path first, then negative cases, boundaries, and security \
  concerns where they are relevant to the feature.
- Write steps a person (or an automation script) can follow literally. \
  "Enter 'user@example.com' in the Email field" beats "provide valid input".
- Each test case has exactly one expected result. If you find yourself \
  verifying two unrelated things, split it into two cases.
- Use realistic, concrete test data.
- If the requirement is vague, pick the most common interpretation, proceed, \
  and record what you assumed in the `assumptions` field.
"""


# ---------------------------------------------------------------------------
# 4. The agent
# ---------------------------------------------------------------------------


def generate_test_cases(requirement: str, count: int = 8) -> dict:
    """Send the requirement to Claude and return the test cases as a dict.

    The returned dict always matches TEST_CASE_SCHEMA.
    """
    # Reads ANTHROPIC_API_KEY from the environment. Don't hardcode your key.
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"effort": EFFORT},
        system=SYSTEM_PROMPT,
        tools=[EMIT_TEST_CASES_TOOL],
        # This is the "forced" part: Claude MUST call this specific tool, so it
        # cannot reply with prose instead. Its only way to answer is the schema.
        tool_choice={"type": "tool", "name": "emit_test_cases"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Requirement: {requirement}\n\n"
                    f"Generate roughly {count} test cases covering this requirement."
                ),
            }
        ],
    )

    # A response is a list of content blocks (thinking, text, tool_use, ...).
    # We want the tool_use block — its `.input` is the validated dict.
    for block in response.content:
        if block.type == "tool_use":
            return block.input

    # Practically unreachable with a forced tool_choice, but never let a
    # surprise turn into a confusing crash somewhere further downstream.
    raise RuntimeError(
        f"Claude did not call the tool (stop_reason={response.stop_reason}). "
        "This can happen if the request was refused."
    )


# ---------------------------------------------------------------------------
# 5. Command-line interface
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a plain-English requirement into structured test cases."
    )
    parser.add_argument(
        "requirement",
        nargs="?",
        help='What to test, e.g. "test a login form". Prompts if omitted.',
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=8,
        help="Roughly how many test cases to generate (default: 8).",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="Write the JSON to this file instead of printing it.",
    )
    args = parser.parse_args()

    requirement = args.requirement or input("What should I write test cases for? ").strip()
    if not requirement:
        print("Nothing to test. Give me a requirement.", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "or put it in a .env file next to this script.",
            file=sys.stderr,
        )
        return 1

    try:
        result = generate_test_cases(requirement, count=args.count)
    except anthropic.AuthenticationError:
        print("Your API key was rejected. Double-check ANTHROPIC_API_KEY.", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("Rate limited by the API. Wait a moment and try again.", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("Couldn't reach the API. Check your internet connection.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as exc:
        print(f"API error {exc.status_code}: {exc.message}", file=sys.stderr)
        return 1

    pretty = json.dumps(result, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(pretty + "\n")
        print(f"Wrote {len(result['test_cases'])} test cases to {args.out}")
    else:
        print(pretty)

    return 0


if __name__ == "__main__":
    sys.exit(main())
