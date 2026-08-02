/**
 * Parses a flat UIMessage parts array into discrete agentic steps.
 *
 * Handles two modes:
 * - Live streaming: step-start parts are present as explicit step boundaries
 * - DB-loaded: step-start filtered out; reasoning-after-tool acts as implicit boundary
 */

export interface MessageStep {
  reasoning: Array<{ text: string; state?: "streaming" | "done" }>;
  toolParts: Array<{ type: string; [key: string]: unknown }>;
  dataParts: Array<{ type: string; [key: string]: unknown }>;
  textParts: Array<{ text: string }>;
}

type AnyPart = { type: string; [key: string]: unknown };

export function parseSteps(parts: AnyPart[]): MessageStep[] {
  const steps: MessageStep[] = [];
  let current: MessageStep = { reasoning: [], toolParts: [], dataParts: [], textParts: [] };
  let seenToolInCurrent = false;

  const flush = () => {
    const hasContent =
      current.reasoning.length || current.toolParts.length ||
      current.dataParts.length || current.textParts.length;
    if (hasContent) {
      steps.push(current);
      current = { reasoning: [], toolParts: [], dataParts: [], textParts: [] };
      seenToolInCurrent = false;
    }
  };

  for (const part of parts) {
    if (part.type === "step-start") {
      flush();
    } else if (part.type === "reasoning") {
      // Implicit boundary: reasoning after a tool = new step (handles DB-loaded messages)
      if (seenToolInCurrent) flush();
      const text = (part.text as string) ?? "";
      if (text.trim()) current.reasoning.push({ text, state: part.state as "streaming" | "done" | undefined });
    } else if (part.type.startsWith("tool-")) {
      seenToolInCurrent = true;
      current.toolParts.push(part);
    } else if (part.type.startsWith("data-")) {
      current.dataParts.push(part);
    } else if (part.type === "text") {
      const text = (part.text as string) ?? "";
      if (text.trim()) current.textParts.push({ text });
    }
  }

  flush();
  return steps;
}
