import { useState } from 'react'
import { ArrowLeft, MessageSquare, Trash2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Skeleton } from '../ui/skeleton'
import { ConfirmDialog } from '../ui/confirm-dialog'
import { useConversations, useDeleteConversation } from '../../hooks/use-chat-history'
import { getChatModelLabel } from '../../lib/chat/models'
import { formatRelativeTime } from '../../lib/date'

interface ConversationListProps {
  activeConversationId: string | undefined
  onSelect: (id: string) => void
  onBack: () => void
  onReset: () => void
}

export function ConversationList({ activeConversationId, onSelect, onBack, onReset }: ConversationListProps) {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const { data: conversations, isLoading } = useConversations()
  const deleteConversation = useDeleteConversation()

  function handleDeleteConfirm() {
    if (!deleteTarget) return
    const wasActive = deleteTarget === activeConversationId
    deleteConversation.mutate(deleteTarget, {
      onSuccess: () => {
        setDeleteTarget(null)
        if (wasActive) onReset()
      },
    })
  }

  return (
    <div className="flex-1 flex flex-col min-h-0" data-test-id="conversation-list">
      {/* List header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/20 flex-shrink-0">
        <button
          onClick={onBack}
          className="h-5 w-5 flex items-center justify-center text-muted-foreground/50 hover:text-foreground transition-colors cursor-pointer"
          title="Back to chat"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <span className="text-[10px] font-mono text-muted-foreground/50 uppercase tracking-wide">History</span>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="px-3 py-2 space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1.5 py-2 px-2">
                <Skeleton className="h-3.5 w-3/4" />
                <Skeleton className="h-2.5 w-1/3" />
              </div>
            ))}
          </div>
        )}

        {!isLoading && (!conversations || conversations.length === 0) && (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center px-6">
            <div className="h-8 w-8 rounded-full border border-border/30 flex items-center justify-center bg-muted/10">
              <MessageSquare className="h-3.5 w-3.5 text-muted-foreground/30" />
            </div>
            <p className="text-xs font-mono text-muted-foreground/50">No conversations yet</p>
            <p className="text-[10px] text-muted-foreground/30">Start chatting to build your history</p>
          </div>
        )}

        {!isLoading && conversations && conversations.length > 0 && (
          <div className="py-1">
            {conversations.map((conv) => {
              const isActive = conv.id === activeConversationId
              return (
                <div
                  key={conv.id}
                  className={cn(
                    'group relative flex items-start gap-2 px-3 py-2.5 cursor-pointer transition-colors',
                    'hover:bg-muted/20',
                    isActive && 'border-l-2 border-primary bg-muted/10 pl-[10px]',
                    !isActive && 'border-l-2 border-transparent',
                  )}
                  onClick={() => onSelect(conv.id)}
                  data-test-id={`conversation-item-${conv.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <p className={cn(
                      'text-xs font-mono truncate leading-tight',
                      isActive ? 'text-foreground/90' : 'text-foreground/70',
                    )}>
                      {conv.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] font-mono text-muted-foreground/40">
                        {getChatModelLabel(conv.model_id)}
                      </span>
                      <span className="text-[10px] text-muted-foreground/30">
                        {formatRelativeTime(conv.updated_at)}
                      </span>
                    </div>
                  </div>

                  {/* Delete button — visible on hover */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeleteTarget(conv.id)
                    }}
                    className={cn(
                      'flex-shrink-0 h-5 w-5 flex items-center justify-center rounded',
                      'text-muted-foreground/0 group-hover:text-muted-foreground/40',
                      'hover:!text-rose-400/70 hover:bg-rose-500/10 transition-colors cursor-pointer',
                    )}
                    title="Delete conversation"
                    data-test-id={`delete-conversation-${conv.id}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete conversation?"
        description="This will permanently delete this conversation and all its messages."
        confirmText="Delete"
        variant="destructive"
        onConfirm={handleDeleteConfirm}
        isPending={deleteConversation.isPending}
      />
    </div>
  )
}
