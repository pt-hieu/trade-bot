/**
 * Sub-agent factory functions. Each creates a ToolLoopAgent with a focused toolset.
 * Agents are created per-request (cheap — no LLM call until .generate()).
 */
import { ToolLoopAgent } from 'ai'
import type { LanguageModel } from 'ai'

type JSONValue = null | string | number | boolean | JSONObject | JSONValue[]
type JSONObject = { [key: string]: JSONValue }
type ProviderOptions = Record<string, JSONObject>
import { marketTools } from '../tools/market'
import { researchTools } from '../tools/research'
import { strategyTools } from '../tools/strategy'

// Strategy Advisor needs get_technicals to look up current price before computing trade setups
const strategyToolsWithPrice = {
  ...strategyTools,
  get_technicals: marketTools.get_technicals,
}
import {
  buildResearchPrompt,
  buildStrategyPrompt,
} from './system-prompts'

export function createResearchAnalyst(model: LanguageModel, providerOptions?: ProviderOptions) {
  return new ToolLoopAgent({
    model,
    instructions: buildResearchPrompt(),
    tools: researchTools,
    providerOptions,
    experimental_telemetry: {
      isEnabled: true,
      functionId: 'swingy-research-analyst',
    },
  })
}

export function createStrategyAdvisor(model: LanguageModel, providerOptions?: ProviderOptions) {
  return new ToolLoopAgent({
    model,
    instructions: buildStrategyPrompt(),
    tools: strategyToolsWithPrice,
    providerOptions,
    experimental_telemetry: {
      isEnabled: true,
      functionId: 'swingy-strategy-advisor',
    },
  })
}
