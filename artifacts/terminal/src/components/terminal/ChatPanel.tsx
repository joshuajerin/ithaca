import React, { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useGetSuggestions, useGetSkills, useGetWatchlist } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Send, ChevronRight, Activity, Command } from "lucide-react";

interface ChatPanelProps {
  sessionId?: string;
  onCommand: (cmd: string) => void;
  isProcessing: boolean;
  // The latest assistant reply (a build summary or a conversational answer),
  // carried with a monotonically increasing nonce so every reply renders — even
  // when its text repeats a previous one (no content-based dedup dropping it).
  reply?: { text: string; kind: 'answer' | 'summary'; nonce: number } | null;
  // Forwarded ref to the command input so power-user hotkeys (e.g. "/" or ⌘K)
  // can focus it from anywhere in the terminal.
  inputRef?: React.Ref<HTMLInputElement>;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  kind?: 'answer' | 'summary';
}

export function ChatPanel({ sessionId, onCommand, isProcessing, reply, inputRef }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastReplyNonce = useRef(0);

  const { data: suggestions } = useGetSuggestions();
  const { data: skills } = useGetSkills();
  const { data: watchlist } = useGetWatchlist();

  useEffect(() => {
    if (reply && reply.text && reply.nonce !== lastReplyNonce.current) {
      lastReplyNonce.current = reply.nonce;
      setMessages(prev => [...prev, { role: 'assistant', content: reply.text, kind: reply.kind }]);
    }
  }, [reply]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isProcessing]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;
    
    const cmd = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: 'user', content: cmd }]);
    onCommand(cmd);
  };

  const handleSuggestionClick = (prompt: string) => {
    setMessages(prev => [...prev, { role: 'user', content: prompt }]);
    onCommand(prompt);
  };

  return (
    <div className="flex flex-col h-full border-l border-border bg-black">
      <div className="px-5 pt-4 pb-3 border-b border-border">
        <span className="editorial-label text-[9px] text-muted-foreground">Command Input</span>
        <h2 className="font-serif text-xl leading-none mt-1.5 flex items-center gap-2">
          Console
        </h2>
      </div>

      <ScrollArea className="flex-1 px-5 py-5" ref={scrollRef}>
        <div className="space-y-7">
          {/* Welcome / Suggestions — fades out cleanly once a conversation begins */}
          <AnimatePresence mode="wait">
            {messages.length === 0 && (
              <motion.div
                key="welcome"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8, filter: "blur(2px)" }}
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                className="space-y-7"
              >
                <div className="border-b border-border pb-5">
                  <div className="editorial-label text-[9px] text-muted-foreground mb-2 flex items-center gap-1.5">
                    <Activity className="w-3 h-3" strokeWidth={1.5} />
                    System Ready
                  </div>
                  <p className="font-serif text-base leading-snug text-gray-200">Awaiting commands. Enter a natural-language request to compose a dashboard.</p>
                </div>

                {suggestions?.prompts && (
                  <div className="space-y-3">
                    <div className="editorial-label text-[9px] text-muted-foreground">Example queries</div>
                    <div className="flex flex-col">
                      {suggestions.prompts.map((prompt, i) => (
                        <button
                          key={i}
                          onClick={() => handleSuggestionClick(prompt)}
                          className="text-left py-3 border-t border-border first:border-t-0 hover:text-white text-gray-300 transition-colors duration-200 flex items-start gap-2 group"
                        >
                          <ChevronRight className="w-3.5 h-3.5 mt-1 shrink-0 text-muted-foreground group-hover:text-white transition-colors" strokeWidth={1.5} />
                          <span className="font-serif text-base leading-snug">{prompt}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Chat History — each message fades/slides in */}
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10, filter: "blur(2px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className={`flex flex-col gap-1.5 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div className="editorial-label text-[8.5px] text-muted-foreground">
                {msg.role === 'user' ? 'Operator' : msg.kind === 'answer' ? 'Terminal · Answer' : 'Terminal'}
              </div>
              <div className={`px-3.5 py-2.5 max-w-[90%] font-serif text-base leading-snug ${
                msg.role === 'user' 
                  ? 'bg-white text-black' 
                  : 'border-l border-border text-gray-100'
              }`}>
                {msg.content}
              </div>
            </motion.div>
          ))}

          <AnimatePresence>
            {isProcessing && (
              <motion.div
                key="processing"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="flex flex-col gap-1.5 items-start"
              >
                <div className="editorial-label text-[8.5px] text-muted-foreground">Terminal</div>
                <div className="px-3.5 py-2.5 border-l border-border text-muted-foreground flex items-center gap-3 font-serif text-base italic">
                  <span className="flex gap-0.5">
                    <span className="animate-bounce">.</span>
                    <span className="animate-bounce delay-75">.</span>
                    <span className="animate-bounce delay-150">.</span>
                  </span>
                  Processing command
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </ScrollArea>

      <div className="px-5 py-4 border-t border-border shrink-0">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <Command className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter command…"
            disabled={isProcessing}
            className="w-full bg-transparent text-white px-3 py-2 font-serif text-base placeholder:text-muted-foreground placeholder:italic focus:outline-none transition-colors disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isProcessing}
            className="text-white disabled:opacity-30 hover:text-gray-300 shrink-0"
          >
            <Send className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </form>
      </div>
    </div>
  );
}
