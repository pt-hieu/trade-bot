"use client";

import { Bot } from "lucide-react";
import type { UIMessage } from "ai";
import { DataPartRenderer } from "../data-renderers";
import { AgentCard } from "../agent-execution";
import { MarkdownContent } from "../markdown-content";
import { parseSteps } from "../../../lib/chat/parse-steps";
import {
  BROKER_TOOLS,
  DELEGATION_LABELS,
  DELEGATION_TOOLS,
  type UIPart,
} from "./constants";
import { BrokerToolBubble, ThinkingBlock, ToolCallBubble } from "./components";

export function AssistantMessage({ message, showThinking }: { message: UIMessage; showThinking?: boolean }) {
  const steps = parseSteps(message.parts ?? []);

  return (
    <div className="flex flex-col gap-1.5">
      {steps.map((step, i) => {
        // Split tool parts: delegation → cards, broker → special rendering, rest → chips
        const delegationParts = step.toolParts.filter((p) => {
          const toolName = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
          return DELEGATION_TOOLS.has(toolName);
        });
        const brokerParts = step.toolParts.filter((p) => {
          const toolName = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
          return BROKER_TOOLS.has(toolName);
        });
        const regularToolParts = step.toolParts.filter((p) => {
          const toolName = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
          return !DELEGATION_TOOLS.has(toolName) && !BROKER_TOOLS.has(toolName);
        });

        return (
          <div key={i} className="flex flex-col gap-1.5">
            {/* Thinking — above everything, no avatar */}
            {showThinking !== false && step.reasoning.map((r, j) => (
              <ThinkingBlock key={j} text={r.text} state={r.state} />
            ))}
            {/* Text — before delegation so "I'll ask the analysts" appears first */}
            {step.textParts.length > 0 && (
              <div className="flex gap-2">
                <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center mt-0.5 bg-primary/10 border border-primary/20">
                  <Bot className="h-2.5 w-2.5 text-primary/60" />
                </div>
                <div className="flex-1 min-w-0 flex flex-col gap-2 pt-[0.1em]">
                  {step.textParts.map((t, j) => (
                    <div key={j} className="text-sm text-foreground/90">
                      <MarkdownContent text={t.text} />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Delegation tool calls — compact grid cards */}
            {delegationParts.length > 0 && (
              <div className="ml-7 grid grid-cols-1 @lg:grid-cols-3 gap-2">
                {delegationParts.map((p, j) => {
                  const toolName = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
                  const label = DELEGATION_LABELS[toolName] ?? toolName;
                  return (
                    <AgentCard
                      key={j}
                      part={p as Parameters<typeof AgentCard>[0]["part"]}
                      label={label}
                    />
                  );
                })}
              </div>
            )}
            {/* Broker tool calls — skill badges + direct call chips */}
            {brokerParts.length > 0 && <BrokerToolBubble parts={brokerParts as UIPart[]} />}
            {/* Regular tool calls — chip style */}
            {regularToolParts.length > 0 && <ToolCallBubble parts={regularToolParts as UIPart[]} />}
            {/* Data parts (charts, tables, etc.) */}
            {step.dataParts.map((d, j) => (
              <DataPartRenderer key={j} part={d as { type: string; data: unknown }} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
