"use client";

import { useRef, useState } from "react";
import { Check, Pencil, RotateCcw } from "lucide-react";
import type { UIMessage } from "ai";

export function UserMessage({
  message,
  onReplay,
  onEdit,
  isStreaming,
}: {
  message: UIMessage;
  onReplay?: () => void;
  onEdit?: (newText: string) => void;
  isStreaming?: boolean;
}) {
  const textPart = message.parts?.find((p) => p.type === "text") as { text: string } | undefined;
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  if (!textPart?.text?.trim()) return null;

  const handleStartEdit = () => {
    setEditText(textPart.text);
    setIsEditing(true);
    // Focus after render
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const handleSubmitEdit = () => {
    const trimmed = editText.trim();
    if (trimmed && trimmed !== textPart.text) {
      onEdit?.(trimmed);
    }
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmitEdit();
    }
    if (e.key === "Escape") {
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <div className="flex gap-2 flex-row-reverse">
        <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center mt-0.5 bg-muted/50">
          <span className="text-[9px] font-mono text-muted-foreground">You</span>
        </div>
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          <textarea
            ref={textareaRef}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            className="bg-muted/40 border border-primary/30 rounded-lg px-3 py-2 font-mono text-xs text-foreground/80 resize-none focus:outline-none focus:border-primary/50 w-full"
            data-test-id="chat-edit-input"
          />
          <div className="flex items-center gap-1 justify-end">
            <button
              onClick={() => setIsEditing(false)}
              className="h-5 px-1.5 rounded text-[9px] font-mono text-muted-foreground/50 hover:text-foreground/70 hover:bg-muted/30 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmitEdit}
              className="h-5 px-1.5 rounded text-[9px] font-mono text-primary/70 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer flex items-center gap-1"
              data-test-id="chat-edit-submit"
            >
              <Check className="h-2.5 w-2.5" />
              Save
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative flex gap-2 flex-row-reverse">
      <div className="flex-shrink-0 h-5 w-5 rounded flex items-center justify-center mt-0.5 bg-muted/50">
        <span className="text-[9px] font-mono text-muted-foreground">You</span>
      </div>
      <div className="flex items-end">
        <div className="bg-muted/40 border border-border/30 rounded-lg px-3 py-2 font-mono text-xs text-foreground/80 inline-block">
          {textPart.text}
        </div>
      </div>
      {/* Hover actions */}
      {!isStreaming && (onReplay || onEdit) && (
        <div className="absolute -top-5 right-7 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          {onReplay && (
            <button
              onClick={onReplay}
              className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground/30 hover:text-foreground/60 hover:bg-muted/30 transition-colors cursor-pointer"
              title="Replay from here"
              data-test-id="chat-replay"
            >
              <RotateCcw className="h-2.5 w-2.5" />
            </button>
          )}
          {onEdit && (
            <button
              onClick={handleStartEdit}
              className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground/30 hover:text-foreground/60 hover:bg-muted/30 transition-colors cursor-pointer"
              title="Edit message"
              data-test-id="chat-edit"
            >
              <Pencil className="h-2.5 w-2.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
