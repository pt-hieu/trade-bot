---
name: ai-sdk
description: 'Answer questions about the Vercel AI SDK and help build AI-powered features in web/. Use when working on generateText, streamText, agents, tool calling, structured output, embeddings, or the useChat / useCompletion React hooks.'
---

## Read the installed docs, not memory

The AI SDK changes fast and model knowledge of it is usually stale. Before answering,
read the docs shipped inside the installed package:

```
web/node_modules/ai/docs/
```

If that directory is missing, install the `ai` package first with the project's package
manager, then read it. Install provider packages (`@ai-sdk/openai`, `@ai-sdk/anthropic`)
and client packages (`@ai-sdk/react`) only once you know which ones the task needs.

Quote the version you read from `web/node_modules/ai/package.json` when the answer
depends on API shape.

## Where this repo uses it

- `web/src/lib/chat/agents/` — coordinator and sub-agent wiring
- `web/src/lib/chat/tools/` — tool definitions, including the tool broker
- `web/src/routes/api/chat.ts` — `streamText` config and step limits

See the `coordinator-architecture` skill for the design rules those files follow.
