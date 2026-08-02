import { useRef, useCallback, type KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'
import { cn } from '../../lib/utils'

interface ChatInputProps {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  disabled?: boolean
}

export function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const value = textareaRef.current?.value.trim()
    if (!value || isStreaming || disabled) return
    onSend(value)
    if (textareaRef.current) {
      textareaRef.current.value = ''
      textareaRef.current.style.height = 'auto'
    }
  }, [onSend, isStreaming, disabled])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleInput = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 96)}px` // max ~4 lines
  }, [])

  return (
    <div className="flex items-end gap-2 px-3 py-2 border-t border-border/30">
      <textarea
        ref={textareaRef}
        rows={1}
        placeholder="Ask about portfolio, trades, market…"
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={isStreaming || disabled}
        className={cn(
          'flex-1 resize-none bg-transparent text-sm font-mono',
          'placeholder:text-muted-foreground/40',
          'focus:outline-none disabled:opacity-50',
          'max-h-24 leading-relaxed py-1',
        )}
        data-test-id="chat-input"
      />
      {isStreaming ? (
        <button
          onClick={onStop}
          className="flex-shrink-0 h-7 w-7 rounded flex items-center justify-center border border-border/50 hover:border-rose-500/50 hover:bg-rose-500/10 transition-colors cursor-pointer"
          data-test-id="chat-stop"
          aria-label="Stop"
        >
          <Square className="h-3 w-3 text-rose-400" />
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={disabled}
          className="flex-shrink-0 h-7 w-7 rounded flex items-center justify-center border border-border/50 hover:border-primary/50 hover:bg-primary/10 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
          data-test-id="chat-send"
          aria-label="Send"
        >
          <Send className="h-3 w-3 text-muted-foreground" />
        </button>
      )}
    </div>
  )
}
