import { describe, it, expect } from "vitest";
import { parseSteps } from "./parse-steps";

// ─── helpers ──────────────────────────────────────────────────────────────────

const stepStart = () => ({ type: "step-start" });
const reasoning = (text: string, state: "streaming" | "done" = "done") => ({
  type: "reasoning",
  text,
  state,
});
const tool = (name: string, state = "output-available") => ({
  type: `tool-${name}`,
  state,
});
const data = (partType: string) => ({ type: `data-${partType}`, data: {} });
const text = (t: string) => ({ type: "text", text: t });

// ─── empty / trivial ──────────────────────────────────────────────────────────

describe("parseSteps", () => {
  it("returns empty array for empty parts", () => {
    expect(parseSteps([])).toEqual([]);
  });

  it("skips lone step-start with no content", () => {
    expect(parseSteps([stepStart()])).toEqual([]);
  });

  it("skips reasoning with blank text", () => {
    const result = parseSteps([{ type: "reasoning", text: "   ", state: "done" }]);
    expect(result).toEqual([]);
  });

  it("skips text part with only whitespace", () => {
    expect(parseSteps([{ type: "text", text: "\n  \t" }])).toEqual([]);
  });

  // ─── simple single-step responses ──────────────────────────────────────────

  it("single text response produces one step with textParts", () => {
    const result = parseSteps([text("Hello world")]);
    expect(result).toHaveLength(1);
    expect(result[0].textParts).toEqual([{ text: "Hello world" }]);
    expect(result[0].reasoning).toEqual([]);
    expect(result[0].toolParts).toEqual([]);
    expect(result[0].dataParts).toEqual([]);
  });

  it("reasoning + text produces one step", () => {
    const result = parseSteps([
      reasoning("Let me think"),
      text("The answer is 42"),
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].reasoning).toHaveLength(1);
    expect(result[0].reasoning[0].text).toBe("Let me think");
    expect(result[0].textParts[0].text).toBe("The answer is 42");
  });

  // ─── step-start boundaries (live streaming) ────────────────────────────────

  it("uses step-start as explicit boundary between steps", () => {
    const result = parseSteps([
      stepStart(),
      reasoning("Pre-tool think"),
      tool("get_portfolio"),
      stepStart(),
      reasoning("Post-tool think"),
      text("Portfolio looks good"),
    ]);

    expect(result).toHaveLength(2);

    // Step 1: reasoning + tool
    expect(result[0].reasoning[0].text).toBe("Pre-tool think");
    expect(result[0].toolParts).toHaveLength(1);
    expect(result[0].toolParts[0].type).toBe("tool-get_portfolio");
    expect(result[0].textParts).toHaveLength(0);

    // Step 2: reasoning + text
    expect(result[1].reasoning[0].text).toBe("Post-tool think");
    expect(result[1].textParts[0].text).toBe("Portfolio looks good");
    expect(result[1].toolParts).toHaveLength(0);
  });

  it("leading step-start before any content is ignored", () => {
    const result = parseSteps([
      stepStart(),
      reasoning("Thinking"),
      text("Response"),
    ]);
    expect(result).toHaveLength(1);
  });

  // ─── implicit boundary (DB-loaded, no step-start) ──────────────────────────

  it("reasoning after tool triggers implicit step boundary (DB-loaded scenario)", () => {
    // Simulates what comes back from DB after step-start is filtered out
    const result = parseSteps([
      reasoning("Pre-tool think"),
      tool("get_prices"),
      reasoning("Post-tool think"), // ← should trigger new step
      data("price-chart"),
      text("FPT closed at 90.5"),
    ]);

    expect(result).toHaveLength(2);

    // Step 1: pre-tool reasoning + tool call
    expect(result[0].reasoning[0].text).toBe("Pre-tool think");
    expect(result[0].toolParts[0].type).toBe("tool-get_prices");
    expect(result[0].dataParts).toHaveLength(0);
    expect(result[0].textParts).toHaveLength(0);

    // Step 2: post-tool reasoning + data + text
    expect(result[1].reasoning[0].text).toBe("Post-tool think");
    expect(result[1].dataParts[0].type).toBe("data-price-chart");
    expect(result[1].textParts[0].text).toBe("FPT closed at 90.5");
    expect(result[1].toolParts).toHaveLength(0);
  });

  it("reasoning before any tool does NOT trigger implicit boundary", () => {
    // Both reasoning blocks before a tool should be in the same step
    const result = parseSteps([
      reasoning("First thought"),
      reasoning("Second thought"),
      tool("get_portfolio"),
      text("Done"),
    ]);
    // No tool seen before second reasoning → stays in same step
    expect(result).toHaveLength(1);
    expect(result[0].reasoning).toHaveLength(2);
  });

  // ─── data parts placement ─────────────────────────────────────────────────

  it("data parts land in the same step as the text response (no thinking between them)", () => {
    // The original bug: thinking was sandwiched between chart and text
    const result = parseSteps([
      reasoning("Pre-tool think"),
      tool("get_prices"),
      reasoning("Post-tool think"),
      data("price-chart"),
      text("FPT +1.8% today"),
    ]);

    // Step 2 should have: reasoning → dataParts → textParts (no reasoning between data and text)
    const step2 = result[1];
    expect(step2.dataParts[0].type).toBe("data-price-chart");
    expect(step2.textParts[0].text).toBe("FPT +1.8% today");
    // reasoning is in same step but renders BEFORE data in the component
    expect(step2.reasoning[0].text).toBe("Post-tool think");
  });

  // ─── multi-tool steps ─────────────────────────────────────────────────────

  it("multiple tools in one step are grouped together", () => {
    const result = parseSteps([
      reasoning("Checking everything"),
      tool("get_portfolio"),
      tool("get_market_context"),
      text("Market is bullish"),
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].toolParts).toHaveLength(2);
  });

  // ─── reasoning state ──────────────────────────────────────────────────────

  it("preserves reasoning state (streaming vs done)", () => {
    const result = parseSteps([
      reasoning("Still thinking...", "streaming"),
    ]);
    expect(result[0].reasoning[0].state).toBe("streaming");
  });

  it("preserves done state on completed reasoning", () => {
    const result = parseSteps([
      reasoning("Finished", "done"),
      text("Response"),
    ]);
    expect(result[0].reasoning[0].state).toBe("done");
  });

  // ─── unknown part types ───────────────────────────────────────────────────

  it("ignores unknown part types without crashing", () => {
    const result = parseSteps([
      { type: "source-url", url: "https://example.com" },
      text("Response"),
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].textParts[0].text).toBe("Response");
  });
});
