# Structured Test-Case Generation Agent

[![Tests](https://github.com/sadvi11/structured-test-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/sadvi11/structured-test-agent/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Schema](https://img.shields.io/badge/Output-strict%20JSON%20Schema-2088ff)
![Tool use](https://img.shields.io/badge/Anthropic-forced%20tool%20choice-d97757)
![License](https://img.shields.io/badge/License-MIT-green)

> An AI agent that turns a plain-English requirement into professional, structured test cases as strictly-validated JSON - using tool-forced schema output so the format is always valid.

## What It Does

Give it a requirement in plain English:

```bash
python agent.py "test a login form"
```

It returns a complete test suite as valid JSON - functional, negative, security, and boundary cases - each with ID, title, type, priority, preconditions, steps, test data, and expected result. From one line of input, it generated cases covering SQL injection, account lockout, email validation, and password masking.

## The Core Technique: Tool-Forced Structured Output

Most people ask an LLM for JSON and hope it comes back clean. This agent forces it:

```mermaid
flowchart TD
    A[Plain-English requirement] --> B[Define a tool whose schema IS the answer format]
    B --> C[Mark schema strict: every property required]
    C --> D[Force tool_choice to that tool]
    D --> E[Claude's only move is filling the schema]
    E --> F[Returns already-validated JSON]
    style F fill:#2ea44f,stroke:#1a7431,color:#ffffff
    style D fill:#2088ff,stroke:#0d47a1,color:#ffffff
```

Because the model is forced through a strict schema, there is nothing to parse and nothing that can come back malformed.

## How It Works

```mermaid
flowchart LR
    U[User requirement] --> AG[agent.py]
    AG --> API[Claude API]
    API --> TOOL[Strict tool schema, forced]
    TOOL --> OUT[Validated JSON test cases]
    style API fill:#D97757,stroke:#a04a30,color:#ffffff
    style OUT fill:#2ea44f,stroke:#1a7431,color:#ffffff
```

## Quick Start

```bash
git clone https://github.com/sadvi11/structured-test-agent.git
cd structured-test-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python agent.py "test a checkout flow"
```

## Why This Pattern Matters

Reliable structured output separates an AI demo from something you can put in a pipeline. Forcing the model through a strict schema makes the output contract-guaranteed - exactly what production integrations need. The technique generalises: extracting data from documents, generating config, producing API payloads.

## Tech Stack

Python, Anthropic Claude API, tool-forced structured output.

## Author

Sadhvi Sharma - Cloud & AI Engineer. Ex-Nokia (cloud-native 5G core, 99.9% SLA) -> Cloud & AI.
Calgary, AB, Canada. [LinkedIn](https://linkedin.com/in/sadhvi-sharma) - [GitHub](https://github.com/sadvi11)
