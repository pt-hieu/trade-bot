import { describe, it, expect } from "vitest";
import {
  CHAT_MODELS,
  isValidChatModel,
  getChatModelLabel,
  modelSupportsThinking,
  DEFAULT_CHAT_MODEL,
} from "./models";

describe("modelSupportsThinking", () => {
  it("returns true for Kimi K2.5", () => {
    expect(modelSupportsThinking("moonshotai/Kimi-K2.5")).toBe(true);
  });

  it("returns true for Qwen 3.5", () => {
    expect(modelSupportsThinking("Qwen/Qwen3.5-397B-A17B")).toBe(true);
  });

  it("returns true for MiniMax M2.7", () => {
    expect(modelSupportsThinking("minimax/minimax-m2.7")).toBe(true);
  });

  it("returns false for unknown model id", () => {
    expect(modelSupportsThinking("unknown/model")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(modelSupportsThinking("")).toBe(false);
  });
});

describe("isValidChatModel", () => {
  it("returns true for every model in CHAT_MODELS", () => {
    for (const m of CHAT_MODELS) {
      expect(isValidChatModel(m.id)).toBe(true);
    }
  });

  it("returns false for unknown model", () => {
    expect(isValidChatModel("gpt-4o")).toBe(false);
  });
});

describe("getChatModelLabel", () => {
  it("returns label for known model", () => {
    expect(getChatModelLabel("moonshotai/Kimi-K2.5")).toBe("Kimi K2.5");
  });

  it("falls back to last path segment for unknown model", () => {
    expect(getChatModelLabel("org/some-model")).toBe("some-model");
  });

  it("returns full id when no slash", () => {
    expect(getChatModelLabel("plainmodel")).toBe("plainmodel");
  });
});

describe("DEFAULT_CHAT_MODEL", () => {
  it("is a valid chat model", () => {
    expect(isValidChatModel(DEFAULT_CHAT_MODEL)).toBe(true);
  });

  it("supports thinking (default model should have thinking capability)", () => {
    expect(modelSupportsThinking(DEFAULT_CHAT_MODEL)).toBe(true);
  });
});
