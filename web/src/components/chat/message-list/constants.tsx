import type { UIMessage } from "ai";

export type UIPart = NonNullable<UIMessage["parts"]>[number];

export function getToolState(part: UIPart): string {
  return (part as { state?: string }).state ?? "input-available";
}

// Delegation tools are rendered as full inline agent cards, not chips
export const DELEGATION_TOOLS = new Set([
  "ask_research_analyst",
  "ask_strategy_advisor",
]);

export const DELEGATION_LABELS: Record<string, string> = {
  ask_research_analyst: "Research Analyst",
  ask_strategy_advisor: "Strategy Advisor",
};

// Broker meta-tools get special rendering
export const BROKER_TOOLS = new Set(["list_tools", "get_tool_schema", "call_tool", "load_skill"]);

// ─── Skill domain colors ──────────────────────────────────────────────────────

export const SKILL_COLORS: Record<string, { border: string; text: string; bg: string; dot: string }> = {
  portfolio: {
    border: "border-emerald-500/25",
    text: "text-emerald-400/80",
    bg: "bg-emerald-500/[0.06]",
    dot: "bg-emerald-400/60",
  },
  market: {
    border: "border-sky-500/25",
    text: "text-sky-400/80",
    bg: "bg-sky-500/[0.06]",
    dot: "bg-sky-400/60",
  },
  watchlist: {
    border: "border-amber-500/25",
    text: "text-amber-400/80",
    bg: "bg-amber-500/[0.06]",
    dot: "bg-amber-400/60",
  },
  pipeline: {
    border: "border-violet-500/25",
    text: "text-violet-400/80",
    bg: "bg-violet-500/[0.06]",
    dot: "bg-violet-400/60",
  },
};

export const SKILL_DEFAULT_COLOR = {
  border: "border-border/30",
  text: "text-muted-foreground/60",
  bg: "bg-muted/10",
  dot: "bg-muted-foreground/40",
};
