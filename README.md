# Structured Test-Case Agent

Give it a plain-English requirement. Get back structured test cases as JSON.

```
$ python agent.py "test a login form"
```

The JSON is **always** valid and **always** the same shape — not because we ask
nicely and parse carefully, but because the API enforces a schema. More on that
below.

---

## Setup

```bash
cd ~/structured-test-agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
```

Get a key from https://console.anthropic.com → API Keys.

Prefer not to re-export it every session? Create a `.env` file in this folder:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Don't commit that file.

---

## Usage

```bash
# Basic
python agent.py "test a login form"

# Ask for more cases
python agent.py "test a shopping cart checkout" --count 15

# Save to a file instead of printing
python agent.py "test a password reset flow" --out cases.json

# No argument? It'll ask you.
python agent.py
```

---

## Example output

```json
{
  "feature": "Login form",
  "assumptions": [
    "Assumes email + password authentication, not SSO or magic links"
  ],
  "test_cases": [
    {
      "id": "TC-001",
      "title": "Successful login with valid credentials",
      "type": "functional",
      "priority": "high",
      "preconditions": [
        "A registered, verified account exists for user@example.com"
      ],
      "steps": [
        "Navigate to /login",
        "Enter 'user@example.com' in the Email field",
        "Enter 'Correct-Horse-9!' in the Password field",
        "Click 'Sign in'"
      ],
      "test_data": "user@example.com / Correct-Horse-9!",
      "expected_result": "User is redirected to /dashboard and their name appears in the header"
    },
    {
      "id": "TC-002",
      "title": "Login rejected with wrong password",
      "type": "negative",
      "priority": "high",
      "preconditions": [
        "A registered account exists for user@example.com"
      ],
      "steps": [
        "Navigate to /login",
        "Enter 'user@example.com' in the Email field",
        "Enter 'wrong-password' in the Password field",
        "Click 'Sign in'"
      ],
      "test_data": "user@example.com / wrong-password",
      "expected_result": "An error 'Invalid email or password' is shown and the user stays on /login"
    }
  ]
}
```

Because the shape is guaranteed, downstream code can be blunt:

```python
from agent import generate_test_cases

result = generate_test_cases("test a login form")

for case in result["test_cases"]:
    print(case["id"], case["priority"], case["title"])
```

No `.get()` defensiveness, no key-existence checks.

---

## How the "always valid JSON" part works

The naive approach is to write *"reply with JSON and nothing else"* in the
prompt, then scrape the reply. That mostly works, and then one day the model
opens with "Certainly! Here's your JSON:" or wraps the object in a ```` ``` ````
fence, and your parser explodes at 2am.

This agent uses **tool-forced output** instead. Three pieces:

1. **A JSON Schema** (`TEST_CASE_SCHEMA` in `agent.py`) describing precisely
   what a test-case list looks like — field names, types, allowed enum values.

2. **A tool definition** wrapping that schema, marked `"strict": True`. Strict
   mode makes the API validate the model's arguments against the schema, and
   it requires `"additionalProperties": false` plus every property listed in
   `"required"`.

3. **Forced tool choice**: `tool_choice={"type": "tool", "name": "emit_test_cases"}`.
   This removes prose as an option. The model's only way to respond is to fill
   in the tool's arguments.

We never actually *execute* the tool. It's a typed form, not an action — the
tool's arguments are the answer. Reading it back is one line:

```python
for block in response.content:
    if block.type == "tool_use":
        return block.input   # already a validated Python dict
```

The trade-off worth knowing: strict mode has no optional fields, so every field
must be present on every test case. Fields that don't apply come back as `""`
or `[]`. That's why the code can index directly instead of checking.

---

## Files

| File               | What it is                                               |
| ------------------ | -------------------------------------------------------- |
| `agent.py`         | The whole agent — schema, prompt, API call, CLI          |
| `requirements.txt` | Two dependencies: `anthropic`, and optional `python-dotenv` |
| `README.md`        | This file                                                 |

---

## Customising it

Everything worth changing is near the top of `agent.py`.

**Add a field to every test case** — say, which browser to run it in. Add it to
the `properties` block *and* to the `required` list of the inner test-case
object. Strict mode rejects a schema where a property isn't required:

```python
"browser": {
    "type": "string",
    "description": "Browser to run this case in, or empty string for any.",
},
```

**Change the categories** — edit the `enum` on the `type` field. The model can
only choose from that list, so this is a hard constraint, not a suggestion.

**Change the testing style** — edit `SYSTEM_PROMPT`. That's where "senior QA
engineer", the one-assertion-per-case rule, and the concrete-test-data
preference live.

**Trade cost against depth** — `EFFORT` controls how much Claude thinks before
answering (`low` → `max`). `medium` suits a well-specified extraction task like
this. Raise it to `high` for broader, more imaginative coverage; drop to `low`
for fast, cheap, obvious cases.

**Swap models** — `MODEL` is set to `claude-opus-5`. `claude-sonnet-5` is faster
and cheaper; `claude-haiku-4-5` is cheapest. Model IDs are exact strings — no
date suffixes.

---

## Where to take it next

- Emit `pytest` skeletons or Playwright scripts from the JSON.
- Feed it a real ticket (Jira description, PR body) instead of one sentence.
- Add a second pass that reviews the generated cases for gaps in coverage.
- Batch a backlog of requirements through the
  [Batches API](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
  at half price.
