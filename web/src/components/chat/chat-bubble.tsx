import { MessageSquare } from 'lucide-react'
import { cn } from '../../lib/utils'

interface ChatBubbleProps {
  isOpen: boolean
  onClick: () => void
  hasMessages?: boolean
}

export function ChatBubble({ isOpen, onClick, hasMessages = false }: ChatBubbleProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'fixed bottom-6 right-6 z-50',
        'h-12 w-12 rounded-full',
        'flex items-center justify-center',
        'border border-border/50',
        'bg-background shadow-lg shadow-black/20',
        'transition-all duration-200',
        'hover:border-border hover:scale-105 cursor-pointer',
        isOpen && 'border-primary/40 bg-primary/5',
        !isOpen && !hasMessages && 'animate-pulse-slow',
      )}
      data-test-id="chat-bubble"
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      <MessageSquare
        className={cn(
          'h-4 w-4 transition-colors',
          isOpen ? 'text-primary' : 'text-muted-foreground',
        )}
      />
      {hasMessages && !isOpen && (
        <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-primary" />
      )}
    </button>
  )
}
