import { useState, useRef, useEffect } from "react";
import { ChatMessage, Message, Citation } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { Tag, TagType, Document } from "../types";
import { TagPill } from "./TagPill";
import {
  Sparkles, TrendingUp, Scale, Users, FileText,
  SlidersHorizontal, X, ChevronDown, ChevronUp, Brain,
} from "lucide-react";

const MOCK_CITATIONS: Citation[] = [
  {
    id: 1,
    title: "Q3 2024 Financial Report",
    source: "Q3 2024 Financial Report.pdf",
    page: "14",
    excerpt: "Total revenue increased by 23% year-over-year, reaching $142.3M compared to $115.7M in Q3 2023.",
  },
  {
    id: 2,
    title: "Market Analysis Report",
    source: "Market Analysis Report.pdf",
    page: "37",
    excerpt: "Market share expansion in the APAC region contributed 8.4 percentage points to overall growth.",
  },
  {
    id: 3,
    title: "Product Roadmap 2026",
    source: "Product Roadmap 2026.pdf",
    page: "5",
    excerpt: "Platform investments in H2 are expected to drive an additional $18M in ARR by Q1 2027.",
  },
];

const INITIAL_MESSAGES: Message[] = [
  {
    id: "1",
    role: "user",
    content: "Summarize our Q3 financial performance and highlight the main growth drivers.",
    timestamp: "2:14 PM",
  },
  {
    id: "2",
    role: "assistant",
    content:
      "Based on the Q3 Financial Report, Acme delivered strong results this quarter.\n\n**Revenue** grew 23% year-over-year to $142.3M [1], driven by three key factors:\n\n1. **APAC market expansion** — geographic growth contributed 8.4 percentage points [2], with new enterprise contracts in Japan and South Korea.\n\n2. **Platform investments** — the core platform upgrades are projected to unlock $18M in additional ARR by Q1 2027 [3].\n\n3. **Improved retention** — net revenue retention reached 118%, up from 109% in Q3 2023 [1].\n\nGross margin held steady at 71.4%. Operating expenses grew at a slower rate (14%) than revenue, indicating improving operational leverage.",
    citations: MOCK_CITATIONS,
    timestamp: "2:14 PM",
  },
];

const SUGGESTIONS = [
  { icon: <TrendingUp size={14} />, text: "Compare Q3 vs Q2 performance" },
  { icon: <Users size={14} />, text: "Summarize customer feedback themes" },
  { icon: <Scale size={14} />, text: "Key points from legal documents" },
  { icon: <FileText size={14} />, text: "What's on the 2026 roadmap?" },
];

const NO_SOURCE_MSG =
  "No source document supporting requested information found in the database";

const INSUFFICIENT_CONTEXT_MSG =
  "The documents available in the database do not provide enough context to accurately answer your query. Please upload relevant source documents or refine your question.";

// Topics covered by the mock document set
const KNOWN_TOPICS = [
  "financial","finance","revenue","profit","q3","q2","quarter","annual","margin",
  "product","roadmap","feature","platform","release",
  "market","competitor","analysis","landscape","apac","region",
  "customer","survey","nps","csat","satisfaction","feedback",
  "legal","contract","compliance","regulatory","framework","policy",
  "hr","employee","staff","leave","benefits","conduct","handbook",
];

function queryHasKnownContext(text: string): boolean {
  const lower = text.toLowerCase();
  return KNOWN_TOPICS.some((t) => lower.includes(t));
}

const THINKING_STEPS = [
  "Parsing query intent and extracting key entities…",
  "Scanning document index for relevant chunks…",
  "Identified 11 candidate passages across 3 documents",
  "Re-ranking passages by semantic similarity to query…",
  "Top sources: Q3 Financial Report · Market Analysis · Product Roadmap",
  "Checking for contradictions or conflicting data between sources…",
  "No conflicting signals found — sources are consistent",
  "Planning response structure with section headers…",
  "Drafting answer with inline citations ready for attribution…",
];

const STREAMING_RESPONSE =
  "Based on the customer survey results, satisfaction scores improved by 14 points [1] following the platform update in May. The primary drivers were faster response times [2] and the new self-service portal [3], which reduced support ticket volume by 31%.";

interface TagFilterPanelProps {
  tags: Tag[];
  tagTypes: TagType[];
  documents: Document[];
  selectedTagIds: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
}

function TagFilterPanel({ tags, tagTypes, documents, selectedTagIds, onToggle, onClear }: TagFilterPanelProps) {
  const [open, setOpen] = useState(false);

  const allUsedTagIds = Array.from(new Set(documents.flatMap((d) => d.tagIds)));
  const matchingDocCount = selectedTagIds.length === 0
    ? documents.length
    : documents.filter((d) => selectedTagIds.some((id) => d.tagIds.includes(id))).length;

  const groupedByType = tagTypes.map((tt) => ({
    type: tt,
    tags: tags.filter((t) => t.typeId === tt.id && allUsedTagIds.includes(t.id)),
  })).filter((g) => g.tags.length > 0);

  return (
    <div className="border-b border-border flex-shrink-0">
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-2 px-8 py-2 hover:bg-muted/30 transition-colors text-sm"
      >
        <SlidersHorizontal size={13} style={{ color: selectedTagIds.length > 0 ? "var(--accent)" : "var(--muted-foreground)" }} />
        <span className="text-muted-foreground">
          {selectedTagIds.length > 0 ? "Searching selected tags" : "Search scope: all documents"}
        </span>
        {selectedTagIds.length > 0 && (
          <span className="px-1.5 py-0.5 rounded-full text-xs text-white font-medium" style={{ background: "var(--accent)" }}>
            {selectedTagIds.length}
          </span>
        )}
        <span className="text-xs text-muted-foreground ml-auto mr-1">
          {matchingDocCount} doc{matchingDocCount !== 1 ? "s" : ""} in scope
        </span>
        {open ? <ChevronUp size={13} className="text-muted-foreground" /> : <ChevronDown size={13} className="text-muted-foreground" />}
      </button>

      {open && (
        <div className="px-8 pb-4 flex flex-col gap-4">
          {/* Selected tags */}
          {selectedTagIds.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground">Active:</span>
              {selectedTagIds.map((id) => {
                const tag = tags.find((t) => t.id === id);
                if (!tag) return null;
                const tt = tagTypes.find((t) => t.id === tag.typeId);
                return (
                  <TagPill key={id} tag={tag} tagType={tt} selected onRemove={() => onToggle(id)} size="sm" />
                );
              })}
              <button onClick={onClear} className="text-xs text-muted-foreground underline hover:text-foreground">
                Clear all
              </button>
            </div>
          )}

          {/* Scope callout */}
          {selectedTagIds.length > 0 ? (
            <div className="flex items-start gap-2 px-4 py-4 rounded-lg text-xs" style={{ background: "rgba(93,39,184,0.08)", color: "var(--accent)" }}>
              <SlidersHorizontal size={12} className="mt-0.5 flex-shrink-0" />
              The AI assistant will search only the {matchingDocCount} document{matchingDocCount !== 1 ? "s" : ""} matching any of your selected tags.
            </div>
          ) : (
            <div className="flex items-start gap-2 px-4 py-4 rounded-lg text-xs" style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}>
              <SlidersHorizontal size={12} className="mt-0.5 flex-shrink-0" />
              No tags selected. The AI assistant will search across <span className="font-medium text-foreground mx-0.5">all {documents.length} documents</span> in the database. Select tags below to narrow the search scope.
            </div>
          )}

          {/* Tag type groups */}
          <div className="flex flex-col gap-2">
            {groupedByType.map(({ type: tt, tags: typeTags }) => (
              <div key={tt.id}>
                <p className="text-xs text-muted-foreground mb-1.5" style={{ letterSpacing: "0.04em" }}>
                  {tt.name.toUpperCase()}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {typeTags.map((tag) => (
                    <TagPill
                      key={tag.id}
                      tag={tag}
                      selected={selectedTagIds.includes(tag.id)}
                      onClick={() => onToggle(tag.id)}
                      size="sm"
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface ChatViewProps {
  chatId: string | null;
  tags: Tag[];
  tagTypes: TagType[];
  documents: Document[];
}

export function ChatView({ chatId, tags, tagTypes, documents }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>(chatId ? INITIAL_MESSAGES : []);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [activeTagIds, setActiveTagIds] = useState<string[]>([]);
  const [showThinking, setShowThinking] = useState(true);
  const [thinkingLines, setThinkingLines] = useState<string[]>([]);
  const [thinkingDone, setThinkingDone] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const thinkRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  useEffect(() => {
    setMessages(chatId ? INITIAL_MESSAGES : []);
    setIsStreaming(false);
    setStreamingContent("");
    setIsThinking(false);
    setThinkingLines([]);
    setThinkingDone(false);
  }, [chatId]);

  const toggleTag = (id: string) => {
    setActiveTagIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const getMatchingDocs = () => {
    if (activeTagIds.length === 0) return documents;
    return documents.filter((d) => activeTagIds.some((id) => d.tagIds.includes(id)));
  };

  const startStreaming = (capturedThinkingLines: string[]) => {
    setThinkingDone(true);
    setTimeout(() => {
      setIsThinking(false);
      setIsStreaming(true);
      setStreamingContent("");
      let index = 0;
      streamRef.current = setInterval(() => {
        index += Math.floor(Math.random() * 4) + 2;
        setStreamingContent(STREAMING_RESPONSE.slice(0, index));
        if (index >= STREAMING_RESPONSE.length) {
          clearInterval(streamRef.current!);
          setIsStreaming(false);
          setStreamingContent("");
          setThinkingLines([]);
          setThinkingDone(false);
          setMessages((prev) => [
            ...prev,
            {
              id: (Date.now() + 1).toString(),
              role: "assistant",
              content: STREAMING_RESPONSE,
              citations: MOCK_CITATIONS,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              thinkingSteps: capturedThinkingLines,
            },
          ]);
        }
      }, 30);
    }, 500);
  };

  const handleSend = (text: string) => {
    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMsg]);

    const matchingDocs = getMatchingDocs();
    const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    // Case 1: tag scope yields zero matching documents
    if (matchingDocs.length === 0) {
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: NO_SOURCE_MSG,
        timestamp: ts,
        noSource: true,
      } as Message]);
      return;
    }

    // Case 2: documents exist but query topic is not covered
    if (!queryHasKnownContext(text)) {
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: INSUFFICIENT_CONTEXT_MSG,
        timestamp: ts,
        insufficientContext: true,
      } as Message]);
      return;
    }

    // With thinking enabled: reveal steps one by one, then stream
    if (showThinking) {
      setIsThinking(true);
      setThinkingDone(false);
      setThinkingLines([]);
      let step = 0;
      const revealNext = () => {
        step += 1;
        const current = THINKING_STEPS.slice(0, step);
        setThinkingLines(current);
        if (step < THINKING_STEPS.length) {
          thinkRef.current = setTimeout(revealNext, 380 + Math.random() * 220);
        } else {
          startStreaming(current);
        }
      };
      thinkRef.current = setTimeout(revealNext, 300);
    } else {
      setIsStreaming(true);
      setStreamingContent("");
      let index = 0;
      streamRef.current = setInterval(() => {
        index += Math.floor(Math.random() * 4) + 2;
        setStreamingContent(STREAMING_RESPONSE.slice(0, index));
        if (index >= STREAMING_RESPONSE.length) {
          clearInterval(streamRef.current!);
          setIsStreaming(false);
          setStreamingContent("");
          setMessages((prev) => [
            ...prev,
            {
              id: (Date.now() + 1).toString(),
              role: "assistant",
              content: STREAMING_RESPONSE,
              citations: MOCK_CITATIONS,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            },
          ]);
        }
      }, 30);
    }
  };

  const handleStop = () => {
    if (thinkRef.current) clearTimeout(thinkRef.current);
    if (streamRef.current) clearInterval(streamRef.current);
    setIsThinking(false);
    setThinkingLines([]);
    setThinkingDone(false);
    setIsStreaming(false);
    if (streamingContent.trim()) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: streamingContent,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    }
    setStreamingContent("");
  };

  const isEmpty = messages.length === 0 && !isStreaming && !isThinking;

  return (
    <div className="flex flex-col h-full">
      {/* Tag filter bar */}
      <TagFilterPanel
        tags={tags}
        tagTypes={tagTypes}
        documents={documents}
        selectedTagIds={activeTagIds}
        onToggle={toggleTag}
        onClear={() => setActiveTagIds([])}
      />

      {/* Active tag scope indicator */}
      {activeTagIds.length > 0 && (
        <div className="px-8 py-2 flex items-center gap-2 flex-shrink-0" style={{ background: "rgba(93,39,184,0.04)" }}>
          <span className="text-xs text-muted-foreground">Searching in:</span>
          {activeTagIds.slice(0, 4).map((id) => {
            const tag = tags.find((t) => t.id === id);
            if (!tag) return null;
            const tt = tagTypes.find((t) => t.id === tag.typeId);
            return <TagPill key={id} tag={tag} tagType={tt} size="sm" />;
          })}
          {activeTagIds.length > 4 && <span className="text-xs text-muted-foreground">+{activeTagIds.length - 4} more</span>}
          <button onClick={() => setActiveTagIds([])} className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
            <X size={11} /> Clear
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto" style={{ scrollbarWidth: "thin" }}>
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-8 px-8">
            <div className="text-center">
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "var(--primary)" }}
              >
                <Sparkles size={22} style={{ color: "var(--highlight)" }} />
              </div>
              <h2 className="text-foreground mb-1">How can I help you today?</h2>
              <p className="text-sm text-muted-foreground max-w-sm">
                Ask questions about your documents. Use the tag filter above to focus on specific document sets.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(s.text)}
                  className="flex items-center gap-2 px-4 py-4 rounded-xl text-sm text-left transition-colors hover:bg-muted"
                  style={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    color: "var(--foreground)",
                  }}
                >
                  <span style={{ color: "var(--accent)" }}>{s.icon}</span>
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto px-8 py-8 flex flex-col gap-8">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}

            {/* Live thinking block — shown while thinking phase is active */}
            {(isThinking || (thinkingLines.length > 0 && isStreaming)) && (
              <div className="max-w-[82%]">
                <div className="rounded-xl border overflow-hidden" style={{ borderColor: "rgba(93,39,184,0.25)", background: "rgba(93,39,184,0.04)" }}>
                  <div className="flex items-center gap-2.5 px-4 py-2.5">
                    <Brain size={13} className="animate-pulse flex-shrink-0" style={{ color: "var(--accent)" }} />
                    <span className="text-xs font-medium flex-1" style={{ color: "var(--accent)" }}>Thinking…</span>
                  </div>
                  <div className="px-4 pb-4 border-t flex flex-col gap-1.5" style={{ borderColor: "rgba(93,39,184,0.15)" }}>
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide pt-4 pb-2" style={{ letterSpacing: "0.07em" }}>Reasoning trace</p>
                    {thinkingLines.map((line, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs leading-relaxed" style={{ color: i === thinkingLines.length - 1 ? "var(--accent)" : "var(--muted-foreground)" }}>
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: i === thinkingLines.length - 1 ? "var(--accent)" : "var(--border)", marginTop: "5px" }} />
                        {line}
                        {i === thinkingLines.length - 1 && !thinkingDone && (
                          <span className="inline-flex gap-0.5 ml-1 items-center">
                            {[0, 1, 2].map((d) => (
                              <span key={d} className="w-1 h-1 rounded-full animate-bounce" style={{ background: "var(--accent)", animationDelay: `${d * 0.15}s` }} />
                            ))}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {isStreaming && streamingContent && (
              <ChatMessage
                message={{
                  id: "streaming",
                  role: "assistant",
                  content: streamingContent,
                  isStreaming: true,
                  timestamp: "",
                }}
              />
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex-shrink-0 px-8 pb-8 pt-4 max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-end mb-2">
          <button
            onClick={() => setShowThinking((p) => !p)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium border transition-colors"
            style={{
              background: showThinking ? "rgba(93,39,184,0.08)" : "transparent",
              borderColor: showThinking ? "rgba(93,39,184,0.3)" : "var(--border)",
              color: showThinking ? "var(--accent)" : "var(--muted-foreground)",
            }}
            title={showThinking ? "Thinking is on — click to turn off" : "Thinking is off — click to turn on"}
          >
            <Brain size={12} />
            Thinking {showThinking ? "on" : "off"}
            <span
              className="inline-block w-6 h-3.5 rounded-full relative transition-colors ml-0.5"
              style={{ background: showThinking ? "var(--accent)" : "var(--border)" }}
            >
              <span
                className="absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white transition-all"
                style={{ left: showThinking ? "calc(100% - 0.625rem - 0.125rem)" : "0.125rem" }}
              />
            </span>
          </button>
        </div>
        <ChatInput onSend={handleSend} isStreaming={isStreaming || isThinking} onStop={handleStop} />
      </div>
    </div>
  );
}
