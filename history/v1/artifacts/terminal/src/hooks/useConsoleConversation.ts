import { useCallback, useEffect, useState } from "react";

// A single line in the Console transcript: either an operator command or a
// Terminal reply (a conversational answer or a build summary).
export interface ConsoleMessage {
  role: "user" | "assistant";
  content: string;
  kind?: "answer" | "summary" | "notice";
}

// Versioned keys so a future schema change can be ignored cleanly rather than
// crashing on a stale shape. Keys are namespaced by the authenticated user id so
// a user's transcript is tied to their identity, not the anonymous browser —
// switching accounts (or logging out) never leaks the previous user's console.
const MESSAGES_PREFIX = "agentic-terminal.console.messages.v1";
const SESSION_PREFIX = "agentic-terminal.console.sessionId.v1";
// Cap the persisted transcript so it can't grow without bound.
const MAX_MESSAGES = 200;

function messagesKey(userId?: string): string {
  return userId ? `${MESSAGES_PREFIX}.${userId}` : MESSAGES_PREFIX;
}

function sessionKey(userId?: string): string {
  return userId ? `${SESSION_PREFIX}.${userId}` : SESSION_PREFIX;
}

function loadMessages(userId?: string): ConsoleMessage[] {
  try {
    const raw = localStorage.getItem(messagesKey(userId));
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

function loadSessionId(userId?: string): string | undefined {
  try {
    return localStorage.getItem(sessionKey(userId)) || undefined;
  } catch {
    return undefined;
  }
}

// Persists the Console conversation (transcript + the backend session id it
// belongs to) in localStorage so it survives a page reload. Reusing the stored
// session id lets follow-up questions reconnect to the same backend session and
// keep their context.
export function useConsoleConversation(userId?: string) {
  const [messages, setMessages] = useState<ConsoleMessage[]>(() => loadMessages(userId));
  const [sessionId, setSessionIdState] = useState<string | undefined>(() => loadSessionId(userId));

  // When the authenticated user changes, swap to that user's persisted console
  // so identities never share a transcript or backend session.
  useEffect(() => {
    setMessages(loadMessages(userId));
    setSessionIdState(loadSessionId(userId));
  }, [userId]);

  useEffect(() => {
    try {
      localStorage.setItem(
        messagesKey(userId),
        JSON.stringify(messages.slice(-MAX_MESSAGES)),
      );
    } catch {
      /* storage unavailable — degrade to in-memory only */
    }
  }, [messages, userId]);

  const setSessionId = useCallback((id: string | undefined) => {
    setSessionIdState(id);
    try {
      if (id) localStorage.setItem(sessionKey(userId), id);
      else localStorage.removeItem(sessionKey(userId));
    } catch {
      /* ignore */
    }
  }, [userId]);

  const addUserMessage = useCallback((content: string) => {
    setMessages((prev) => [...prev, { role: "user", content }]);
  }, []);

  const addAssistantMessage = useCallback(
    (content: string, kind: "answer" | "summary") => {
      setMessages((prev) => [...prev, { role: "assistant", content, kind }]);
    },
    [],
  );

  // A degraded/fallback notice — surfaced when the AI was slow or unavailable so
  // the user understands why the dashboard may look simpler.
  const addNoticeMessage = useCallback((content: string) => {
    setMessages((prev) => [...prev, { role: "assistant", content, kind: "notice" }]);
  }, []);

  // Wipe the transcript and the persisted session — used when the dashboard is
  // reset/cleared so the Console starts fresh too.
  const clear = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
    try {
      localStorage.removeItem(messagesKey(userId));
    } catch {
      /* ignore */
    }
  }, [setSessionId, userId]);

  return {
    messages,
    sessionId,
    setSessionId,
    addUserMessage,
    addAssistantMessage,
    addNoticeMessage,
    clear,
  };
}
