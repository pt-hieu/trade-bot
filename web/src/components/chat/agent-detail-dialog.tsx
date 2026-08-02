"use client";

import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  ChevronRight,
  Eye,
  FileSearch,
  Loader2,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import { cn } from "../../lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import {
  DialogClose,
  DialogContent,
} from "../ui/dialog";
import { MarkdownContent } from "./markdown-content";
import { TOOL_LABELS } from "../../lib/chat/tool-labels";
import type { UIMessage } from "ai";

interface DelegationToolPart {
  type: string
  state?: string
  preliminary?: boolean
  input?: { question?: string; tickers?: string[] }
  output?: UIMessage
}

const AGENT_ICONS: Record<string, React.ElementType> = {
  ask_portfolio_analyst: Briefcase,
  ask_market_analyst: TrendingUp,
  ask_watchlist_scout: Eye,
  ask_research_analyst: FileSearch,
  ask_strategy_advisor: Target,
  ask_pipeline_reporter: Activity,
};

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

export interface AgentDetailDialogProps {
  part: DelegationToolPart;
  label: string;
  agentKey: string;
}

export function AgentDetailDialog({ part, label, agentKey }: AgentDetailDialogProps) {
  const [promptOpen, setPromptOpen] = useState(false);

  const hasOutput = part.state === "output-available";
  const isStreaming = hasOutput && part.preliminary === true;
  const isError = part.state === "output-error";
  const subMessage = hasOutput ? part.output : null;

  const subParts = subMessage?.parts ?? [];
  const prompt = part.input?.question ?? "";
  const tickers = part.input?.tickers;
  const Icon = AGENT_ICONS[agentKey] ?? Activity;

  return (
    <DialogContent
      showCloseButton={false}
      className="p-0 gap-0 max-w-lg border-border/20 bg-background/98 backdrop-blur-sm shadow-2xl"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/15 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Icon
            className={cn(
              "h-3.5 w-3.5 flex-shrink-0",
              isError && "text-rose-400/60",
              isStreaming && "text-primary/60",
              hasOutput && !isStreaming && "text-emerald-400/60",
              !hasOutput && !isError && "text-muted-foreground/40",
            )}
          />
          <span
            className={cn(
              "text-[11px] font-mono font-medium",
              isError && "text-rose-400/60",
              isStreaming && "text-primary/60",
              hasOutput && !isStreaming && "text-emerald-400/60",
              !hasOutput && !isError && "text-muted-foreground/40",
            )}
          >
            {label}
          </span>
          {tickers && tickers.length > 0 && (
            <span className="text-[9px] font-mono text-muted-foreground/30">
              {tickers.join(", ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isError ? (
            <AlertTriangle className="h-3 w-3 text-rose-400/50" />
          ) : isStreaming ? (
            <Loader2 className="h-3 w-3 animate-spin text-primary/50" />
          ) : hasOutput ? (
            <CheckCircle2 className="h-3 w-3 text-emerald-400/50" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/30" />
          )}
          <DialogClose className="text-muted-foreground/30 hover:text-muted-foreground/60 transition-colors cursor-pointer">
            <X className="h-3.5 w-3.5" />
          </DialogClose>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 max-h-[65vh] overflow-y-auto flex flex-col gap-2">
        {prompt && (
          <Collapsible open={promptOpen} onOpenChange={setPromptOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 cursor-pointer group">
              <ChevronRight
                className={cn(
                  "h-2.5 w-2.5 text-muted-foreground/25 transition-transform duration-150",
                  promptOpen && "rotate-90",
                )}
              />
              <span className="text-[9px] font-mono text-muted-foreground/25 group-hover:text-muted-foreground/40 transition-colors">
                prompt
              </span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <p className="ml-[14px] mt-0.5 text-[10px] font-mono text-muted-foreground/30 leading-relaxed whitespace-pre-wrap">
                {prompt}
              </p>
            </CollapsibleContent>
          </Collapsible>
        )}

        {subParts.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            {subParts.map((p, i) => {
              if (p.type === "text") {
                const text = (p as { type: "text"; text: string }).text;
                if (!text?.trim()) return null;
                return (
                  <div key={i} className="text-sm text-foreground/85">
                    <MarkdownContent text={text} />
                  </div>
                );
              }
              if (p.type.startsWith("tool-")) {
                const tp = p as { type: string; state?: string };
                const toolName = tp.type.slice(5);
                return (
                  <div key={i}>
                    <SubAgentToolChip toolName={toolName} state={tp.state} />
                  </div>
                );
              }
              return null;
            })}
          </div>
        ) : isError ? (
          <p className="text-[10px] font-mono text-rose-400/50">
            Agent failed — check logs
          </p>
        ) : (
          <p className="text-[10px] font-mono text-muted-foreground/30 animate-pulse">
            Working...
          </p>
        )}
      </div>
    </DialogContent>
  );
}
