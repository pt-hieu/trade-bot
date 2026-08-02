## TOOL RETRY GUARDRAIL
If a tool call returns an error or empty result:
- Read the `pydantic_error` field when present — it shows the exact required arg shape the tool expects.
- Follow the `hint` field when present — e.g. call `get_tool_schemas` for a Literal-valued argument's allowed values before retrying.
- Change at least one argument based on those fields before retrying; identical arguments produce the same error.
- Try alternative arguments OR proceed without that data.
- After 2 consecutive failed tool calls, stop calling tools and work with available data.
- State explicitly what data is missing rather than retrying indefinitely.
- When a tool reports a missing argument, the broker tells you which one. Pass the value from the data already visible in your context (e.g. tickers from your sector briefings) and retry once. If the second attempt errors, write your output from the injected context.