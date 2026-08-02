"use client";

import { useState } from "react";
import { Bot, Brain, BookOpen, ChevronRight, Loader2, X, Zap } from "lucide-react";
import { cn } from "../../../lib/utils";
import { MarkdownContent } from "../markdown-content";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../../ui/collapsible";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTrigger,
} from "../../ui/dialog";
import { TOOL_LABELS } from "../../../lib/chat/tool-labels";
import {
  getToolState,
  SKILL_COLORS,
  SKILL_DEFAULT_COLOR,
  type UIPart,
} from "./constants";

export function ThinkingBlock({ text, state }: { text: string; state?: "streaming" | "done" }) {
  const isStreaming = state === "streaming";
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 group cursor-pointer py-0.5 w-full">
        {/* Same h-5 w-5 slot as the Bot avatar — chevron/brain centers inside it */}
        <div className="flex-shrink-0 h-5 w-5 flex items-center justify-center">
          {isStreaming ? (
            <Brain className="h-3 w-3 text-amber-500/50 animate-pulse" />
          ) : (
            <ChevronRight
              className={cn(
                "h-3 w-3 text-amber-500/40 transition-transform duration-150",
                isOpen && "rotate-90",
              )}
            />
          )}
        </div>
        <span className="text-[10px] font-mono text-amber-500/50 tracking-wider">
          {isStreaming ? "Thinking" : "Thought"}
        </span>
        {isStreaming && (
          <span className="flex items-center gap-0.5 ml-0.5">
            <span className="h-1 w-1 rounded-full bg-amber-500/40 animate-bounce [animation-delay:-0.3s]" />
            <span className="h-1 w-1 rounded-full bg-amber-500/40 animate-bounce [animation-delay:-0.15s]" />
            <span className="h-1 w-1 rounded-full bg-amber-500/40 animate-bounce" />
          </span>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        {/* ml-7 = h-5 (20px) + gap-2 (8px) — aligns with "Thought" text */}
        <p className="text-[11px] font-mono text-muted-foreground/40 leading-relaxed whitespace-pre-wrap mt-1 mb-2 ml-7">
          {text.trim()}
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ToolResultModal({ part, label }: { part: UIPart; label: string }) {
  const raw = (part as { output?: unknown }).output;

  let content: React.ReactNode;
  if (raw == null) {
    content = <span className="text-muted-foreground/30">No output</span>;
  } else if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as { text?: string; renderData?: unknown[] };
      if (parsed.text) {
        content = (
          <div className="text-sm text-foreground/80">
            <MarkdownContent text={parsed.text} />
          </div>
        );
      } else {
        content = (
          <pre className="text-[10px] font-mono text-foreground/50 leading-relaxed whitespace-pre-wrap">
            {JSON.stringify(parsed, null, 2)}
          </pre>
        );
      }
    } catch {
      content = (
        <p className="text-[11px] font-mono text-foreground/60 leading-relaxed whitespace-pre-wrap">
          {raw}
        </p>
      );
    }
  } else {
    content = (
      <pre className="text-[10px] font-mono text-foreground/50 leading-relaxed whitespace-pre-wrap">
        {JSON.stringify(raw, null, 2)}
      </pre>
    );
  }

  return (
    <DialogContent
      showCloseButton={false}
      className="p-0 gap-0 max-w-md border-border/20 bg-background/95 backdrop-blur-sm shadow-2xl"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/15">
        <span className="text-[10px] font-mono tracking-[0.18em] text-muted-foreground/50 uppercase">
          {label}
        </span>
        <DialogClose className="text-muted-foreground/30 hover:text-muted-foreground/60 transition-colors">
          <X className="h-3.5 w-3.5" />
        </DialogClose>
      </div>
      {/* Body */}
      <div className="px-4 py-3 max-h-[60vh] overflow-y-auto">
        {content}
      </div>
    </DialogContent>
  );
}

export function ToolCallBubble({ parts }: { parts: UIPart[] }) {
  if (parts.length === 0) return null;
  const allDone = parts.every((p) => getToolState(p) === "output-available");
  const hasError = parts.some((p) => getToolState(p) === "output-error");

  return (
    <div className="flex gap-2 items-center">
      <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center bg-primary/10 border border-primary/20">
        <Bot className="h-2.5 w-2.5 text-primary/60" />
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[9px] font-mono text-muted-foreground/30 tracking-wider">
          {hasError ? "failed" : allDone ? "called" : "calling"}
        </span>
        {parts.map((part, i) => {
          const toolName = part.type.startsWith("tool-") ? part.type.slice(5) : part.type;
          const label = TOOL_LABELS[toolName] ?? toolName;
          const state = getToolState(part);
          const isDone = state === "output-available";
          const isError = state === "output-error";

          const chip = (
            <span
              className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors",
                isDone && "border-emerald-500/20 text-emerald-400/70 bg-emerald-500/5 hover:bg-emerald-500/10 cursor-pointer",
                isError && "border-rose-500/20 text-rose-400/70 bg-rose-500/5",
                !isDone && !isError && "border-border/40 text-muted-foreground/60 bg-muted/20",
              )}
            >
              {!isDone && !isError && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
              {isDone && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />}
              {isError && <span className="h-1.5 w-1.5 rounded-full bg-rose-400/70" />}
              {isDone ? label : isError ? `${label} failed` : `${label}…`}
            </span>
          );

          if (!isDone) return <span key={i}>{chip}</span>;

          return (
            <Dialog key={i}>
              <DialogTrigger asChild>{chip}</DialogTrigger>
              <ToolResultModal part={part} label={label} />
            </Dialog>
          );
        })}
      </div>
    </div>
  );
}

export function SkillBadge({ part }: { part: UIPart }) {
  const input = (part as { input?: { skill?: string } }).input;
  const skill = input?.skill ?? "unknown";
  const state = getToolState(part);
  const isDone = state === "output-available";
  const isError = state === "output-error";
  const colors = SKILL_COLORS[skill] ?? SKILL_DEFAULT_COLOR;

  return (
    <div className="flex gap-2 items-center">
      <div className={cn(
        "flex-shrink-0 h-5 w-5 rounded flex items-center justify-center border",
        isDone ? `${colors.bg} ${colors.border}` : "bg-muted/10 border-border/20",
      )}>
        <BookOpen className={cn(
          "h-2.5 w-2.5",
          isDone ? colors.text : isError ? "text-rose-400/60" : "text-muted-foreground/40 animate-pulse",
        )} />
      </div>
      <span className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono border transition-all duration-300",
        isDone && `${colors.border} ${colors.text} ${colors.bg}`,
        isError && "border-rose-500/20 text-rose-400/60 bg-rose-500/5",
        !isDone && !isError && "border-border/30 text-muted-foreground/50 bg-muted/10",
      )}>
        {!isDone && !isError && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
        {isDone && <span className={cn("h-1.5 w-1.5 rounded-full flex-shrink-0", colors.dot)} />}
        {isError && <span className="h-1.5 w-1.5 rounded-full bg-rose-400/60 flex-shrink-0" />}
        {isDone ? `${skill} expertise loaded` : isError ? `${skill} failed` : `loading ${skill}…`}
      </span>
    </div>
  );
}

export function BrokerToolBubble({ parts }: { parts: UIPart[] }) {
  if (parts.length === 0) return null;

  // Separate broker tool types
  const skillParts = parts.filter((p) => {
    const name = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
    return name === "load_skill";
  });
  const callParts = parts.filter((p) => {
    const name = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
    return name === "call_tool";
  });
  const discoveryParts = parts.filter((p) => {
    const name = p.type.startsWith("tool-") ? p.type.slice(5) : p.type;
    return name === "list_tools" || name === "get_tool_schema";
  });

  return (
    <div className="flex flex-col gap-1.5">
      {/* Skill badges — each on its own line for prominence */}
      {skillParts.map((part, i) => (
        <SkillBadge key={`skill-${i}`} part={part} />
      ))}

      {/* Direct tool calls + discovery — chip row */}
      {(callParts.length > 0 || discoveryParts.length > 0) && (
        <div className="flex gap-2 items-center">
          <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center bg-primary/10 border border-primary/20">
            <Zap className="h-2.5 w-2.5 text-primary/60" />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Discovery tools — collapsed subtle indicator */}
            {discoveryParts.length > 0 && (() => {
              const allDone = discoveryParts.every((p) => getToolState(p) === "output-available");
              return (
                <span className={cn(
                  "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono border",
                  allDone
                    ? "border-border/15 text-muted-foreground/30 bg-transparent"
                    : "border-border/25 text-muted-foreground/40 bg-muted/10",
                )}>
                  {!allDone && <Loader2 className="h-2 w-2 animate-spin" />}
                  {allDone ? "discovered" : "discovering…"}
                </span>
              );
            })()}

            {/* Direct call_tool calls — show inner tool name */}
            {callParts.map((part, i) => {
              const input = (part as { input?: { name?: string } }).input;
              const innerToolName = input?.name ?? "unknown";
              const innerLabel = TOOL_LABELS[innerToolName] ?? innerToolName;
              const state = getToolState(part);
              const isDone = state === "output-available";
              const isError = state === "output-error";

              const chip = (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors",
                    isDone && "border-emerald-500/20 text-emerald-400/70 bg-emerald-500/5 hover:bg-emerald-500/10 cursor-pointer",
                    isError && "border-rose-500/20 text-rose-400/70 bg-rose-500/5",
                    !isDone && !isError && "border-border/40 text-muted-foreground/60 bg-muted/20",
                  )}
                >
                  {!isDone && !isError && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
                  {isDone && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />}
                  {isError && <span className="h-1.5 w-1.5 rounded-full bg-rose-400/70" />}
                  {isDone ? innerLabel : isError ? `${innerLabel} failed` : `${innerLabel}…`}
                </span>
              );

              if (!isDone) return <span key={`call-${i}`}>{chip}</span>;

              return (
                <Dialog key={`call-${i}`}>
                  <DialogTrigger asChild>{chip}</DialogTrigger>
                  <ToolResultModal part={part} label={`Direct: ${innerLabel}`} />
                </Dialog>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
