"use client";

import { useEffect, useRef } from "react";
import { Bot } from "lucide-react";
import type { UIMessage } from "ai";
import { useConversations } from "../../../hooks/use-chat-history";
import { formatRelativeTime } from "../../../lib/date";
import { AssistantMessage } from "./assistant-message";
import { UserMessage } from "./user-message";

interface MessageListProps {
  messages: UIMessage[];
  isStreaming?: boolean;
  showThinking?: boolean;
  onSend?: (text: string) => void;
  onSelectConversation?: (id: string) => void;
  onReplay?: (messageIndex: number) => void;
  onEdit?: (messageIndex: number, newText: string) => void;
}

export function MessageList({
  messages,
  isStreaming,
  showThinking,
  onSend,
  onSelectConversation,
  onReplay,
  onEdit,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const { data: conversations } = useConversations();
  const hasHistory = conversations && conversations.length > 0;

  if (messages.length === 0) {
    return (
      <div
        className="flex-1 flex flex-col justify-center px-5 py-6"
        data-test-id="chat-empty"
        style={{
          backgroundImage:
            "radial-gradient(ellipse 80% 40% at 50% 0%, hsl(var(--primary)/0.05) 0%, transparent 100%)",
        }}
      >
        <div className="mb-5">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/40" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary/70" />
            </span>
            <span className="text-[10px] font-mono tracking-[0.22em] text-muted-foreground/40 uppercase">
              SWINGY
            </span>
            <span className="text-[10px] font-mono text-primary/30 animate-pulse">_</span>
          </div>
          <p className="text-[11px] font-mono text-muted-foreground/25 pl-3.5 tracking-wide">
            portfolio · trades · market
          </p>
        </div>
        <div className="flex items-center gap-2 mb-4">
          <div className="flex-1 border-t border-border/15" />
          <span className="text-[9px] font-mono text-muted-foreground/20 uppercase tracking-[0.2em]">
            {hasHistory ? "sessions" : "queries"}
          </span>
          <div className="flex-1 border-t border-border/15" />
        </div>
        {hasHistory ? (
          <div className="space-y-px">
            {conversations.slice(0, 5).map((conv, i) => (
              <button
                key={conv.id}
                onClick={() => onSelectConversation?.(conv.id)}
                className="w-full flex items-baseline gap-2.5 px-2 py-2 text-left group transition-colors duration-150 hover:bg-primary/[0.05] cursor-pointer"
              >
                <span className="text-[10px] font-mono text-primary/25 group-hover:text-primary/50 transition-colors flex-shrink-0 tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-[11px] font-mono text-foreground/40 group-hover:text-foreground/75 transition-colors truncate leading-snug">
                  {conv.title}
                </span>
                <span className="text-[10px] font-mono text-muted-foreground/20 group-hover:text-muted-foreground/40 transition-colors flex-shrink-0 ml-auto tabular-nums">
                  {formatRelativeTime(conv.updated_at)}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-px">
            {["What are my open trades?", "Show my portfolio P&L", "What is the market regime today?"].map((s) => (
              <button
                key={s}
                onClick={() => onSend?.(s)}
                className="w-full flex items-center gap-2.5 px-2 py-2 text-left group transition-colors duration-150 hover:bg-primary/[0.05] cursor-pointer"
              >
                <span className="text-[11px] font-mono text-primary/30 group-hover:text-primary/60 transition-colors flex-shrink-0">›</span>
                <span className="text-[11px] font-mono text-foreground/40 group-hover:text-foreground/75 transition-colors">{s}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4" data-test-id="message-list">
      {messages.map((message, index) =>
        message.role === "user" ? (
          <UserMessage
            key={message.id}
            message={message}
            isStreaming={isStreaming}
            onReplay={onReplay ? () => onReplay(index) : undefined}
            onEdit={onEdit ? (newText: string) => onEdit(index, newText) : undefined}
          />
        ) : (
          <AssistantMessage key={message.id} message={message} showThinking={showThinking} />
        ),
      )}
      {isStreaming && (
        <div className="flex gap-2">
          <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center mt-0.5 bg-primary/10 border border-primary/20">
            <Bot className="h-2.5 w-2.5 text-primary/60" />
          </div>
          <div className="flex items-center gap-1 pt-1">
            <span className="h-1 w-1 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.3s]" />
            <span className="h-1 w-1 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.15s]" />
            <span className="h-1 w-1 rounded-full bg-primary/40 animate-bounce" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
