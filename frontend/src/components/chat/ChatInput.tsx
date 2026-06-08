"use client";

import { useRef, useState, KeyboardEvent } from "react";
import { Send, Square, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What are the main findings of this document?",
  "Summarize the key concepts",
  "Create 5 quiz questions about this topic",
  "Explain the methodology used",
];

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  placeholder = "Ask anything about your documents…",
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || isStreaming) return;
    onSend(trimmed);
    setValue("");
    setShowSuggestions(false);
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const handleSuggestion = (text: string) => {
    setValue(text);
    setShowSuggestions(false);
    textareaRef.current?.focus();
  };

  return (
    <div className="relative flex flex-col gap-2">
      {/* Suggestions */}
      {showSuggestions && (
        <div className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-border bg-card p-2 shadow-lg animate-fade-in z-10">
          <p className="px-2 pb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Suggestions
          </p>
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              onClick={() => handleSuggestion(s)}
              className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input container */}
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
        <button
          onClick={() => setShowSuggestions(!showSuggestions)}
          className="mb-0.5 flex-shrink-0 rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Show suggestions"
        >
          <Lightbulb className="h-4 w-4" />
        </button>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={placeholder}
          className="flex-1 resize-none bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50 leading-relaxed"
          style={{ maxHeight: "200px" }}
        />

        {isStreaming ? (
          <button
            onClick={onStop}
            className="mb-0.5 flex-shrink-0 rounded-lg bg-red-500/10 p-2 text-red-500 hover:bg-red-500/20 transition-colors"
            title="Stop generation"
          >
            <Square className="h-4 w-4 fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!value.trim() || disabled}
            className={cn(
              "mb-0.5 flex-shrink-0 rounded-lg p-2 transition-colors",
              value.trim() && !disabled
                ? "bg-primary text-white hover:bg-primary/90"
                : "text-muted-foreground cursor-not-allowed"
            )}
            title="Send message (Enter)"
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>

      <p className="text-center text-xs text-muted-foreground/50">
        Press{" "}
        <kbd className="rounded border border-border px-1 py-0.5 font-mono text-xs">
          Enter
        </kbd>{" "}
        to send ·{" "}
        <kbd className="rounded border border-border px-1 py-0.5 font-mono text-xs">
          Shift+Enter
        </kbd>{" "}
        for new line
      </p>
    </div>
  );
}
