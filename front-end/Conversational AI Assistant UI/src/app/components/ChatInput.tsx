import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  isStreaming: boolean;
  onStop: () => void;
}

export function ChatInput({ onSend, isStreaming, onStop }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full">
      <div
        className="flex flex-col rounded-2xl border transition-shadow focus-within:shadow-sm"
        style={{
          background: "var(--card)",
          borderColor: "var(--border)",
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your documents…"
          rows={1}
          className="w-full resize-none px-4 pt-4 pb-2 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground leading-relaxed"
          style={{ fontFamily: "var(--font-sans)", maxHeight: "160px", scrollbarWidth: "none" }}
        />
        <div className="flex items-center justify-between px-4 pb-2">
          <div />
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {value.length > 0 && `${value.length}`}
            </span>
            {isStreaming ? (
              <button
                onClick={onStop}
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-colors"
                style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
                title="Stop"
              >
                <Square size={13} fill="currentColor" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!value.trim()}
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-all"
                style={{
                  background: value.trim() ? "var(--primary)" : "var(--muted)",
                  color: value.trim() ? "var(--primary-foreground)" : "var(--muted-foreground)",
                  cursor: value.trim() ? "pointer" : "default",
                }}
                title="Send (Enter)"
              >
                <Send size={13} />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="text-center text-xs text-muted-foreground mt-2">
        AI can make mistakes. Verify important information from source documents.
      </p>
    </div>
  );
}
