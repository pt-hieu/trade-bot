import { useState, useCallback, useRef, useMemo, useEffect } from 'react'
import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport } from 'ai'
import { Clock, Plus, X, Maximize2, Minimize2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '../../lib/utils'
import { api } from '../../lib/api'
import { ChatBubble } from './chat-bubble'
import { MessageList } from './message-list'
import { ChatInput } from './chat-input'
import { ChatSettings } from './chat-settings'
import { ConversationList } from './conversation-list'
import { DEFAULT_CHAT_MODEL, isValidChatModel, modelSupportsThinking, type ChatModelId, type ThinkingEffort } from '../../lib/chat/models'
import { convertDbMessagesToUIMessages } from '../../lib/chat/convert-messages'
import type { ConversationDetail } from '../../hooks/use-chat-history'
import { type SwingyUIMessage, type UsageData, dataPartSchemas } from '../../lib/chat/data-parts'

export function ChatPanel() {
  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [model, setModel] = useState<ChatModelId>(DEFAULT_CHAT_MODEL)
  const [thinking, setThinking] = useState<ThinkingEffort>('off')
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)

  const queryClient = useQueryClient()

  // Use refs so the transport closure captures latest values without recreation
  const modelRef = useRef(model)
  const thinkingRef = useRef(thinking)
  const conversationIdRef = useRef(conversationId)
  const setConversationIdRef = useRef(setConversationId)
  modelRef.current = model
  thinkingRef.current = thinking
  conversationIdRef.current = conversationId
  setConversationIdRef.current = setConversationId

  // Create transport once — body and fetch are closures over refs
  const transport = useMemo(
    () =>
      new DefaultChatTransport<SwingyUIMessage>({
        api: '/api/chat',
        body: () => ({ model: modelRef.current, conversationId: conversationIdRef.current, thinking: thinkingRef.current }),
        fetch: async (input, init) => {
          const response = await fetch(input as RequestInfo, init)
          const newId = response.headers.get('X-Conversation-Id')
          if (newId) setConversationIdRef.current(newId)
          return response
        },
      }),
    [],
  )

  const { messages, sendMessage, status, stop, setMessages } = useChat<SwingyUIMessage>({
    transport,
    dataPartSchemas,
  })

  const isStreaming = status === 'streaming' || status === 'submitted'

  // Extract latest usage data from the most recent assistant message
  const usage = useMemo<UsageData | null>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      if (msg.role !== 'assistant') continue
      const part = msg.parts?.findLast((p) => p.type === 'data-usage')
      if (part && 'data' in part && part.data) return part.data as UsageData
    }
    return null
  }, [messages])

  // Invalidate conversation list when a new conversation is created
  useEffect(() => {
    if (conversationId) {
      queryClient.invalidateQueries({ queryKey: ['chat', 'conversations'] })
    }
  }, [conversationId, queryClient])

  const handleSend = useCallback(
    (text: string) => {
      sendMessage({ text })
    },
    [sendMessage],
  )

  const handleNewConversation = useCallback(() => {
    setConversationId(undefined)
    setMessages([])
    setThinking('off')
    setView('chat')
  }, [setMessages])

  const handleSelectConversation = useCallback(
    async (id: string) => {
      if (isStreaming) stop()
      try {
        const data = await api.get<ConversationDetail>(`/chat/conversations/${id}`)
        setMessages(convertDbMessagesToUIMessages(data.messages as any) as SwingyUIMessage[])
        setConversationId(id)
        setModel(
          isValidChatModel(data.conversation.model_id as string)
            ? (data.conversation.model_id as ChatModelId)
            : DEFAULT_CHAT_MODEL,
        )
        setThinking((data.conversation.thinking_effort as ThinkingEffort) ?? 'off')
        setView('chat')
      } catch (err) {
        console.error('[chat] Failed to load conversation:', err)
      }
    },
    [isStreaming, stop, setMessages],
  )

  const handleModelChange = useCallback(
    (newModel: ChatModelId) => {
      setModel(newModel)
      // Auto-reset thinking when switching to a model that doesn't support it
      if (!modelSupportsThinking(newModel)) {
        setThinking('off')
      }
    },
    [],
  )

  const handleReplay = useCallback(
    (messageIndex: number) => {
      if (isStreaming) stop()
      const targetMsg = messages[messageIndex]
      const textPart = targetMsg?.parts?.find((p) => p.type === 'text') as { text: string } | undefined
      if (!textPart?.text) return
      setMessages(messages.slice(0, messageIndex))
      setConversationId(undefined)
      sendMessage({ text: textPart.text })
    },
    [isStreaming, stop, messages, setMessages, sendMessage],
  )

  const handleEdit = useCallback(
    (messageIndex: number, newText: string) => {
      if (isStreaming) stop()
      setMessages(messages.slice(0, messageIndex))
      setConversationId(undefined)
      sendMessage({ text: newText })
    },
    [isStreaming, stop, messages, setMessages, sendMessage],
  )

  return (
    <>
      <ChatBubble
        isOpen={isOpen}
        onClick={() => setIsOpen((v) => !v)}
        hasMessages={messages.length > 0}
      />

      {/* Backdrop — visible only when expanded */}
      {isOpen && isExpanded && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-200"
          onClick={() => setIsExpanded(false)}
          data-test-id="chat-backdrop"
        />
      )}

      {/* Panel */}
      <div
        className={cn(
          'fixed z-50 flex flex-col',
          'bg-background border border-border/50 rounded-xl',
          'shadow-2xl shadow-black/30',
          'transition-all duration-200 ease-out',
          '@container',
          isExpanded
            ? 'bottom-[10vh] right-[10vw] w-[80vw] h-[80vh]'
            : 'bottom-20 right-6 w-[420px] h-[620px]',
          isOpen
            ? 'opacity-100 translate-y-0 pointer-events-auto'
            : 'opacity-0 translate-y-3 pointer-events-none',
        )}
        data-test-id="chat-panel"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/30 flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-semibold text-foreground/80 tracking-wide">
              SWINGY
            </span>
            <span className="text-[10px] font-mono text-muted-foreground/40">
              {view === 'history' ? 'history' : 'chat'}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setView((v) => (v === 'history' ? 'chat' : 'history'))}
              className={cn(
                'h-6 w-6 rounded flex items-center justify-center transition-colors cursor-pointer',
                view === 'history'
                  ? 'text-primary/70 bg-primary/10'
                  : 'text-muted-foreground/50 hover:text-foreground hover:bg-muted/30',
              )}
              title="Conversation history"
              data-test-id="chat-history"
            >
              <Clock className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleNewConversation}
              className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
              title="New conversation"
              data-test-id="chat-new"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setIsExpanded((v) => !v)}
              className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
              title={isExpanded ? 'Collapse' : 'Expand'}
              data-test-id="chat-expand"
            >
              {isExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-muted/30 transition-colors cursor-pointer"
              title="Close"
              data-test-id="chat-close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Messages or History */}
        {view === 'history' ? (
          <ConversationList
            activeConversationId={conversationId}
            onSelect={handleSelectConversation}
            onBack={() => setView('chat')}
            onReset={handleNewConversation}
          />
        ) : (
          <MessageList messages={messages} isStreaming={isStreaming} showThinking={thinking !== 'off'} onSend={handleSend} onSelectConversation={handleSelectConversation} onReplay={handleReplay} onEdit={handleEdit} />
        )}

        {/* Settings + Input — hidden when browsing history */}
        {view === 'chat' && (
          <>
            <ChatSettings
              model={model}
              onModelChange={handleModelChange}
              thinking={thinking}
              onThinkingChange={setThinking}
              supportsThinking={modelSupportsThinking(model)}
              disabled={messages.length > 0}
              usage={usage}
            />
            <ChatInput
              onSend={handleSend}
              onStop={stop}
              isStreaming={isStreaming}
            />
          </>
        )}
      </div>
    </>
  )
}
