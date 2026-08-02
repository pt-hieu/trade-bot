import { createFileRoute } from '@tanstack/react-router'
import {
  streamText,
  convertToModelMessages,
  stepCountIs,
  createUIMessageStream,
  createUIMessageStreamResponse,
  wrapLanguageModel,
  extractReasoningMiddleware,
} from 'ai'
import { createOpenAI } from '@ai-sdk/openai'
import type { UIMessage } from 'ai'
import { getSql } from '../../server/db'
import {
  isValidChatModel,
  DEFAULT_CHAT_MODEL,
  modelSupportsThinking,
  getContextWindow,
  SUB_AGENT_MODELS,
  type ThinkingEffort,
} from '../../lib/chat/models'
import { type SwingyUIMessage } from '../../lib/chat/data-parts'
import { buildCoordinatorTools } from '../../lib/chat/agents/coordinator'
import { buildCoordinatorPrompt } from '../../lib/chat/agents/system-prompts'

function getOpenRouter() {
  return createOpenAI({
    apiKey: process.env.OPENROUTER_API_KEY!,
    baseURL: 'https://openrouter.ai/api/v1',
  })
}

export const Route = createFileRoute('/api/chat')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        try {
          const openrouter = getOpenRouter()
          const { messages, model, conversationId, thinking } =
            (await request.json()) as {
              messages: UIMessage[]
              model: string
              conversationId?: string
              thinking?: ThinkingEffort
            }

          const selectedModel = isValidChatModel(model)
            ? model
            : DEFAULT_CHAT_MODEL
          const sql = getSql()

          const thinkingEffort: ThinkingEffort = thinking ?? 'off'
          const useThinking =
            thinkingEffort !== 'off' && modelSupportsThinking(selectedModel)
          const baseModel = openrouter(selectedModel)
          const chatModel = useThinking
            ? wrapLanguageModel({
                model: baseModel,
                middleware: extractReasoningMiddleware({ tagName: 'think' }),
              })
            : baseModel

          let convId = conversationId
          if (!convId) {
            const firstUserMsg = messages.find(
              (m: UIMessage) => m.role === 'user'
            )
            const textPart = firstUserMsg?.parts?.find(
              (p: { type: string }) => p.type === 'text'
            )
            const title =
              (textPart && 'text' in textPart
                ? (textPart as { text: string }).text
                : '') || 'New conversation'

            const rows = await sql`
              INSERT INTO chat_conversations (title, model_id, thinking_effort)
              VALUES (${title.slice(0, 80)}, ${selectedModel}, ${thinkingEffort})
              RETURNING id
            `
            convId = rows[0].id as string
          } else {
            await sql`
              UPDATE chat_conversations SET updated_at = NOW(), model_id = ${selectedModel}, thinking_effort = ${thinkingEffort}
              WHERE id = ${convId}
            `
          }

          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'user') {
            await sql`
              INSERT INTO chat_messages (conversation_id, role, content)
              VALUES (${convId}, 'user', ${JSON.stringify(lastMsg.parts ?? [])})
            `
          }

          const finalConvId = convId
          const systemPrompt = buildCoordinatorPrompt(thinkingEffort)

          const subAgentModelMap = {
            heavy: openrouter(SUB_AGENT_MODELS.heavy),
            light: openrouter(SUB_AGENT_MODELS.light),
          }

          const stream = createUIMessageStream<SwingyUIMessage>({
            execute: async ({ writer }) => {
              const coordinatorTools = buildCoordinatorTools(
                subAgentModelMap,
                baseModel,
                writer,
              )

              const result = streamText({
                model: chatModel,
                system: systemPrompt,
                messages: await convertToModelMessages(messages),
                tools: coordinatorTools,
                stopWhen: stepCountIs(8),
                experimental_telemetry: {
                  isEnabled: true,
                  functionId: 'swingy-coordinator',
                  metadata: {
                    conversationId: finalConvId,
                    model: selectedModel,
                  },
                },
              })
              writer.merge(result.toUIMessageStream())

              const totalUsage = await result.totalUsage
              writer.write({
                type: 'data-usage',
                data: {
                  inputTokens: totalUsage.inputTokens ?? 0,
                  outputTokens: totalUsage.outputTokens ?? 0,
                  contextWindow: getContextWindow(selectedModel),
                },
              } as Parameters<typeof writer.write>[0])
            },

            onFinish: async ({ responseMessage }) => {
              try {
                const persistParts = responseMessage.parts.filter(
                  (p: { type: string }) => p.type !== 'step-start'
                )
                if (persistParts.length === 0) return

                const content = JSON.stringify(persistParts).replace(
                  /\u0000/g,
                  ''
                )
                await sql`
                  INSERT INTO chat_messages (conversation_id, role, content)
                  VALUES (${finalConvId}, 'assistant', ${content})
                `
                await sql`
                  UPDATE chat_conversations SET updated_at = NOW() WHERE id = ${finalConvId}
                `
              } catch (err) {
                console.error(
                  '[chat] Failed to persist assistant message:',
                  err
                )
              }
            },
          })

          const headers = new Headers()
          if (!conversationId) headers.set('X-Conversation-Id', finalConvId)

          return createUIMessageStreamResponse({ stream, headers })
        } catch (error) {
          console.error('[chat] POST error:', error)
          return new Response(
            JSON.stringify({ error: 'Chat request failed' }),
            { status: 500, headers: { 'Content-Type': 'application/json' } }
          )
        }
      },
    },
  },
})
