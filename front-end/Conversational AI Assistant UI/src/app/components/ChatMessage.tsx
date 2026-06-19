import { useState } from "react";
import { Copy, ThumbsUp, ThumbsDown, RotateCcw, ExternalLink, ChevronDown, ChevronUp, AlertCircle, Brain } from "lucide-react";

export interface Citation {
  id: number;
  title: string;
  source: string;
  excerpt: string;
  page?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  timestamp: string;
  noSource?: boolean;
  insufficientContext?: boolean;
  thinkingSteps?: string[];
}

function ThinkingBlock({ steps }: { steps: string[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-xl border overflow-hidden mb-2" style={{ borderColor: "rgba(93,39,184,0.25)", background: "rgba(93,39,184,0.04)" }}>
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center gap-2.5 px-4 py-2.5 text-left"
      >
        <Brain size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
        <span className="text-xs font-medium flex-1" style={{ color: "var(--accent)" }}>
          Thought for a moment
        </span>
        {expanded
          ? <ChevronUp size={12} style={{ color: "var(--accent)" }} />
          : <ChevronDown size={12} style={{ color: "var(--accent)" }} />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 border-t flex flex-col gap-1.5" style={{ borderColor: "rgba(93,39,184,0.15)" }}>
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide pt-4 pb-2" style={{ letterSpacing: "0.07em" }}>
            Reasoning trace
          </p>
          {steps.map((line, i) => (
            <div key={i} className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1" style={{ background: "var(--border)" }} />
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CitationChip({ citation, active, onClick }: { citation: Citation; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs transition-all"
      style={{
        fontFamily: "var(--font-mono)",
        background: active ? "var(--accent)" : "rgba(93,39,184,0.12)",
        color: active ? "#fff" : "var(--accent)",
        border: `1px solid rgba(93,39,184,0.25)`,
      }}
    >
      <span>{citation.id}</span>
    </button>
  );
}

function CitationPanel({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? citations : citations.slice(0, 2);

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground font-medium" style={{ letterSpacing: "0.06em" }}>
          SOURCES
        </span>
        {citations.length > 2 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-muted-foreground flex items-center gap-0.5 hover:text-foreground transition-colors"
          >
            {expanded ? <>Show less <ChevronUp size={11} /></> : <>+{citations.length - 2} more <ChevronDown size={11} /></>}
          </button>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        {visible.map((c) => (
          <div
            key={c.id}
            className="flex items-start gap-2.5 p-2.5 rounded-md group cursor-pointer transition-colors hover:bg-accent/5"
            style={{ background: "var(--muted)", border: "1px solid var(--border)" }}
            onClick={() => window.open(`file://${c.source}`, "_blank")}
          >
            <span
              className="text-xs flex-shrink-0 w-4 h-4 flex items-center justify-center rounded"
              style={{
                fontFamily: "var(--font-mono)",
                background: "rgba(93,39,184,0.15)",
                color: "var(--accent)",
                fontWeight: 500,
              }}
            >
              {c.id}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-medium text-foreground leading-snug group-hover:underline">{c.title}</span>
                <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 text-muted-foreground flex-shrink-0" />
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {c.source}{c.page ? ` · p. ${c.page}` : ""}
              </div>
              <div className="text-xs text-muted-foreground mt-1 leading-relaxed line-clamp-2">
                "{c.excerpt}"
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function parseCitationContent(content: string, citations: Citation[] = []) {
  const parts: Array<{ type: "text" | "citation"; value: string; citation?: Citation }> = [];
  const regex = /\[(\d+)\]/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) parts.push({ type: "text", value: content.slice(lastIndex, match.index) });
    const citation = citations.find((c) => c.id === parseInt(match[1]));
    if (citation) parts.push({ type: "citation", value: match[0], citation });
    else parts.push({ type: "text", value: match[0] });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < content.length) parts.push({ type: "text", value: content.slice(lastIndex) });
  return parts;
}

export function ChatMessage({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  const [activeCitId, setActiveCitId] = useState<number | null>(null);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      const el = document.createElement("textarea");
      el.value = message.content;
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const isUser = message.role === "user";
  const parts = parseCitationContent(message.content, message.citations);

  // System-level notices: no source / insufficient context
  if (message.noSource || message.insufficientContext) {
    return (
      <div className="flex justify-center">
        <div
          className="flex items-center gap-2 px-4 py-4 rounded-xl text-xs max-w-lg text-center"
          style={{
            background: "rgba(231,35,0,0.06)",
            border: "1px solid rgba(231,35,0,0.18)",
            color: "var(--destructive)",
          }}
        >
          <AlertCircle size={13} className="flex-shrink-0" />
          <span style={{ fontFamily: "var(--font-sans)" }}>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-4 ${isUser ? "flex-row-reverse" : ""} group`}>
      {/* Avatar */}
      {!isUser && (
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: "var(--primary)" }}
        >
          <span className="text-xs" style={{ fontFamily: "var(--font-mono)", fontWeight: 500, color: "var(--highlight)" }}>
            AI
          </span>
        </div>
      )}

      <div className={`flex flex-col gap-1 max-w-[82%] ${isUser ? "items-end" : "items-start"}`}>
        {!isUser && message.thinkingSteps && message.thinkingSteps.length > 0 && (
          <ThinkingBlock steps={message.thinkingSteps} />
        )}
        <div
          className="px-4 py-4 text-sm leading-relaxed"
          style={
            isUser
              ? {
                  background: "var(--primary)",
                  color: "var(--primary-foreground)",
                  borderRadius: "18px 18px 4px 18px",
                }
              : {
                  background: "var(--card)",
                  color: "var(--card-foreground)",
                  border: "1px solid var(--border)",
                  borderRadius: "4px 18px 18px 18px",
                }
          }
        >
          <div className="whitespace-pre-wrap">
            {parts.map((part, i) =>
              part.type === "citation" && part.citation ? (
                <CitationChip
                  key={i}
                  citation={part.citation}
                  active={activeCitId === part.citation.id}
                  onClick={() =>
                    setActiveCitId(activeCitId === part.citation!.id ? null : part.citation!.id)
                  }
                />
              ) : (
                <span key={i}>{part.value}</span>
              )
            )}
            {message.isStreaming && (
              <span
                className="inline-block w-0.5 h-3.5 ml-0.5 animate-pulse"
                style={{ background: "var(--muted-foreground)", verticalAlign: "text-bottom" }}
              />
            )}
          </div>

          {!isUser && message.citations && message.citations.length > 0 && (
            <CitationPanel citations={message.citations} />
          )}
        </div>

        {/* Actions */}
        {!isUser && !message.isStreaming && (
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity px-1">
            <button
              onClick={handleCopy}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Copy"
            >
              {copied ? <span className="text-xs" style={{ color: "var(--accent)" }}>✓</span> : <Copy size={13} />}
            </button>
            <button className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Good response">
              <ThumbsUp size={13} />
            </button>
            <button className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Bad response">
              <ThumbsDown size={13} />
            </button>
            <button className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Regenerate">
              <RotateCcw size={13} />
            </button>
            <span className="text-xs text-muted-foreground ml-1">{message.timestamp}</span>
          </div>
        )}

        {isUser && (
          <div className="text-xs text-muted-foreground px-1">{message.timestamp}</div>
        )}
      </div>
    </div>
  );
}
