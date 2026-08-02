/**
 * Tool broker — 4 meta-tools that let the coordinator discover, call,
 * and load domain expertise for any leaf tool on demand.
 */
import { z } from 'zod'
import { asSchema } from 'ai'
import type { Tool, UIMessageStreamWriter } from 'ai'
import type { SwingyUIMessage } from '../data-parts'
import { TOOL_DATA_MAP } from '../data-parts'
import { SKILL_NAMES, SKILL_REGISTRY } from '../skills'
import { portfolioTools } from './portfolio'
import { marketTools } from './market'
import { watchlistTools } from './watchlist'
import { researchTools } from './research'
import { strategyTools } from './strategy'
import { pipelineTools } from './pipeline'

type Writer = UIMessageStreamWriter<SwingyUIMessage>

// ─── Tool Registry ───────────────────────────────────────────────────────────

const DOMAIN_MAP: Record<string, Record<string, Tool>> = {
  portfolio: portfolioTools,
  market: marketTools,
  watchlist: watchlistTools,
  research: researchTools,
  strategy: strategyTools,
  pipeline: pipelineTools,
}

const TOOL_REGISTRY: Record<string, { tool: Tool; domain: string }> = {}
for (const [domain, tools] of Object.entries(DOMAIN_MAP)) {
  for (const [name, tool] of Object.entries(tools)) {
    TOOL_REGISTRY[name] = { tool, domain }
  }
}

const DOMAIN_NAMES = Object.keys(DOMAIN_MAP) as [string, ...string[]]

// ─── list_tools ──────────────────────────────────────────────────────────────

const list_tools: Tool = {
  description:
    'List available data tools by domain. Returns tool names and descriptions. Use to discover what tools exist before calling them.',
  inputSchema: z.object({
    category: z
      .enum(DOMAIN_NAMES)
      .optional()
      .describe(
        'Filter by domain: portfolio, market, watchlist, research, strategy, pipeline. Omit to list all.',
      ),
  }),
  execute: async (input: { category?: string }) => {
    const domains = input.category ? [input.category] : DOMAIN_NAMES
    const result: Record<string, Array<{ name: string; description: string }>> = {}
    for (const domain of domains) {
      const tools = DOMAIN_MAP[domain]
      if (!tools) continue
      result[domain] = Object.entries(tools).map(([name, tool]) => ({
        name,
        description: (tool as Tool).description ?? '',
      }))
    }
    return JSON.stringify(result)
  },
}

// ─── get_tool_schema ─────────────────────────────────────────────────────────

const get_tool_schema: Tool = {
  description:
    'Get the input schema for a specific tool. Returns JSON Schema describing required and optional parameters.',
  inputSchema: z.object({
    name: z.string().describe('Tool name from list_tools results, e.g. "get_portfolio"'),
  }),
  execute: async (input: { name: string }) => {
    const entry = TOOL_REGISTRY[input.name]
    if (!entry) {
      return JSON.stringify({ error: `Unknown tool: ${input.name}` })
    }
    const schema = asSchema(entry.tool.inputSchema)
    return JSON.stringify({
      name: input.name,
      domain: entry.domain,
      schema: schema.jsonSchema,
    })
  },
}

// ─── call_tool ───────────────────────────────────────────────────────────────

function makeCallTool(writer: Writer): Tool {
  return {
    description:
      'Execute a data tool by name with provided arguments. Returns the tool output as JSON. For renderable tools (charts, tables), pass render:true in args.',
    inputSchema: z.object({
      name: z.string().describe('Tool name, e.g. "get_portfolio", "get_cash"'),
      args: z
        .record(z.unknown())
        .optional()
        .describe('Tool input arguments as key-value pairs'),
    }),
    execute: async (input: { name: string; args?: Record<string, unknown> }) => {
      const entry = TOOL_REGISTRY[input.name]
      if (!entry) {
        return JSON.stringify({ error: `Unknown tool: ${input.name}` })
      }
      const tool = entry.tool
      if (!tool.execute) {
        return JSON.stringify({ error: `Tool ${input.name} has no execute function` })
      }

      const args = input.args ?? {}
      let result: unknown
      try {
        result = await (tool.execute as (input: unknown) => Promise<unknown>)(args)
      } catch (e) {
        return JSON.stringify({ error: `Tool ${input.name} failed: ${String(e)}` })
      }

      // Push render data part if render:true and tool has a mapping
      const inp = args as { render?: boolean }
      if (inp.render) {
        const mapping = TOOL_DATA_MAP[input.name]
        if (mapping) {
          try {
            let data = result
            if (typeof data === 'string') {
              try {
                data = JSON.parse(data)
              } catch {
                /* keep as string */
              }
            }
            ;(writer.write as (chunk: unknown) => void)({
              type: `data-${mapping.partType}`,
              data: mapping.transform(data, args),
            })
          } catch (e) {
            console.error(`[broker] render data error for ${input.name}:`, e)
          }
        }
      }

      return typeof result === 'string' ? result : JSON.stringify(result)
    },
  }
}

// ─── load_skill ─────────────────────────────────────────────────────────────

const load_skill: Tool = {
  description:
    'Load domain expertise for a topic. Returns analysis guidelines to help you interpret data from call_tool. Use before multi-step analysis in a domain.',
  inputSchema: z.object({
    skill: z
      .enum(SKILL_NAMES)
      .describe('Domain to load expertise for: portfolio, market, watchlist, pipeline'),
  }),
  execute: async (input: { skill: string }) => {
    const content = SKILL_REGISTRY[input.skill as keyof typeof SKILL_REGISTRY]
    if (!content) {
      return JSON.stringify({ error: `Unknown skill: ${input.skill}` })
    }
    return content
  },
}

// ─── Export ───────────────────────────────────────────────────────────────────

export function buildBrokerTools(writer: Writer) {
  return {
    list_tools,
    get_tool_schema,
    call_tool: makeCallTool(writer),
    load_skill,
  }
}
