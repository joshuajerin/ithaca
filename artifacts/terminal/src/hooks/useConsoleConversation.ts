import { useCallback, useEffect, useState } from "react";

// A single line in the Console transcript: either an operator command or a
// Terminal reply (a conversational answer or a build summary).
export interface ConsoleMessage {
  role: "user" | "assistant";
  content: string;
  kind?: "answer" | "summary";
}

// Versioned keys so a future schema change can be ignored cleanly rather than
// crashing on a stale shape.
const MESSAGES_KEY = "agentic-terminal.console.messages.v1";
const SESSION_KEY = "agentic-terminal.console.sessionId.v1";
// Cap the persisted transcript so it can't grow without bound.
const MAX_MESSAGES = 200;

function loadMessages(): ConsoleMessage[] {
  try {
    const raw = localStorage.getItem(MESSAGES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is ConsoleMessage =>
        !!m &&
        (m.role === "user" || m.role === "assistant") &&
        typeof m.content === "string",
    );
  } catch {
    return [];
  }
}

function loadSessionId(): string | undefined {
  try {
    return localStorage.getItem(SESSION_KEY) || undefined;
  } catch {
    return undefined;
  }
}

// Persists the Console conversation (transcript + the backend session id it
// belongs to) in localStorage so it survives a page reload. Reusing the stored
// session id lets follow-up questions reconnect to the same backend session and
// keep their context.
export function useConsoleConversation() {
  const [messages, setMessages] = useState<ConsoleMessage[]>(loadMessages);
  const [sessionId, setSessionIdState] = useState<string | undefined>(loadSessionId);

  useEffect(() => {
    try {
      localStorage.setItem(
        MESSAGES_KEY,
        JSON.stringify(messages.slice(-MAX_MESSAGES)),
      );
    } catch {
      /* storage unavailable — degrade to in-memory only */
    }
  }, [messages]);

  const setSessionId = useCallback((id: string | undefined) => {
    setSessionIdState(id);
    try {
      if (id) localStorage.setItem(SESSION_KEY, id);
      else localStorage.removeItem(SESSION_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const addUserMessage = useCallback((content: string) => {
    setMessages((prev) => [...prev, { role: "user", content }]);
  }, []);

  const addAssistantMessage = useCallback(
    (content: string, kind: "answer" | "summary") => {
      setMessages((prev) => [...prev, { role: "assistant", content, kind }]);
    },
    [],
  );

  // Wipe the transcript and the persisted session — used when the dashboard is
  // reset/cleared so the Console starts fresh too.
  const clear = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
    try {
      localStorage.removeItem(MESSAGES_KEY);
    } catch {
      /* ignore */
    }
  }, [setSessionId]);

  return {
    messages,
    sessionId,
    setSessionId,
    addUserMessage,
    addAssistantMessage,
    clear,
  };
}
