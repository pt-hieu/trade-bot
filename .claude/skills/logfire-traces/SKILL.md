---
name: logfire-traces
description: Placeholder. Observability account details are not published. Use when debugging agent runs — then point it at your own project.
---

# Logfire Traces — redacted

The real contents of this skill are not published. It named a specific
observability project, its service identifier, and the query endpoint, all of
which are useful only to someone holding that project's token.

## What it did

Agent runs are instrumented with [Logfire](https://pydantic.dev/logfire), which
PydanticAI supports natively. Traces capture each agent's reasoning, every tool
call and its arguments, and the structured output — which is the only practical
way to answer "why did the agent decide that".

The useful queries were:

- find the run, then read the tool-call sequence to see what data the agent
  actually had when it decided
- filter by structured-output rejection to find prompts producing invalid shapes
- compare token spend per agent across runs to find prompt bloat

## If you are running your own copy

Set your own `LOGFIRE_TOKEN` and service name. Write your own version of this
skill against your project.
