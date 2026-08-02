"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Feather,
  FileSearch,
  Flame,
  Loader2,
  Target,
} from "lucide-react";
import { cn } from "../../lib/utils";
import {
  Dialog,
  DialogTrigger,
} from "../ui/dialog";
import { AgentDetailDialog } from "./agent-detail-dialog";
import { TOOL_LABELS } from "../../lib/chat/tool-labels";
import type { UIMessage } from "ai";

// ─── Types ────────────────────────────────────────────────────────────────────

interface DelegationToolPart {
  type: string
  state?: string
  preliminary?: boolean
  input?: { question?: string; tickers?: string[]; model?: 'heavy' | 'light' }
  output?: UIMessage
}

export interface AgentCardProps {
  part: DelegationToolPart
  label: string
}

// ─── Agent icon registry ───────────────────────────────────────────────────

const AGENT_ICONS: Record<string, React.ElementType> = {
  ask_research_analyst: FileSearch,
  ask_strategy_advisor: Target,
};

// ─── Sub-agent tool chip ───────────────────────────────────────────────────

function SubAgentToolChip({ toolName, state }: { toolName: string; state?: string }) {
  const label = TOOL_LABELS[toolName] ?? toolName;
  const isDone = state === "output-available";
  const isError = state === "output-error";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border",
        isDone && "border-emerald-500/20 text-emerald-400/60 bg-emerald-500/5",
        isError && "border-rose-500/20 text-rose-400/60 bg-rose-500/5",
        !isDone && !isError && "border-border/30 text-muted-foreground/50 bg-muted/10",
      )}
    >
      {!isDone && !isError && <Loader2 className="h-2 w-2 animate-spin" />}
      {isDone && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/60 flex-shrink-0" />}
      {isError && <span className="h-1.5 w-1.5 rounded-full bg-rose-400/60 flex-shrink-0" />}
      {label}
    </span>
  );
}

// ─── AgentCard ─────────────────────────────────────────────────────────────

export function AgentCard({ part, label }: AgentCardProps) {
  const agentKey = part.type.startsWith("tool-") ? part.type.slice(5) : part.type;
  const Icon = AGENT_ICONS[agentKey] ?? Activity;

  const hasOutput = part.state === "output-available";
  const isStreaming = hasOutput && part.preliminary === true;
  const isError = part.state === "output-error";
  const isPending = !hasOutput && !isError;

  const subMessage = hasOutput ? part.output : null;
  const subParts = subMessage?.parts ?? [];
  const textParts = subParts.filter(
    (p): p is { type: "text"; text: string } => p.type === "text",
  );
  const toolParts = subParts.filter((p) => p.type.startsWith("tool-")) as Array<{
    type: string;
    state?: string;
  }>;

  const tickers = part.input?.tickers;
  const previewText = textParts.map((t) => t.text).join(" ");

  return (
    <Dialog>
      <DialogTrigger asChild>
        <div
          className={cn(
            "rounded-lg border p-2.5 flex flex-col gap-1.5 cursor-pointer transition-all duration-150",
            "hover:bg-muted/10",
            isError && "border-rose-500/20 bg-rose-500/[0.03]",
            isStreaming && "border-primary/20 bg-primary/[0.03] animate-pulse",
            hasOutput && !isStreaming && "border-emerald-500/15 bg-emerald-500/[0.02]",
            isPending && "border-border/20 bg-muted/[0.03]",
          )}
        >
          {/* Header row */}
          <div className="flex items-center gap-1.5">
            {isError ? (
              <AlertTriangle className="h-3 w-3 text-rose-400/60 flex-shrink-0" />
            ) : isStreaming ? (
              <Loader2 className="h-3 w-3 animate-spin text-primary/50 flex-shrink-0" />
            ) : hasOutput ? (
              <CheckCircle2 className="h-3 w-3 text-emerald-400/50 flex-shrink-0" />
            ) : (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/30 flex-shrink-0" />
            )}
            <Icon
              className={cn(
                "h-3 w-3 flex-shrink-0",
                isError && "text-rose-400/50",
                isStreaming && "text-primary/50",
                hasOutput && !isStreaming && "text-emerald-400/50",
                isPending && "text-muted-foreground/30",
              )}
            />
            <span
              className={cn(
                "text-[10px] font-mono font-medium flex-1 truncate",
                isError && "text-rose-400/60",
                isStreaming && "text-primary/60",
                hasOutput && !isStreaming && "text-emerald-400/60",
                isPending && "text-muted-foreground/35",
              )}
            >
              {label}
            </span>
            {tickers && tickers.length > 0 && (
              <span className="text-[8px] font-mono text-muted-foreground/20 flex-shrink-0">
                {tickers.join(", ")}
              </span>
            )}
            {part.input?.model === "heavy" && (
              <Flame className="h-2.5 w-2.5 text-amber-400/40 flex-shrink-0" />
            )}
            {part.input?.model === "light" && (
              <Feather className="h-2.5 w-2.5 text-sky-400/40 flex-shrink-0" />
            )}
          </div>

          {/* Tool chips */}
          {toolParts.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {toolParts.map((tp, i) => {
                const toolName = tp.type.startsWith("tool-") ? tp.type.slice(5) : tp.type;
                return <SubAgentToolChip key={i} toolName={toolName} state={tp.state} />;
              })}
            </div>
          )}

          {/* Text preview */}
          {previewText ? (
            <p className="text-[10px] font-mono text-foreground/50 leading-relaxed line-clamp-3">
              {previewText}
            </p>
          ) : isPending ? (
            <p className="text-[9px] font-mono text-muted-foreground/25 animate-pulse">
              Working...
            </p>
          ) : isError ? (
            <p className="text-[9px] font-mono text-rose-400/40">
              Agent failed
            </p>
          ) : null}
        </div>
      </DialogTrigger>

      <AgentDetailDialog part={part} label={label} agentKey={agentKey} />
    </Dialog>
  );
}
