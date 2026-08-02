/**
 * Shared types for sub-agent coordination.
 */

/** A tool result that should be surfaced as a rich data part to the client. */
export interface RenderDataItem {
  toolName: string
  input: unknown
  data: unknown
}
