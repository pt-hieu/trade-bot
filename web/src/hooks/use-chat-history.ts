import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getConversations, deleteConversation, getConversation } from '../server/fns/chat'

export function useConversations() {
  return useQuery({
    queryKey: ['chat', 'conversations'],
    queryFn: () => getConversations(),
    staleTime: 30_000,
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteConversation({ data: { id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', 'conversations'] })
    },
  })
}

export interface ConversationDetail {
  conversation: Record<string, unknown>
  messages: Record<string, unknown>[]
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ['chat', 'conversation', id],
    queryFn: () => getConversation({ data: { id: id! } }),
    enabled: !!id,
    staleTime: 60_000,
  })
}
