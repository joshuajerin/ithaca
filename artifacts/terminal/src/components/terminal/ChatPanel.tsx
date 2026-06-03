import React, { useState, useRef, useEffect } from "react";
import { useGetSuggestions, useGetSkills, useGetWatchlist } from "@workspace/api-client-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Terminal as TerminalIcon, Send, Clock, ChevronRight, Activity, Command } from "lucide-react";

interface ChatPanelProps {
  sessionId?: string;
  onCommand: (cmd: string) => void;
  isProcessing: boolean;
  lastSummary?: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export function ChatPanel({ sessionId, onCommand, isProcessing, lastSummary }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: suggestions } = useGetSuggestions();
  const { data: skills } = useGetSkills();
  const { data: watchlist } = useGetWatchlist();

  useEffect(() => {
    if (lastSummary) {
      setMessages(prev => {
        // Only add if it's different from the last assistant message
        const lastMsg = prev[prev.length - 1];
        if (lastMsg?.role === 'assistant' && lastMsg.content === lastSummary) {
          return prev;
        }
        return [...prev, { role: 'assistant', content: lastSummary }];
      });
    }
  }, [lastSummary]);

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
    <div className="flex flex-col h-full border-l border-border bg-[#050505]">
      <div className="p-4 border-b border-border bg-black">
        <h2 className="text-xs uppercase tracking-widest text-muted-foreground font-bold flex items-center gap-2">
          <TerminalIcon className="w-4 h-4" />
          Command Input
        </h2>
      </div>

      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="space-y-6">
          {/* Welcome / Suggestions */}
          {messages.length === 0 && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <div className="border border-border p-4 bg-black">
                <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Activity className="w-3 h-3" />
                  System Ready
                </div>
                <p className="text-sm">Awaiting commands. Enter a natural language request to compose a dashboard.</p>
              </div>

              {suggestions?.prompts && (
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wider">Example queries:</div>
                  <div className="flex flex-col gap-2">
                    {suggestions.prompts.map((prompt, i) => (
                      <button
                        key={i}
                        onClick={() => handleSuggestionClick(prompt)}
                        className="text-left p-3 text-sm border border-border bg-black hover:bg-white hover:text-black transition-colors duration-200 flex items-start gap-2"
                      >
                        <ChevronRight className="w-4 h-4 mt-0.5 shrink-0" />
                        <span className="leading-tight">{prompt}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Chat History */}
          {messages.map((msg, i) => (
            <div key={i} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {msg.role === 'user' ? 'USR' : 'SYS'}
              </div>
              <div className={`p-3 text-sm max-w-[90%] border ${
                msg.role === 'user' 
                  ? 'border-white bg-white text-black' 
                  : 'border-border bg-black text-white'
              }`}>
                {msg.content}
              </div>
            </div>
          ))}

          {isProcessing && (
            <div className="flex flex-col gap-1 items-start">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">SYS</div>
              <div className="p-3 text-sm border border-border bg-black text-muted-foreground flex items-center gap-3">
                <span className="flex gap-1">
                  <span className="animate-bounce">.</span>
                  <span className="animate-bounce delay-75">.</span>
                  <span className="animate-bounce delay-150">.</span>
                </span>
                PROCESSING COMMAND
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="p-4 bg-black border-t border-border shrink-0">
        <form onSubmit={handleSubmit} className="relative">
          <div className="absolute left-3 top-3.5 text-muted-foreground">
            <Command className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="ENTER COMMAND..."
            disabled={isProcessing}
            className="w-full bg-black border border-border text-white px-10 py-3 text-sm font-mono focus:outline-none focus:border-white transition-colors disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isProcessing}
            className="absolute right-3 top-3 text-white disabled:opacity-50 hover:text-gray-300"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
