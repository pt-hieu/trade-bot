/**
 * Coordinator delegation tools.
 * Each tool wraps a sub-agent using the SDK-native preliminary tool results pattern:
 * - execute is an async generator that yields UIMessage snapshots as streaming progress
 * - agent.stream() + readUIMessageStream() drives real-time rendering on the client
 * - toModelOutput extracts the final text summary for the coordinator model
 * - renderData (charts/tables) is pushed via writer after the sub-agent stream completes
 */
import { z } from "zod";
import { readUIMessageStream } from "ai";
import type { Tool, LanguageModel, UIMessageStreamWriter, UIMessage } from "ai";

type JSONValue = null | string | number | boolean | JSONObject | JSONValue[];
type JSONObject = { [key: string]: JSONValue };
type ProviderOptions = Record<string, JSONObject>;
import type { SwingyUIMessage } from "../data-parts";
import type { RenderDataItem } from "./types";
import type { SubAgentModelKey } from "../models";
import {
  createResearchAnalyst,
  createStrategyAdvisor,
} from "./sub-agents";
import { TOOL_DATA_MAP } from "../data-parts";
import { buildBrokerTools } from "../tools/broker";

type Writer = UIMessageStreamWriter<SwingyUIMessage>;
type ModelMap = Record<SubAgentModelKey, LanguageModel>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Collect renderable tool results from a completed sub-agent run
function collectRenderData(
  steps: Array<{
    toolResults?: Array<{ toolName: string; input: unknown; output: unknown }>;
  }>,
): RenderDataItem[] {
  return steps.flatMap((step) =>
    (step.toolResults ?? [])
      .filter((tr) => {
        const inp = tr.input as { render?: boolean };
        return inp?.render && TOOL_DATA_MAP[tr.toolName];
      })
      .map((tr) => {
        let data = tr.output;
        if (typeof data === "string") {
          try {
            data = JSON.parse(data);
          } catch {
            /* keep as string */
          }
        }
        return { toolName: tr.toolName, input: tr.input, data };
      }),
  );
}

// Extract final text from the last UIMessage snapshot
function extractFinalText(message: UIMessage | undefined): string {
  const lastText = message?.parts?.findLast((p) => p.type === "text") as
    | { text: string }
    | undefined;
  return lastText?.text ?? "Task completed.";
}

// Stream a sub-agent and yield UIMessage snapshots as preliminary tool results.
// After the stream completes, push any renderable data parts via the writer.
async function* runSubAgentStreaming(
  agent: any, // ToolLoopAgent with varying TOOLS generic — typed as any to avoid PromiseLike/Promise mismatch
  writer: Writer,
  prompt: string,
): AsyncGenerator<UIMessage> {
  const streamResult = await agent.stream({ prompt });

  for await (const message of readUIMessageStream({
    stream: streamResult.toUIMessageStream(),
  })) {
    yield message as UIMessage;
  }

  // Push renderData (charts, tables) via writer after stream completes
  const steps = await streamResult.steps;
  const renderData = collectRenderData(steps);
  for (const rd of renderData) {
    const mapping = TOOL_DATA_MAP[rd.toolName];
    if (!mapping) continue;
    try {
      const data = mapping.transform(rd.data, rd.input);
      (writer.write as (chunk: unknown) => void)({
        type: `data-${mapping.partType}`,
        data,
      });
    } catch (e) {
      console.error(
        `[coordinator] Failed to push data part for ${rd.toolName}:`,
        e,
      );
    }
  }
}

// ─── Delegation Tool Factories ────────────────────────────────────────────────

type MaybeProviderOptions = ProviderOptions | undefined;

const modelSchema = z.enum(["heavy", "light"]).optional().describe(
  "Model tier: heavy for deep analysis, light for data lookups. Omit to use session default.",
);

type DelegationInput = { question: string; tickers?: string[]; model?: SubAgentModelKey };

function resolveModel(modelMap: ModelMap, defaultModel: LanguageModel, key?: SubAgentModelKey): LanguageModel {
  return key ? modelMap[key] : defaultModel;
}

function buildPrompt(question: string, tickers?: string[]): string {
  return tickers?.length ? `${question}\nTickers: ${tickers.join(", ")}` : question;
}

function makeResearchTool(
  modelMap: ModelMap,
  defaultModel: LanguageModel,
  writer: Writer,
  providerOptions: MaybeProviderOptions,
): Tool {
  return {
    description:
      "Delegate to the Research Analyst for: news articles, financial ratios, company research notes, investment thesis, geopolitical events, and world news affecting Vietnamese markets.",
    inputSchema: z.object({
      question: z.string().describe("Specific research question"),
      tickers: z.array(z.string()).optional().describe("Tickers to research"),
      model: modelSchema,
    }),
    execute: async function* ({ question, tickers, model }: DelegationInput) {
      const agent = createResearchAnalyst(resolveModel(modelMap, defaultModel, model), providerOptions);
      yield* runSubAgentStreaming(agent, writer, buildPrompt(question, tickers));
    },
    toModelOutput: ({ output }: { output: UIMessage }) => ({
      type: "text" as const,
      value: extractFinalText(output),
    }),
  };
}

function makeStrategyTool(
  modelMap: ModelMap,
  defaultModel: LanguageModel,
  writer: Writer,
  providerOptions: MaybeProviderOptions,
): Tool {
  return {
    description:
      "Delegate to the Strategy Advisor for: trade setup R:R calculation, position sizing, historical winning/losing patterns, applicable trading rules, similar historical market days.",
    inputSchema: z.object({
      question: z.string().describe("Specific strategy or trade setup question"),
      tickers: z.array(z.string()).optional().describe("Tickers involved in the setup"),
      model: modelSchema,
    }),
    execute: async function* ({ question, tickers, model }: DelegationInput) {
      const agent = createStrategyAdvisor(resolveModel(modelMap, defaultModel, model), providerOptions);
      yield* runSubAgentStreaming(agent, writer, buildPrompt(question, tickers));
    },
    toModelOutput: ({ output }: { output: UIMessage }) => ({
      type: "text" as const,
      value: extractFinalText(output),
    }),
  };
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function buildCoordinatorTools(
  modelMap: ModelMap,
  defaultModel: LanguageModel,
  writer: Writer,
  providerOptions?: ProviderOptions,
) {
  return {
    // Tool broker — direct access to any leaf tool + domain skills
    ...buildBrokerTools(writer),
    // Delegation tools — complex multi-tool synthesis via sub-agents
    ask_research_analyst: makeResearchTool(modelMap, defaultModel, writer, providerOptions),
    ask_strategy_advisor: makeStrategyTool(modelMap, defaultModel, writer, providerOptions),
  };
}
